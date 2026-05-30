import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from supabase import create_client
from dotenv import load_dotenv
from engines.time_filter import current_bot_mode


DASHBOARD_SYNC_STATUS_PATH = Path("data") / "runtime" / "dashboard_sync_status.json"
HEARTBEAT_PATH = Path("data") / "runtime" / "titan_heartbeat.json"
RUNTIME_STATUS_PATH = Path("data") / "runtime" / "titan_runtime_status.json"
SCANNER_STATUS_PATH = Path("data") / "runtime" / "scanner_status.json"
FINAL_VALIDATED_SETUPS_PATH = Path("data") / "runtime" / "final_validated_setups.json"
SETUP_ENGINE_STATUS_PATH = Path("data") / "runtime" / "setup_engine_status.json"
MASTER_BRAIN_STATUS_PATH = Path("data") / "runtime" / "master_brain_status.json"
PAPER_ENGINE_STATUS_PATH = Path("data") / "runtime" / "paper_engine_status.json"
LIVE_PRICE_MONITOR_STATUS_PATH = Path("data") / "runtime" / "live_price_monitor_status.json"
NEWS_PULSE_STATUS_PATH = Path("data") / "runtime" / "news_pulse_status.json"
LIGHT_NEWS_PULSE_STATUS_PATH = Path("data") / "runtime" / "light_news_pulse_status.json"
NEWS_INTELLIGENCE_STATUS_PATH = Path("data") / "runtime" / "news_intelligence_status.json"
DAEMON_HEALTH_PATH = Path("data") / "runtime" / "daemon_health.json"
RUNTIME_RESILIENCE_STATUS_PATH = Path("data") / "runtime" / "runtime_resilience_status.json"
PYRAMID_GOVERNANCE_STATUS_PATH = Path("data") / "runtime" / "pyramid_governance_status.json"
WEEKEND_RESEARCH_MODE_STATUS_PATH = Path("data") / "runtime" / "weekend_research_mode_status.json"
RUNTIME_STATUS_TABLE = "runtime_status"
IST = timezone(timedelta(hours=5, minutes=30))
RUNTIME_FRESH_SECONDS = 15 * 60
RUNTIME_FRESH_SECONDS_BY_MODE = {
    "RESEARCH_MODE": 24 * 3600,
    "WEEKEND_MODE": 72 * 3600,
}


load_dotenv()


RUNTIME_STATUS_SOURCES = {
    "titan_heartbeat": HEARTBEAT_PATH,
    "daemon_health": DAEMON_HEALTH_PATH,
    "titan_runtime_status": RUNTIME_STATUS_PATH,
    "scanner_status": SCANNER_STATUS_PATH,
    "final_validated_setups": FINAL_VALIDATED_SETUPS_PATH,
    "setup_engine_status": SETUP_ENGINE_STATUS_PATH,
    "live_price_monitor_status": LIVE_PRICE_MONITOR_STATUS_PATH,
    "master_brain_status": MASTER_BRAIN_STATUS_PATH,
    "paper_engine_status": PAPER_ENGINE_STATUS_PATH,
    "news_pulse_status": NEWS_PULSE_STATUS_PATH,
    "light_news_pulse_status": LIGHT_NEWS_PULSE_STATUS_PATH,
    "news_intelligence_status": NEWS_INTELLIGENCE_STATUS_PATH,
    "runtime_resilience_status": RUNTIME_RESILIENCE_STATUS_PATH,
    "pyramid_governance_status": PYRAMID_GOVERNANCE_STATUS_PATH,
    "weekend_research_mode_status": WEEKEND_RESEARCH_MODE_STATUS_PATH,
}


def read_json_safe(path):
    try:
        path = Path(path)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def is_active_status(payload):
    if not isinstance(payload, dict):
        return False
    status = str(payload.get("status") or "").upper()
    if not status:
        return False
    inactive_markers = ("STOPPED", "FAILED", "ERROR", "INACTIVE")
    return not any(marker in status for marker in inactive_markers)


def normalized_runtime_mode():
    mode = current_bot_mode()
    return "RESEARCH_MODE" if mode == "INTELLIGENCE_MODE" else mode


def fresh_seconds_for_mode(mode):
    return RUNTIME_FRESH_SECONDS_BY_MODE.get(str(mode or "").upper(), RUNTIME_FRESH_SECONDS)


def get_nested_number(payload, keys, default=0):
    current = payload if isinstance(payload, dict) else {}
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if isinstance(current, (int, float)) and not isinstance(current, bool) else default


def optional_int_number(value):
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def scanner_final_validated_count(scanner_status, final_validated_setups):
    nested = scanner_status.get("final_validated_setups") if isinstance(scanner_status, dict) else {}
    nested = nested if isinstance(nested, dict) else {}
    count = optional_int_number(nested.get("validated_setup_count"))
    if count is not None:
        return count, "scanner_status.final_validated_setups"

    if isinstance(final_validated_setups, dict):
        setups = final_validated_setups.get("setups")
        if isinstance(setups, list):
            return len(setups), "data/runtime/final_validated_setups.json"
        count = optional_int_number(final_validated_setups.get("validated_setup_count"))
        if count is not None:
            return count, "data/runtime/final_validated_setups.json"

    return None, "final_validated_setups_unavailable"


def governance_summary(governance_status, weekend_research_status):
    governance = governance_status.get("governance") if isinstance(governance_status, dict) else {}
    governance = governance if isinstance(governance, dict) else {}
    block_reasons = governance.get("block_reasons")
    if block_reasons is None and isinstance(governance_status, dict):
        block_reasons = governance_status.get("block_reasons")
    if block_reasons is None:
        block_reasons = []
    if not isinstance(block_reasons, list):
        block_reasons = [block_reasons]
    governance_decision = (
        governance.get("decision")
        or governance.get("governance_decision")
        or (governance_status.get("governance_decision") if isinstance(governance_status, dict) else None)
        or (
            weekend_research_status.get("governance_decision")
            if isinstance(weekend_research_status, dict)
            else None
        )
    )
    return str(governance_decision or "").upper(), block_reasons


def latest_timestamp(*payloads):
    timestamps = [
        payload.get("timestamp_ist")
        for payload in payloads
        if isinstance(payload, dict) and payload.get("timestamp_ist")
    ]
    return max(timestamps) if timestamps else datetime.now(IST).isoformat()


def parse_timestamp(value):
    if not value:
        return None
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def payload_fresh(payload, fresh_seconds=15 * 60):
    if not isinstance(payload, dict):
        return False
    timestamp = parse_timestamp(payload.get("timestamp_ist") or payload.get("timestamp") or payload.get("updated_at"))
    if timestamp is None:
        return False
    return (datetime.now(timezone.utc) - timestamp).total_seconds() <= fresh_seconds


def get_supabase_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    missing_env_vars = []
    if not url:
        missing_env_vars.append("SUPABASE_URL")
    if not key:
        missing_env_vars.append("SUPABASE_KEY")
    if missing_env_vars:
        for env_var in missing_env_vars:
            print(f"[DashboardSync ERROR] missing env var: {env_var}")
        return None, missing_env_vars, None
    try:
        return create_client(url, key), [], None
    except Exception as exc:
        error = f"Supabase client creation failed: {exc}"
        print(f"[DashboardSync ERROR] {error}")
        return None, [], error


def upsert_runtime_status_rows(payloads, dashboard_payload):
    client, missing_env_vars, client_error = get_supabase_client()
    sync_result = {
        "supabase_sync_enabled": client is not None,
        "rows_attempted": 0,
        "rows_written": 0,
        "sync_error": None,
    }
    if client is None:
        if missing_env_vars:
            sync_result["sync_error"] = "missing env var: " + ", ".join(missing_env_vars)
        else:
            sync_result["sync_error"] = client_error or "Supabase client unavailable"
        print(f"[DashboardSync RESULT] {json.dumps(sync_result, sort_keys=True)}")
        return sync_result

    now_ist = datetime.now(IST).isoformat()
    rows = []
    for status_key, payload in payloads.items():
        if not isinstance(payload, dict):
            continue
        rows.append(
            {
                "status_key": status_key,
                "payload": payload,
                "timestamp_ist": payload.get("timestamp_ist") or now_ist,
                "updated_at": now_ist,
            }
        )

    rows.append(
        {
            "status_key": "dashboard_sync",
            "payload": dashboard_payload,
            "timestamp_ist": (
                dashboard_payload.get("timestamp_ist")
                or dashboard_payload.get("autonomous_runtime_summary", {}).get("last_runtime_update")
                or now_ist
            ),
            "updated_at": now_ist,
        }
    )
    sync_result["rows_attempted"] = len(rows)

    try:
        response = client.table(RUNTIME_STATUS_TABLE).upsert(
            rows,
            on_conflict="status_key",
        ).execute()
        response_rows = getattr(response, "data", None)
        if isinstance(response_rows, list):
            sync_result["rows_written"] = len(response_rows)
        else:
            sync_result["rows_written"] = len(rows)
        print(f"[DashboardSync RESULT] {json.dumps(sync_result, sort_keys=True)}")
        return sync_result
    except Exception as exc:
        sync_result["sync_error"] = str(exc)
        print(f"[DashboardSync RESULT] {json.dumps(sync_result, sort_keys=True)}")
        return sync_result


def run_dashboard_sync(path=DASHBOARD_SYNC_STATUS_PATH):
    runtime_payloads = {
        status_key: read_json_safe(source_path)
        for status_key, source_path in RUNTIME_STATUS_SOURCES.items()
    }
    heartbeat = runtime_payloads["titan_heartbeat"]
    runtime_status = runtime_payloads["titan_runtime_status"]
    scanner_status = runtime_payloads["scanner_status"]
    final_validated_setups = runtime_payloads["final_validated_setups"]
    setup_engine_status = runtime_payloads["setup_engine_status"]
    master_brain_status = runtime_payloads["master_brain_status"]
    paper_engine_status = runtime_payloads["paper_engine_status"]
    news_pulse_status = runtime_payloads["news_pulse_status"]
    news_intelligence_status = runtime_payloads["news_intelligence_status"]
    live_price_monitor_status = runtime_payloads["live_price_monitor_status"]
    daemon_health = runtime_payloads["daemon_health"]
    resilience_status = runtime_payloads["runtime_resilience_status"]
    governance_status = runtime_payloads["pyramid_governance_status"]
    weekend_research_status = runtime_payloads["weekend_research_mode_status"]

    runtime_mode = "UNKNOWN"
    if isinstance(daemon_health, dict):
        runtime_mode = daemon_health.get("mode") or runtime_mode
    if runtime_mode == "UNKNOWN" and isinstance(runtime_status, dict):
        runtime_mode = runtime_status.get("mode") or runtime_mode
    if runtime_mode == "UNKNOWN" and isinstance(heartbeat, dict):
        runtime_mode = heartbeat.get("mode") or runtime_mode
    if runtime_mode in {"UNKNOWN", "INTELLIGENCE_MODE", "CONTINUOUS_WORKERS", "HEALTH_ONLY"}:
        runtime_mode = normalized_runtime_mode()
    runtime_fresh_seconds = fresh_seconds_for_mode(runtime_mode)
    daemon_alive = (
        isinstance(daemon_health, dict)
        and str(daemon_health.get("status") or "").upper() == "RUNNING"
        and payload_fresh(daemon_health, runtime_fresh_seconds)
    ) or (
        isinstance(heartbeat, dict)
        and str(heartbeat.get("status") or "").upper() == "ALIVE"
        and payload_fresh(heartbeat, runtime_fresh_seconds)
    )
    open_paper_positions = get_nested_number(paper_engine_status, ("open_positions_count",))
    paper_equity = get_nested_number(paper_engine_status, ("paper_account_summary", "equity"), 0.0)
    market_workers_allowed_idle = runtime_mode in {"RESEARCH_MODE", "WEEKEND_MODE"}
    no_open_paper_positions = open_paper_positions == 0

    paper_engine_required = not market_workers_allowed_idle or open_paper_positions > 0
    runtime_health_checks = {
        "daemon_alive": (daemon_alive, "daemon_not_alive"),
        "runtime_status_fresh": (payload_fresh(runtime_status, runtime_fresh_seconds), "runtime_status_stale"),
        "scanner_active": (
            True if market_workers_allowed_idle else is_active_status(scanner_status),
            "scanner_inactive",
        ),
        "master_brain_active": (
            True if market_workers_allowed_idle else is_active_status(master_brain_status),
            "master_brain_inactive",
        ),
        "paper_engine_active": (
            True if not paper_engine_required else is_active_status(paper_engine_status),
            "paper_engine_inactive",
        ),
        "live_price_monitor_active": (
            True if market_workers_allowed_idle else is_active_status(live_price_monitor_status),
            "live_price_monitor_inactive",
        ),
        "news_engine_active": (
            is_active_status(news_pulse_status) or is_active_status(news_intelligence_status),
            "news_engine_inactive",
        ),
    }
    attention_reasons = [
        reason for is_active, reason in runtime_health_checks.values() if not is_active
    ]
    governance_decision, block_reasons = governance_summary(governance_status, weekend_research_status)
    worker_degraded_count = (
        resilience_status.get("worker_health_summary", {}).get("degraded_count")
        if isinstance(resilience_status, dict)
        else None
    )
    stale_packet_count = (
        resilience_status.get("stale_packet_summary", {}).get("stale_count")
        if isinstance(resilience_status, dict)
        else None
    )
    no_block_reasons = not block_reasons
    scanner_final_passed, scanner_final_count_source = scanner_final_validated_count(
        scanner_status,
        final_validated_setups,
    )
    standby_runtime_healthy = (
        market_workers_allowed_idle
        and no_block_reasons
        and worker_degraded_count == 0
        and daemon_alive
        and no_open_paper_positions
    )
    defensive_runtime_healthy = governance_decision == "ALLOW" and worker_degraded_count == 0
    if standby_runtime_healthy or defensive_runtime_healthy:
        attention_reasons = []
    elif no_block_reasons and market_workers_allowed_idle:
        attention_reasons = [
            reason
            for reason in attention_reasons
            if reason not in {"scanner_inactive", "master_brain_inactive", "paper_engine_inactive", "live_price_monitor_inactive"}
        ]
    recovery_suggestion_map = {
        "daemon_not_alive": "Start titan_daemon.py",
        "runtime_status_stale": "Check titan_runtime_status heartbeat writer",
        "scanner_inactive": "Check runtime_scanner.py",
        "master_brain_inactive": "Check runtime_master_brain.py",
        "paper_engine_inactive": "Check runtime_paper_engine.py",
        "live_price_monitor_inactive": "Check runtime_live_price_monitor.py",
        "news_engine_inactive": "Check runtime_news_pulse.py",
    }
    recovery_suggestions = list(
        dict.fromkeys(
            recovery_suggestion_map[reason]
            for reason in attention_reasons
            if reason in recovery_suggestion_map
        )
    )

    payload = {
        "timestamp_ist": latest_timestamp(
            heartbeat,
            runtime_status,
            scanner_status,
            master_brain_status,
            paper_engine_status,
            live_price_monitor_status,
            daemon_health,
        ),
        "heartbeat": heartbeat or {},
        "daemon_health": daemon_health or {},
        "runtime_status": runtime_status or {},
        "scanner_status": scanner_status or {},
        "final_validated_setups": final_validated_setups or {},
        "setup_engine_status": setup_engine_status or {},
        "live_price_monitor_status": live_price_monitor_status or {},
        "master_brain_status": master_brain_status or {},
        "paper_engine_status": paper_engine_status or {},
        "news_pulse_status": news_pulse_status or {},
        "news_intelligence_status": news_intelligence_status or {},
        "runtime_resilience_status": resilience_status or {},
        "pyramid_governance_status": governance_status or {},
        "weekend_research_mode_status": weekend_research_status or {},
        "autonomous_runtime_summary": {
            "daemon_alive": runtime_health_checks["daemon_alive"][0],
            "runtime_status_fresh": runtime_health_checks["runtime_status_fresh"][0],
            "scanner_active": runtime_health_checks["scanner_active"][0],
            "master_brain_active": runtime_health_checks["master_brain_active"][0],
            "paper_engine_active": runtime_health_checks["paper_engine_active"][0],
            "live_price_monitor_active": runtime_health_checks["live_price_monitor_active"][0],
            "news_engine_active": runtime_health_checks["news_engine_active"][0],
            "needs_attention": bool(attention_reasons) and not defensive_runtime_healthy,
            "attention_reasons": attention_reasons,
            "reason": (
                "Weekend / research standby"
                if standby_runtime_healthy
                else (", ".join(attention_reasons) if attention_reasons else "Runtime attention checks clear")
            ),
            "recovery_suggestions": recovery_suggestions,
            "open_paper_positions": open_paper_positions,
            "paper_equity": paper_equity,
            "runtime_mode": runtime_mode,
            "market_workers_allowed_idle": market_workers_allowed_idle,
            "paper_engine_status_recommendation": (
                "STANDBY" if runtime_mode == "WEEKEND_MODE" and no_open_paper_positions else (
                    "IDLE_RESEARCH_MODE" if market_workers_allowed_idle and no_open_paper_positions else "ACTIVE"
                )
            ),
            "dashboard_status_recommendation": (
                runtime_mode
                if market_workers_allowed_idle
                else (
                    "HEALTHY"
                    if no_block_reasons and worker_degraded_count == 0 and stale_packet_count == 0
                    else runtime_mode
                )
            ),
            "governance_decision": governance_decision,
            "block_reasons": block_reasons or [],
            "worker_degraded_count": worker_degraded_count,
            "stale_packet_count": stale_packet_count,
            "auxiliary_research_workers_status": "AUXILIARY_WARNING_OR_STANDBY_ALLOWED"
            if market_workers_allowed_idle
            else "ACTIVE",
            "last_runtime_update": latest_timestamp(
                scanner_status,
                master_brain_status,
                paper_engine_status,
                live_price_monitor_status,
                news_pulse_status,
                news_intelligence_status,
                daemon_health,
                heartbeat,
                runtime_status,
            ),
            "scanner_pipeline_health": (
                scanner_status.get("pipeline_health")
                if isinstance(scanner_status, dict) and isinstance(scanner_status.get("pipeline_health"), dict)
                else {}
            ),
            "scanner_fallback_reason": (
                scanner_status.get("fallback_reason") if isinstance(scanner_status, dict) else None
            ),
            "scanner_partial_stale_tolerated": bool(
                scanner_status.get("partial_stale_tolerated")
            ) if isinstance(scanner_status, dict) else False,
            "scanner_stale_symbol_ratio": (
                scanner_status.get("stale_symbol_ratio") if isinstance(scanner_status, dict) else None
            ),
            "scanner_final_passed": (
                scanner_final_passed
            ),
            "scanner_final_count_source": (
                scanner_final_count_source
            ),
            "scanner_dashboard_status_message": (
                scanner_status.get("dashboard_status_message") if isinstance(scanner_status, dict) else None
            ),
            "setup_engine_marker_only": bool(
                setup_engine_status.get("marker_only")
            ) if isinstance(setup_engine_status, dict) else False,
            "setup_engine_real_run": bool(
                setup_engine_status.get("real_setup_engine_called")
            ) if isinstance(setup_engine_status, dict) else False,
        }
    }

    sync_result = upsert_runtime_status_rows(runtime_payloads, payload)
    payload["supabase_sync"] = sync_result

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_dashboard_sync(), indent=2, sort_keys=True))
