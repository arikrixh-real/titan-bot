import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engines.time_filter import current_bot_mode
from runtime_safe_json import safe_atomic_write_json


RUNTIME_DIR = Path("data") / "runtime"
RUNTIME_RESILIENCE_STATUS_PATH = RUNTIME_DIR / "runtime_resilience_status.json"
WEEKEND_RESEARCH_MODE_STATUS_PATH = RUNTIME_DIR / "weekend_research_mode_status.json"
OFFICIAL_RUNTIME_PATH = "titan_daemon.py"
STALE_PACKET_SECONDS = 24 * 60 * 60
RUNTIME_FRESH_SECONDS = 15 * 60
RUNTIME_FRESH_SECONDS_BY_MODE = {
    "RESEARCH_MODE": 24 * 60 * 60,
    "WEEKEND_MODE": 72 * 60 * 60,
}
WORKER_STUCK_GRACE_SECONDS = 60
WORKER_RECENT_FINISH_GRACE_SECONDS = 180
IST = timezone(timedelta(hours=5, minutes=30))
NON_DEGRADED_WORKER_STATUSES = {
    "OK",
    "OK_LAST_GOOD",
    "OK_LAST_GOOD_OUTPUT",
    "OK_STALE_ACTIVE_MARKER",
    "OK_RECENT_FINISH",
    "SKIPPED_UNCHANGED",
    "SKIPPED_RECENT",
    "SKIPPED_LOCKED",
    "WAITING_FOR_MODE",
    "STANDBY",
    "STANDBY_ALLOWED_IDLE",
    "RECOVERED_LAST_GOOD",
    "AUXILIARY_WARNING",
    "SKIPPED_PLACEHOLDER",
    "MISSING_HANDLER",
    "STARTING",
}

DAEMON_HEALTH_PATH = RUNTIME_DIR / "daemon_health.json"
WORKER_HEALTH_PATH = RUNTIME_DIR / "worker_health.json"
PYRAMID_CHAIN_STATUS_PATH = RUNTIME_DIR / "pyramid_chain_status.json"
PYRAMID_GOVERNANCE_STATUS_PATH = RUNTIME_DIR / "pyramid_governance_status.json"
LOAD_CONTROL_STATUS_PATH = RUNTIME_DIR / "intelligence_load_control_status.json"
SELF_IMPROVEMENT_STATUS_PATH = RUNTIME_DIR / "self_improvement_status.json"
TREND_PIPELINE_DIAGNOSTICS_PATH = RUNTIME_DIR / "trend_pipeline_diagnostics.json"

CRITICAL_PACKET_PATHS = {
    RUNTIME_DIR / "daemon_health.json",
    RUNTIME_DIR / "worker_health.json",
    RUNTIME_DIR / "titan_heartbeat.json",
    RUNTIME_DIR / "titan_runtime_status.json",
    RUNTIME_DIR / "scanner_status.json",
    RUNTIME_DIR / "master_brain_status.json",
    RUNTIME_DIR / "ohlc_refresh_status.json",
    Path("data") / "runtime" / "pyramid_chain_status.json",
    Path("data") / "runtime" / "pyramid_governance_status.json",
    Path("data") / "execution_safety" / "latest_execution_safety_report.json",
    Path("data") / "report_vault" / "latest_aggregated_packet.json",
    Path("data") / "consciousness_core" / "consciousness_context.json",
}
ALWAYS_CRITICAL_PACKET_PATHS = {
    RUNTIME_DIR / "daemon_health.json",
    RUNTIME_DIR / "worker_health.json",
    RUNTIME_DIR / "titan_heartbeat.json",
    RUNTIME_DIR / "titan_runtime_status.json",
    Path("data") / "runtime" / "pyramid_governance_status.json",
    Path("data") / "execution_safety" / "latest_execution_safety_report.json",
}
RESEARCH_CRITICAL_PACKET_PATHS = {
    RUNTIME_DIR / "news_pulse_status.json",
    RUNTIME_DIR / "light_news_pulse_status.json",
    RUNTIME_DIR / "news_intelligence_status.json",
    Path("data") / "news_intelligence" / "latest_news_intelligence_2_report.json",
    Path("data") / "report_vault" / "latest_aggregated_packet.json",
    Path("data") / "consciousness_core" / "consciousness_context.json",
}
MARKET_ONLY_PACKET_PATHS = {
    RUNTIME_DIR / "scanner_status.json",
    RUNTIME_DIR / "master_brain_status.json",
    RUNTIME_DIR / "ohlc_refresh_status.json",
}
MARKET_ONLY_WORKERS = {
    "broker_health_check",
    "journal",
    "live_price_monitor",
    "market_pressure_check",
    "market_regime_update",
    "master_brain",
    "ohlc_refresh",
    "outcome_tracker",
    "paper_engine",
    "pnl_refresh",
    "scanner",
    "sector_strength",
    "setup_engine",
    "volatility_check",
}
RESEARCH_NEWS_WORKERS = {"news_pulse", "light_news_pulse", "news_intelligence"}
TASK_OUTPUT_PATHS = {
    "heartbeat": RUNTIME_DIR / "titan_heartbeat.json",
    "runtime_status": RUNTIME_DIR / "titan_runtime_status.json",
    "report_aggregator": Path("data") / "report_vault" / "latest_aggregated_packet.json",
    "consciousness_core": Path("data") / "consciousness_core" / "consciousness_context.json",
    "experience_memory": Path("data") / "consciousness_core" / "real_experience_memory.json",
    "historical_replay": RUNTIME_DIR / "historical_replay_status.json",
    "knowledge_vault_runner": Path("data") / "knowledge_vault" / "reports" / "knowledge_to_consciousness_packet.json",
    "scenario_simulation": Path("data") / "consciousness_core" / "real_scenario_simulation.json",
}
SUPPORT_WORKERS = {"heartbeat", "runtime_status", "dashboard_sync"}
AUXILIARY_RESEARCH_WORKERS = {
    "experience_memory",
    "historical_replay",
    "knowledge_vault_runner",
    "scenario_simulation",
}


def _runtime_mode():
    mode = current_bot_mode()
    return "RESEARCH_MODE" if mode == "INTELLIGENCE_MODE" else mode


def _runtime_fresh_seconds_for_mode(mode):
    return RUNTIME_FRESH_SECONDS_BY_MODE.get(str(mode or "").upper(), RUNTIME_FRESH_SECONDS)


def _critical_packet_paths_for_mode(mode):
    if mode == "MARKET_MODE":
        return sorted(CRITICAL_PACKET_PATHS | RESEARCH_CRITICAL_PACKET_PATHS, key=lambda item: str(item))
    return sorted(ALWAYS_CRITICAL_PACKET_PATHS | RESEARCH_CRITICAL_PACKET_PATHS, key=lambda item: str(item))


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def refresh_execution_safety_status():
    try:
        from engines.broker_execution_safety_system import write_latest_execution_safety_report

        return write_latest_execution_safety_report()
    except Exception as exc:
        return {"status": "ERROR", "error": str(exc)}


def _atomic_write_json(path, payload):
    return safe_atomic_write_json(path, payload)


def read_json_safe(path):
    try:
        path = Path(path)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {"status": "CORRUPT"}
    except Exception as exc:
        return {"status": "CORRUPT", "error": str(exc)}


def _file_age(path):
    path = Path(path)
    if not path.exists():
        return None, None
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - modified_at).total_seconds()), modified_at.isoformat()


def parse_runtime_timestamp(value, naive_tz=IST):
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        text = str(value).strip()
        if not text:
            return None
        try:
            numeric_value = float(text)
            if numeric_value > 10_000_000_000:
                numeric_value = numeric_value / 1000.0
            return datetime.fromtimestamp(numeric_value, tz=timezone.utc)
        except ValueError:
            pass
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=naive_tz)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _last_good_output_path(task):
    path = TASK_OUTPUT_PATHS.get(task) or RUNTIME_DIR / f"{task}_status.json"
    return str(path).replace("\\", "/") if path.exists() else None


def _worker_output_fresh(task, seconds=STALE_PACKET_SECONDS, runtime_mode=None):
    path = TASK_OUTPUT_PATHS.get(task) or RUNTIME_DIR / f"{task}_status.json"
    if task in SUPPORT_WORKERS:
        seconds = min(seconds, _runtime_fresh_seconds_for_mode(runtime_mode))
    return _fresh_packet(path, seconds)


def _fresh_ok_consciousness_context(seconds=STALE_PACKET_SECONDS):
    context_path = Path("data") / "consciousness_core" / "consciousness_context.json"
    payload = read_json_safe(context_path)
    status = str((payload or {}).get("status") or "").upper()
    return bool(payload) and _fresh_packet(context_path, seconds) and status in {"OK", "HEALTHY"}


def _process_exists(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _status_write_error_only(error_text):
    text = str(error_text or "").lower()
    if not text:
        return False
    markers = (
        "access is denied",
        "permissionerror",
        "permission denied",
        ".tmp",
        "temp",
        "os.replace",
        "intelligence_load_control_status.json",
        "runtime_mode_status.json",
        "status.json",
    )
    return any(marker in text for marker in markers)


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_worker_health_summary(worker_health=None, runtime_mode=None):
    worker_health = worker_health if isinstance(worker_health, dict) else read_json_safe(WORKER_HEALTH_PATH)
    worker_health = worker_health if isinstance(worker_health, dict) else {}
    runtime_mode = runtime_mode or _runtime_mode()
    outside_market = runtime_mode in {"RESEARCH_MODE", "WEEKEND_MODE"}
    now = datetime.now(timezone.utc)
    workers = {}
    degraded_components = []
    last_good_outputs_used = []
    recovery_actions = []

    for task, item in sorted(worker_health.items()):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "UNKNOWN").upper()
        active_started_at = parse_runtime_timestamp(item.get("active_run_started_at") or item.get("last_started_at"))
        last_finished_at = parse_runtime_timestamp(item.get("last_finished_at"))
        timeout_seconds = int(item.get("active_timeout_seconds") or item.get("last_timeout_seconds") or 0)
        active_pid = item.get("active_pid")
        stuck = False
        active_age_seconds = None
        recent_finish_age_seconds = None
        recent_finish_grace_active = False
        stale_active_marker_ignored = False
        last_status = str(item.get("last_status") or "").upper()
        last_error = item.get("last_error")
        if last_finished_at is not None:
            recent_finish_age_seconds = max(0.0, (now - last_finished_at).total_seconds())
            recent_finish_grace_active = recent_finish_age_seconds <= WORKER_RECENT_FINISH_GRACE_SECONDS
        if status == "RUNNING" and active_started_at is not None and timeout_seconds > 0:
            active_age_seconds = max(0.0, (now - active_started_at).total_seconds())
            stuck = active_age_seconds > timeout_seconds + WORKER_STUCK_GRACE_SECONDS

        effective_status = "DEGRADED" if stuck else status
        allowed_idle_market_worker = outside_market and task in MARKET_ONLY_WORKERS
        runtime_fresh_seconds = _runtime_fresh_seconds_for_mode(runtime_mode)
        output_fresh = _worker_output_fresh(task, runtime_mode=runtime_mode)
        daemon_fresh = _fresh_packet(DAEMON_HEALTH_PATH, runtime_fresh_seconds) or _fresh_packet(
            RUNTIME_DIR / "titan_heartbeat.json",
            runtime_fresh_seconds,
        )
        active_pid_exists = _process_exists(active_pid)
        false_degraded_grace = False
        stale_active_marker_conditions = (
            status == "RUNNING"
            and stuck
            and daemon_fresh
            and output_fresh
            and (active_pid is None or not active_pid_exists)
        )
        if allowed_idle_market_worker and status in {
            "DEGRADED",
            "TIMEOUT",
            "ERROR",
            "WAITING_FOR_MODE",
            "STALE",
            "RUNNING",
        }:
            effective_status = "STANDBY_ALLOWED_IDLE"
            stuck = False
            stale_active_marker_ignored = True
        elif stale_active_marker_conditions:
            effective_status = "OK_STALE_ACTIVE_MARKER"
            stuck = False
            stale_active_marker_ignored = True
        elif (
            status == "RUNNING"
            and stuck
            and recent_finish_grace_active
            and last_finished_at is not None
            and active_started_at is not None
            and last_finished_at >= active_started_at
        ):
            effective_status = "OK_RECENT_FINISH"
            stuck = False
            stale_active_marker_ignored = True
        if (
            status == "DEGRADED"
            and recent_finish_grace_active
            and last_status in NON_DEGRADED_WORKER_STATUSES
            and (active_started_at is None or last_finished_at is None or last_finished_at >= active_started_at)
        ):
            effective_status = last_status or "RECENT_FINISH_GRACE"
            false_degraded_grace = True
        elif status in NON_DEGRADED_WORKER_STATUSES and not stuck:
            effective_status = status
        last_good_output_path = item.get("last_good_output_path") or _last_good_output_path(task)
        last_good_output_fresh = bool(last_good_output_path) and _fresh_packet(last_good_output_path)
        auxiliary_research_worker = task in AUXILIARY_RESEARCH_WORKERS
        last_good_output_used = bool(item.get("last_good_output_used")) or (
            effective_status in {"DEGRADED", "TIMEOUT", "ERROR"} and bool(last_good_output_path)
        )
        consciousness_last_good_recovered = False
        if (
            task == "consciousness_core"
            and status == "DEGRADED"
            and _safe_int(item.get("last_exitcode")) == -9
            and _fresh_ok_consciousness_context()
            and daemon_fresh
        ):
            effective_status = "OK_LAST_GOOD_OUTPUT"
            stuck = False
            false_degraded_grace = True
            last_error = None
            last_good_output_used = True
            consciousness_last_good_recovered = True
        if (
            auxiliary_research_worker
            and outside_market
            and effective_status in {"DEGRADED", "TIMEOUT", "ERROR"}
            and (_status_write_error_only(last_error) or last_good_output_path)
        ):
            effective_status = "RECOVERED_LAST_GOOD" if last_good_output_path else "AUXILIARY_WARNING"
            stuck = False
            last_good_output_used = bool(last_good_output_path)
        elif (
            auxiliary_research_worker
            and outside_market
            and status in {"SKIPPED_RECENT", "SKIPPED_UNCHANGED", "WAITING_FOR_MODE"}
        ):
            effective_status = status

        workers[task] = {
            "status": effective_status,
            "raw_status": status,
            "runtime_mode": runtime_mode,
            "market_worker_allowed_idle": allowed_idle_market_worker,
            "stuck": stuck,
            "active_age_seconds": None if active_age_seconds is None else round(active_age_seconds, 3),
            "recent_finish_age_seconds": (
                None if recent_finish_age_seconds is None else round(recent_finish_age_seconds, 3)
            ),
            "recent_finish_grace_active": recent_finish_grace_active,
            "stale_active_marker_ignored": stale_active_marker_ignored,
            "output_fresh": output_fresh,
            "daemon_fresh": daemon_fresh,
            "active_pid": active_pid,
            "active_pid_exists": active_pid_exists,
            "false_degraded_grace_applied": false_degraded_grace,
            "stuck_threshold_seconds": (
                timeout_seconds + WORKER_STUCK_GRACE_SECONDS
                if timeout_seconds
                else None
            ),
            "last_finished_at": item.get("last_finished_at"),
            "last_error": last_error,
            "raw_last_error": item.get("last_error") if consciousness_last_good_recovered else None,
            "retry_backoff_seconds": item.get("retry_backoff_seconds", 0),
            "last_good_output_path": last_good_output_path,
            "last_good_output_used": last_good_output_used,
            "last_good_output_fresh": last_good_output_fresh,
            "auxiliary_research_worker": auxiliary_research_worker,
            "consciousness_last_good_recovered": consciousness_last_good_recovered,
        }
        if effective_status in {"DEGRADED", "TIMEOUT", "ERROR"}:
            degraded_components.append(task)
        if last_good_output_used:
            last_good_outputs_used.append({"task": task, "path": last_good_output_path})
        if stuck:
            recovery_actions.append(
                {
                    "component": task,
                    "action": "marked_degraded_stuck_worker",
                    "last_good_output_path": last_good_output_path,
                }
            )

    return {
        "total_workers": len(workers),
        "degraded_count": len(set(degraded_components)),
        "degraded_components": sorted(set(degraded_components)),
        "workers": workers,
        "recovery_actions": recovery_actions,
        "last_good_outputs_used": last_good_outputs_used,
    }


def build_stale_packet_summary(paths=None, fresh_seconds=STALE_PACKET_SECONDS):
    paths = paths or sorted(CRITICAL_PACKET_PATHS, key=lambda item: str(item))
    packets = []
    stale_packets = []
    degraded_components = []
    for path in paths:
        path = Path(path)
        age_seconds, modified_at = _file_age(path)
        available = age_seconds is not None
        stale = (not available) or age_seconds > fresh_seconds
        status = "MISSING" if not available else ("STALE" if stale else "OK")
        item = {
            "path": str(path).replace("\\", "/"),
            "critical": path in CRITICAL_PACKET_PATHS,
            "available": available,
            "status": status,
            "age_seconds": None if age_seconds is None else round(age_seconds, 3),
            "modified_at_utc": modified_at,
            "fresh_seconds": fresh_seconds,
            "action": "marked_degraded_no_delete" if stale else "none",
        }
        packets.append(item)
        if stale:
            stale_packets.append(item)
            degraded_components.append(str(path).replace("\\", "/"))

    return {
        "total_packets_checked": len(packets),
        "stale_count": len(stale_packets),
        "stale_packets": stale_packets,
        "packets": packets,
        "degraded_components": degraded_components,
        "cleanup_policy": "mark_stale_or_degraded_only_no_deletes",
    }


def build_daemon_status(daemon_health=None):
    daemon_health = daemon_health if isinstance(daemon_health, dict) else read_json_safe(DAEMON_HEALTH_PATH)
    daemon_health = daemon_health if isinstance(daemon_health, dict) else {}
    status = str(daemon_health.get("status") or "UNKNOWN").upper()
    return {
        "status": status,
        "pid": daemon_health.get("pid"),
        "mode": daemon_health.get("mode"),
        "ticks_completed": daemon_health.get("ticks_completed"),
        "last_dispatch_count": daemon_health.get("last_dispatch_count"),
        "timestamp_ist": daemon_health.get("timestamp_ist"),
        "official_runtime_path": OFFICIAL_RUNTIME_PATH,
        "duplicate_prevention": daemon_health.get("duplicate_prevention") or "runtime_lock:titan_daemon",
        "shutdown_marker": daemon_health.get("shutdown_marker"),
        "restart_marker": daemon_health.get("restart_marker"),
    }


def build_runtime_resilience_status():
    refresh_execution_safety_status()
    runtime_mode = _runtime_mode()
    daemon_status = build_daemon_status()
    worker_summary = build_worker_health_summary(runtime_mode=runtime_mode)
    stale_summary = build_stale_packet_summary(_critical_packet_paths_for_mode(runtime_mode))
    always_fresh_failures = []
    runtime_fresh_seconds = _runtime_fresh_seconds_for_mode(runtime_mode)
    daemon_or_heartbeat_fresh = _fresh_packet(RUNTIME_DIR / "daemon_health.json", runtime_fresh_seconds) or _fresh_packet(
        RUNTIME_DIR / "titan_heartbeat.json",
        runtime_fresh_seconds,
    )
    for path in (
        RUNTIME_DIR / "daemon_health.json",
        RUNTIME_DIR / "titan_heartbeat.json",
        RUNTIME_DIR / "titan_runtime_status.json",
    ):
        if path == RUNTIME_DIR / "daemon_health.json" and daemon_or_heartbeat_fresh:
            continue
        if not _fresh_packet(path, runtime_fresh_seconds):
            always_fresh_failures.append(str(path).replace("\\", "/"))
    degraded_components = sorted(
        set(worker_summary["degraded_components"])
        | set(stale_summary["degraded_components"])
        | set(always_fresh_failures)
    )
    recovery_actions = []
    recovery_actions.extend(worker_summary["recovery_actions"])
    recovery_actions.extend(
        {
            "component": packet["path"],
            "action": packet["action"],
            "status": packet["status"],
        }
        for packet in stale_summary["stale_packets"]
    )
    recovery_actions.extend(
        {
            "component": path,
            "action": "marked_degraded_always_fresh_packet_stale",
            "status": "STALE",
        }
        for path in always_fresh_failures
    )

    governance_status = read_json_safe(PYRAMID_GOVERNANCE_STATUS_PATH)
    self_improvement_status = read_json_safe(SELF_IMPROVEMENT_STATUS_PATH)
    trend_diagnostics = read_json_safe(TREND_PIPELINE_DIAGNOSTICS_PATH)

    dashboard_ready_status = {
        "governance_decision": (
            (governance_status or {}).get("governance", {}).get("decision")
            if isinstance((governance_status or {}).get("governance"), dict)
            else (governance_status or {}).get("governance_decision")
        ),
        "resilience_health": {
            "status": "DEGRADED" if degraded_components else "OK",
            "official_runtime_path": OFFICIAL_RUNTIME_PATH,
            "degraded_component_count": len(degraded_components),
        },
        "proposal_counts": {
            "proposal_count": (self_improvement_status or {}).get("proposal_count"),
            "paper_test_count": (self_improvement_status or {}).get("paper_test_count"),
            "blocked_count": (self_improvement_status or {}).get("blocked_count"),
            "promoted_count": (self_improvement_status or {}).get("promoted_count"),
            "live_apply_allowed": False,
        },
        "degraded_workers": worker_summary["degraded_components"],
        "stale_packets": [
            packet.get("path")
            for packet in stale_summary["stale_packets"]
        ],
        "trend_diagnostics_summary": {
            "symbols_checked": (trend_diagnostics or {}).get("symbols_checked"),
            "dominant_failure_reason": (trend_diagnostics or {}).get("dominant_failure_reason"),
            "trend_confidence_summary": (trend_diagnostics or {}).get("trend_confidence_summary"),
            "updated_at_ist": (trend_diagnostics or {}).get("updated_at_ist"),
        },
    }

    payload = {
        "generated_at": utc_now_iso(),
        "runtime_mode": runtime_mode,
        "status": "DEGRADED" if degraded_components else "OK",
        "official_runtime_path": OFFICIAL_RUNTIME_PATH,
        "daemon": daemon_status,
        "worker_health_summary": worker_summary,
        "stale_packet_summary": stale_summary,
        "always_fresh_failures": always_fresh_failures,
        "dashboard_ready_status": dashboard_ready_status,
        "recovery_actions_taken": recovery_actions,
        "degraded_components": degraded_components,
        "last_good_outputs_used": worker_summary["last_good_outputs_used"],
        "safety_scope": {
            "advisory_only": True,
            "broker_orders": False,
            "telegram_changes": False,
            "scoring_mutation": False,
            "strategy_weight_mutation": False,
            "live_memory_mixed_with_external_simulated_memory": False,
        },
    }
    write_weekend_research_mode_status(payload)
    return payload


def _fresh_packet(path, seconds=STALE_PACKET_SECONDS):
    age_seconds, _modified_at = _file_age(path)
    return age_seconds is not None and age_seconds <= seconds


def _open_paper_positions_count():
    registry = read_json_safe(RUNTIME_DIR / "paper_trade_registry.json")
    positions = registry.get("open_positions") if isinstance(registry, dict) else []
    return len(positions) if isinstance(positions, list) else 0


def write_weekend_research_mode_status(resilience_status=None, path=WEEKEND_RESEARCH_MODE_STATUS_PATH):
    resilience_status = resilience_status if isinstance(resilience_status, dict) else {}
    runtime_mode = resilience_status.get("runtime_mode") or _runtime_mode()
    governance_status = read_json_safe(PYRAMID_GOVERNANCE_STATUS_PATH) or {}
    governance = governance_status.get("governance") if isinstance(governance_status.get("governance"), dict) else {}
    governance_decision = governance.get("decision") or governance_status.get("governance_decision")
    open_paper_positions = _open_paper_positions_count()
    market_workers_allowed_idle = runtime_mode in {"RESEARCH_MODE", "WEEKEND_MODE"}
    paper_engine_status = "ACTIVE"
    if market_workers_allowed_idle and open_paper_positions == 0:
        paper_engine_status = "IDLE_RESEARCH_MODE" if runtime_mode == "RESEARCH_MODE" else "STANDBY"

    errors_remaining = list(resilience_status.get("degraded_components") or [])
    payload = {
        "generated_at": utc_now_iso(),
        "runtime_mode": runtime_mode,
        "daemon_heartbeat_fresh": _fresh_packet(
            RUNTIME_DIR / "daemon_health.json",
            _runtime_fresh_seconds_for_mode(runtime_mode),
        )
        or _fresh_packet(
            RUNTIME_DIR / "titan_heartbeat.json",
            _runtime_fresh_seconds_for_mode(runtime_mode),
        ),
        "news_engine_fresh": _fresh_packet(RUNTIME_DIR / "news_pulse_status.json")
        or _fresh_packet(RUNTIME_DIR / "news_intelligence_status.json"),
        "market_workers_allowed_idle": market_workers_allowed_idle,
        "paper_engine_status": paper_engine_status,
        "dashboard_status_recommendation": (
            "WEEKEND_MODE" if runtime_mode == "WEEKEND_MODE" else (
                "RESEARCH_MODE" if runtime_mode == "RESEARCH_MODE" else "MARKET_MODE"
            )
        ),
        "telegram_status_reason": "Outside alert window; WAITING is normal and no Telegram alert is sent.",
        "governance_decision": governance_decision,
        "errors_remaining": errors_remaining,
    }
    _atomic_write_json(path, payload)
    return payload


def write_runtime_resilience_status(path=RUNTIME_RESILIENCE_STATUS_PATH):
    payload = build_runtime_resilience_status()
    _atomic_write_json(path, payload)
    return payload


def update_existing_status_outputs(resilience_status=None):
    resilience_status = resilience_status if isinstance(resilience_status, dict) else write_runtime_resilience_status()
    dashboard_ready_status = resilience_status.get("dashboard_ready_status") or {}
    marker = {
        "official_runtime_path": OFFICIAL_RUNTIME_PATH,
        "runtime_resilience_status": {
            "status": resilience_status.get("status"),
            "degraded_components": resilience_status.get("degraded_components", []),
            "stale_packet_count": resilience_status.get("stale_packet_summary", {}).get("stale_count"),
            "worker_degraded_count": resilience_status.get("worker_health_summary", {}).get("degraded_count"),
            "last_good_outputs_used": resilience_status.get("last_good_outputs_used", []),
        },
        "dashboard_ready_status": dashboard_ready_status,
    }
    for path in (
        PYRAMID_CHAIN_STATUS_PATH,
        PYRAMID_GOVERNANCE_STATUS_PATH,
        LOAD_CONTROL_STATUS_PATH,
    ):
        payload = read_json_safe(path)
        if not isinstance(payload, dict):
            continue
        payload.update(marker)
        _atomic_write_json(path, payload)
    return marker


if __name__ == "__main__":
    status = write_runtime_resilience_status()
    update_existing_status_outputs(status)
    print(json.dumps(status, indent=2, sort_keys=True))
