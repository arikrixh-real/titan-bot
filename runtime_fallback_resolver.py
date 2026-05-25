import json
from pathlib import Path

from runtime_dependency_graph import SAFETY_FLAGS
from runtime_engine_health import (
    RUNTIME_DIR,
    atomic_write_json,
    build_master_brain_runtime_health,
    build_setup_engine_runtime_health,
    read_json_safe,
)
from utils.market_hours import as_ist_datetime, is_trade_window, is_trading_day


SCANNER_STATUS_PATH = RUNTIME_DIR / "scanner_status.json"
SCANNER_FILTER_TRUTH_STATUS_PATH = RUNTIME_DIR / "scanner_filter_truth_status.json"
MARKET_DATA_HEALTH_PATH = RUNTIME_DIR / "titan_market_data_health.json"
LIVE_PRICE_HEALTH_PATH = RUNTIME_DIR / "live_price_health.json"
DAEMON_HEALTH_PATH = RUNTIME_DIR / "daemon_health.json"
AUTHORITATIVE_RUNTIME_HEALTH_PATH = RUNTIME_DIR / "titan_authoritative_runtime_health.json"
MASTER_ENGINE_FALLBACK_COMPONENTS = {"MASTER_BRAIN_UNAVAILABLE", "SETUP_ENGINE_UNAVAILABLE"}
RUNNING_DAEMON_STATUSES = {"ALIVE", "RUNNING", "STARTING"}
RUNTIME_FALLBACK_RESOLUTION_PATH = RUNTIME_DIR / "runtime_fallback_resolution.json"


def _listify(value):
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str) and value:
        return [part for part in value.split("|") if part]
    return []


def _scanner_fallback_components(scanner):
    components = []
    components.extend(_listify(scanner.get("fallback_components")))
    components.extend(_listify(scanner.get("fallback_reason")))
    if scanner.get("ohlc_fallback_required") and "OHLC_STALE" not in components:
        components.append("OHLC_STALE")
    return sorted(set(components))


def _runtime_health_value(payload, key):
    return str(payload.get(key) or "UNKNOWN").upper()


def _daemon_alive(daemon, authoritative_runtime=None):
    daemon_status = str(daemon.get("status") or daemon.get("overall_status") or "").upper()
    if daemon_status in RUNNING_DAEMON_STATUSES:
        return True
    authoritative_runtime = authoritative_runtime or {}
    owner = str(
        authoritative_runtime.get("runtime_owner")
        or authoritative_runtime.get("deterministic_runtime_owner")
        or ""
    ).lower()
    if owner in {"daemon_pid", "confirmed_daemon_pid", "running_artifact_only", "daemon_health"}:
        return True
    return False


def _off_hours_runtime_continuity_enabled(now_ist, daemon, authoritative_runtime=None):
    return not is_trade_window(now_ist) and _daemon_alive(daemon, authoritative_runtime)


def _apply_off_hours_master_continuity(master, now_ist):
    payload = dict(master or {})
    if _runtime_health_value(payload, "master_brain_runtime_health") in {"ACTIVE", "STALE", "UNAVAILABLE"}:
        payload["previous_master_brain_runtime_health"] = payload.get("master_brain_runtime_health")
        payload["master_brain_runtime_health"] = "RESEARCH_ACTIVE"
        payload["master_brain_research_freshness"] = "RESEARCH_ACTIVE"
        payload["master_brain_freshness_confidence"] = "MEDIUM"
        payload["overall_status"] = "PASS"
        payload["off_hours_runtime_continuity"] = True
        payload["continuity_generated_at_ist"] = now_ist.isoformat()
        payload["affects_execution"] = False
        payload["affects_live_ranking"] = False
        payload["alert_generation"] = False
        payload["broker_mutation"] = False
        return payload, True
    return payload, False


def _apply_off_hours_setup_continuity(setup, now_ist):
    payload = dict(setup or {})
    if _runtime_health_value(payload, "setup_runtime_health") in {"ACTIVE", "STALE", "UNAVAILABLE"}:
        payload["previous_setup_runtime_health"] = payload.get("setup_runtime_health")
        payload["setup_runtime_health"] = "OFF_HOURS_STANDBY"
        payload["setup_pipeline_health"] = "OFF_HOURS_STANDBY"
        payload["setup_engine_research_freshness"] = "OFF_HOURS_STANDBY"
        payload["setup_freshness_confidence"] = "MEDIUM"
        payload["overall_status"] = "PASS"
        payload["off_hours_runtime_continuity"] = True
        payload["continuity_generated_at_ist"] = now_ist.isoformat()
        payload["affects_execution"] = False
        payload["affects_live_ranking"] = False
        payload["alert_generation"] = False
        payload["broker_mutation"] = False
        return payload, True
    return payload, False


def apply_off_hours_runtime_continuity(master, setup, now=None, daemon=None, authoritative_runtime=None, write=True, require_daemon=True):
    now_ist = as_ist_datetime(now)
    daemon = daemon if isinstance(daemon, dict) else read_json_safe(DAEMON_HEALTH_PATH)
    authoritative_runtime = (
        authoritative_runtime
        if isinstance(authoritative_runtime, dict)
        else read_json_safe(AUTHORITATIVE_RUNTIME_HEALTH_PATH)
    )
    enabled = _off_hours_runtime_continuity_enabled(now_ist, daemon, authoritative_runtime) if require_daemon else not is_trade_window(now_ist)
    if not enabled:
        return master, setup, False

    master_payload, master_changed = _apply_off_hours_master_continuity(master, now_ist)
    setup_payload, setup_changed = _apply_off_hours_setup_continuity(setup, now_ist)
    if write:
        if master_changed:
            atomic_write_json(RUNTIME_DIR / "master_brain_runtime_health.json", master_payload)
        if setup_changed:
            atomic_write_json(RUNTIME_DIR / "setup_engine_runtime_health.json", setup_payload)
    return master_payload, setup_payload, True


def _data_degraded(market_data, live_price, scanner_components):
    market_status = str(market_data.get("overall_status") or market_data.get("status") or "").upper()
    live_status = str(live_price.get("overall_status") or live_price.get("status") or "").upper()
    if "OHLC_STALE" in scanner_components:
        return True
    if market_status in {"WARNING", "FAIL", "DEGRADED"}:
        return True
    if live_status in {"WARNING", "FAIL", "DEGRADED"}:
        return True
    return False


def _resolve_truthfulness(*, scanner_fallback_active, scanner_stale, master_health, setup_health, data_degraded, off_hours, off_hours_continuity):
    engine_unavailable = master_health in {"UNAVAILABLE", "STALE"} or setup_health in {"UNAVAILABLE", "STALE"}
    if off_hours_continuity and not data_degraded:
        return "OFF_HOURS_RESEARCH_STANDBY"
    if scanner_fallback_active and engine_unavailable:
        return "ENGINE_UNAVAILABLE"
    if scanner_fallback_active and data_degraded:
        return "DATA_DEGRADED"
    if scanner_fallback_active and off_hours:
        return "EXPECTED_OFF_HOURS"
    if scanner_fallback_active and not engine_unavailable and scanner_stale:
        return "STALE_FALSE_FALLBACK"
    if scanner_fallback_active:
        return "REAL"
    if engine_unavailable or data_degraded:
        return "PARTIAL"
    return "REAL"


def _severity(truthfulness, fallback_active):
    if truthfulness in {"ENGINE_UNAVAILABLE", "DATA_DEGRADED"}:
        return "HIGH"
    if truthfulness == "REAL" and fallback_active:
        return "MEDIUM"
    if truthfulness in {"STALE_FALSE_FALLBACK", "EXPECTED_OFF_HOURS", "OFF_HOURS_RESEARCH_STANDBY", "PARTIAL"}:
        return "LOW"
    return "NONE"


def _scanner_confidence(truthfulness, scanner_truth, master_health, setup_health, fallback_active):
    if truthfulness in {"ENGINE_UNAVAILABLE", "DATA_DEGRADED"}:
        return "LOW"
    if fallback_active and truthfulness == "REAL":
        return "LOW"
    if truthfulness == "OFF_HOURS_RESEARCH_STANDBY":
        return "MEDIUM"
    if master_health in {"ACTIVE", "RESEARCH_ACTIVE", "OFF_HOURS_STANDBY"} and setup_health in {"ACTIVE", "RESEARCH_ACTIVE", "OFF_HOURS_STANDBY"}:
        if truthfulness in {"STALE_FALSE_FALLBACK", "EXPECTED_OFF_HOURS", "PARTIAL"}:
            return "MEDIUM"
        if scanner_truth.get("counter_confidence") in {"HIGH", "MEDIUM"}:
            return scanner_truth.get("counter_confidence")
        return "HIGH"
    if master_health in {"DEGRADED", "FALLBACK_ACTIVE"} or setup_health in {"DEGRADED", "FALLBACK_ACTIVE"}:
        return "MEDIUM"
    return "LOW"


def run_runtime_fallback_resolution(now=None, output_path=RUNTIME_FALLBACK_RESOLUTION_PATH):
    now_ist = as_ist_datetime(now)
    master = build_master_brain_runtime_health(now=now_ist)
    setup = build_setup_engine_runtime_health(now=now_ist)
    scanner = read_json_safe(SCANNER_STATUS_PATH)
    scanner_truth = read_json_safe(SCANNER_FILTER_TRUTH_STATUS_PATH)
    market_data = read_json_safe(MARKET_DATA_HEALTH_PATH)
    live_price = read_json_safe(LIVE_PRICE_HEALTH_PATH)
    daemon = read_json_safe(DAEMON_HEALTH_PATH)
    authoritative_runtime = read_json_safe(AUTHORITATIVE_RUNTIME_HEALTH_PATH)
    master, setup, off_hours_continuity = apply_off_hours_runtime_continuity(
        master,
        setup,
        now=now_ist,
        daemon=daemon,
        authoritative_runtime=authoritative_runtime,
    )

    raw_components = _scanner_fallback_components(scanner)
    engine_only_off_hours_fallback = bool(
        off_hours_continuity
        and raw_components
        and set(raw_components).issubset(MASTER_ENGINE_FALLBACK_COMPONENTS)
    )
    components = [] if engine_only_off_hours_fallback else raw_components
    scanner_fallback_active = bool(scanner.get("scan_only") or components)
    if engine_only_off_hours_fallback and bool(scanner.get("scan_only")):
        scanner_fallback_active = False
    scanner_stale = bool(scanner_truth.get("stale_snapshot_warning"))
    off_hours = not is_trade_window(now_ist)
    data_degraded = _data_degraded(market_data, live_price, components)
    master_health = _runtime_health_value(master, "master_brain_runtime_health")
    setup_health = _runtime_health_value(setup, "setup_runtime_health")
    truthfulness = _resolve_truthfulness(
        scanner_fallback_active=scanner_fallback_active,
        scanner_stale=scanner_stale,
        master_health=master_health,
        setup_health=setup_health,
        data_degraded=data_degraded,
        off_hours=off_hours,
        off_hours_continuity=off_hours_continuity,
    )
    confidence = _scanner_confidence(truthfulness, scanner_truth, master_health, setup_health, scanner_fallback_active)
    reason_parts = components[:]
    if truthfulness == "STALE_FALSE_FALLBACK":
        reason_parts.append("stale historical fallback; master/setup currently healthy")
    elif truthfulness == "OFF_HOURS_RESEARCH_STANDBY":
        reason_parts.append("off-hours research standby; daemon alive")
    elif truthfulness == "EXPECTED_OFF_HOURS":
        reason_parts.append("outside trade window")
    elif truthfulness == "PARTIAL" and data_degraded:
        reason_parts.append("data dependency degraded without scanner fallback")
    fallback_reason = "|".join(reason_parts) if reason_parts else None
    recommended = "NORMAL"
    if truthfulness == "STALE_FALSE_FALLBACK":
        recommended = "REFRESH_SCANNER_STATUS"
    elif truthfulness == "OFF_HOURS_RESEARCH_STANDBY":
        recommended = "OFF_HOURS_RESEARCH_STANDBY"
    elif truthfulness == "EXPECTED_OFF_HOURS":
        recommended = "OFF_HOURS_STANDBY"
    elif truthfulness == "ENGINE_UNAVAILABLE":
        recommended = "REVIEW_ENGINE_HEALTH"
    elif truthfulness == "DATA_DEGRADED":
        recommended = "DATA_DEGRADED"

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "overall_status": "PASS" if confidence in {"HIGH", "MEDIUM"} and truthfulness != "ENGINE_UNAVAILABLE" else "WARNING",
        "fallback_active": bool(scanner_fallback_active),
        "fallback_reason": fallback_reason,
        "fallback_components": components,
        "suppressed_off_hours_engine_components": raw_components if engine_only_off_hours_fallback else [],
        "fallback_severity": _severity(truthfulness, scanner_fallback_active),
        "fallback_truthfulness": truthfulness,
        "off_hours_runtime_continuity": off_hours_continuity,
        "master_brain_research_freshness": master.get("master_brain_research_freshness"),
        "setup_engine_research_freshness": setup.get("setup_engine_research_freshness"),
        "scanner_confidence": confidence,
        "scanner_stale_snapshot_warning": scanner_stale,
        "master_brain_runtime_health": master,
        "setup_engine_runtime_health": setup,
        "market_data_health_status": market_data.get("overall_status") or market_data.get("status"),
        "live_price_health_status": live_price.get("overall_status") or live_price.get("status"),
        "daemon_health_status": daemon.get("overall_status") or daemon.get("status"),
        "current_market_window": {
            "is_trading_day": is_trading_day(now_ist),
            "is_trade_window": is_trade_window(now_ist),
        },
        "recommended_runtime_state": recommended,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run_runtime_fallback_resolution(), indent=2, sort_keys=True))
