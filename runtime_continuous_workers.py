import json
import os
import inspect
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

from runtime_engine_registry import get_registered_handler
from runtime_error_log import log_runtime_error
from runtime_intelligence_state import (
    ensure_intelligence_state,
    save_intelligence_state,
    state_hash,
    state_path_for_task,
)
from runtime_lock import acquire_lock, release_lock
from runtime_load_control import HEAVY_TASK_RULES, record_task_result, should_skip_task
from runtime_mode_router import runtime_mode_snapshot, should_run_task
from runtime_timeout import run_with_timeout
from runtime_safe_json import safe_atomic_write_json


IST = timezone(timedelta(hours=5, minutes=30))
WORKER_HEALTH_PATH = Path("data") / "runtime" / "worker_health.json"
TASK_OUTPUT_PATHS = {
    "heartbeat": Path("data") / "runtime" / "titan_heartbeat.json",
    "runtime_status": Path("data") / "runtime" / "titan_runtime_status.json",
    "report_aggregator": Path("data") / "report_vault" / "latest_aggregated_packet.json",
    "consciousness_core": Path("data") / "consciousness_core" / "consciousness_context.json",
}
DEFAULT_TASK_TIMEOUT_SECONDS = 60
TASK_TIMEOUT_SECONDS = {
    "ohlc_refresh": 120,
    "setup_engine": 240,
    "master_brain": 600,
    "scanner": 300,
    "news_pulse": 45,
    "light_news_pulse": 45,
    "outcome_tracker": 45,
    "evolution_engine": 60,
    "consciousness_core": 900,
    "report_aggregator": 300,
    "knowledge_vault_runner": 120,
    "experience_vault_runner": 120,
}
TASK_TERMINATE_GRACE_SECONDS = {
    "master_brain": 60,
    "scanner": 45,
    "consciousness_core": 90,
    "report_aggregator": 45,
}
TASK_LOCK_STALE_SECONDS = {
    "master_brain": 720,
    "scanner": 420,
}
MAX_RETRY_BACKOFF_SECONDS = 300

HEAVY_WORKER_INTERVAL_SECONDS = {
    task: int(rule.get("min_interval_seconds") or 0)
    for task, rule in HEAVY_TASK_RULES.items()
}

WORKER_CADENCE_TIERS = {
    "fast_5_min": [
        "scanner",
        "live_price_monitor",
        "market_regime_update",
        "market_pressure_check",
        "setup_engine",
        "outcome_tracker",
    ],
    "medium_10_30_min": [
        "report_aggregator",
        "consciousness_core",
        "daily_review",
        "learning_engine",
        "experience_memory",
        "knowledge_vault_runner",
        "experience_vault_runner",
        "memory_compression",
    ],
    "heavy_hourly_off_market": [
        "backtesting",
        "evolution_engine",
        "scenario_simulation",
        "synthetic_simulation",
        "historical_replay",
        "replay_batch",
        "next_day_preparation",
        "weekly_report",
    ],
}

WORKER_TASKS = {
    "heartbeat": 1,
    "runtime_status": 1,
    "dashboard_sync": 60,
    "risk_watchdog": 60,
    "pnl_refresh": 60,
    "broker_health_check": 10,
    "volatility_check": 10,
    "news_pulse": 15,
    "news_intelligence": 15,
    "experience_memory": 1800,
    "daily_review": 1800,
    "runtime_snapshot_logger": 30,
    "sector_strength": 300,
    "learning_engine": 1800,
    "report_aggregator": HEAVY_WORKER_INTERVAL_SECONDS.get("report_aggregator", 900),
    "knowledge_vault_runner": 1800,
    "experience_vault_runner": 1800,
    "consciousness_core": HEAVY_WORKER_INTERVAL_SECONDS.get("consciousness_core", 1800),
    "scenario_simulation": 3600,
    "next_day_preparation": 3600,
    "replay_batch": 3600,
    "memory_compression": 1800,
    "synthetic_simulation": 3600,
    "historical_replay": 3600,
    "backtesting": HEAVY_WORKER_INTERVAL_SECONDS.get("backtesting", 7200),
    "evolution_engine": HEAVY_WORKER_INTERVAL_SECONDS.get("evolution_engine", 3600),
    "scanner": 300,
    "live_price_monitor": 300,
    "market_regime_update": 300,
    "market_pressure_check": 300,
    "setup_engine": 300,
    "outcome_tracker": 300,
    "master_brain": 240,
    "ohlc_refresh": 300,
    "journal": 180,
    "paper_engine": 240,
}

IMPORTANT_INTELLIGENCE_TASKS = {
    "master_brain",
    "evolution_engine",
    "learning_engine",
    "experience_memory",
    "memory_compression",
    "scenario_simulation",
    "daily_review",
    "replay_batch",
    "historical_replay",
    "backtesting",
    "synthetic_simulation",
    "next_day_preparation",
    "report_aggregator",
    "knowledge_vault_runner",
    "experience_vault_runner",
    "consciousness_core",
}
NON_DEGRADED_PRESERVE_STATUSES = {
    "OK",
    "OK_LAST_GOOD",
    "OK_LAST_GOOD_OUTPUT",
    "SKIPPED_UNCHANGED",
    "SKIPPED_RECENT",
    "SKIPPED_LOCKED",
    "WAITING_FOR_MODE",
}

_health_lock = threading.Lock()
_health = {}
_workers_started = False
_workers_started_lock = threading.Lock()


def _now_ist():
    return datetime.now(IST).isoformat()


def _task_timeout_seconds(task):
    return TASK_TIMEOUT_SECONDS.get(task, DEFAULT_TASK_TIMEOUT_SECONDS)


def _task_terminate_grace_seconds(task):
    return TASK_TERMINATE_GRACE_SECONDS.get(task, 5)


def _task_lock_stale_seconds(task):
    timeout_seconds = _task_timeout_seconds(task)
    terminate_grace_seconds = _task_terminate_grace_seconds(task)
    default_stale_seconds = max(300, timeout_seconds + terminate_grace_seconds + 60)
    return TASK_LOCK_STALE_SECONDS.get(task, default_stale_seconds)


def _atomic_write_json(path, payload):
    safe_atomic_write_json(path, payload)


def _write_worker_health(task, **updates):
    with _health_lock:
        current = _health.setdefault(
            task,
            {
                "task": task,
                "status": "STARTING",
                "last_started_at": None,
                "last_finished_at": None,
                "run_count": 0,
                "error_count": 0,
                "timeout_count": 0,
                "last_error": None,
                "last_duration_seconds": None,
                "last_timeout_seconds": None,
                "last_timeout_reason": None,
                "intelligence_state_path": (
                    str(state_path_for_task(task))
                    if task in IMPORTANT_INTELLIGENCE_TASKS
                    else None
                ),
                "intelligence_run_count": None,
                "last_status": "STARTING",
                "cadence_tier": _cadence_tier_for_task(task),
            },
        )
        current.update(updates)
        try:
            _atomic_write_json(WORKER_HEALTH_PATH, _health)
        except OSError:
            pass


def _is_placeholder_handler(handler):
    if handler is None:
        return True

    handler_name = getattr(handler, "__name__", "")
    handler_repr = repr(handler)
    return (
        "placeholder" in handler_name
        or "placeholder" in handler_repr
        or "<locals>" in handler_repr
    )


def _log_runtime_error(source, error, mode):
    try:
        log_runtime_error(source=source, error=error, mode=mode)
    except OSError:
        pass


def _last_good_output_path(task):
    path = TASK_OUTPUT_PATHS.get(task) or Path("data") / "runtime" / f"{task}_status.json"
    return str(path).replace("\\", "/") if path.exists() else None


def _read_json_safe(path):
    try:
        path = Path(path)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _fresh_file(path, seconds=24 * 60 * 60):
    try:
        path = Path(path)
        if not path.exists():
            return False
        age_seconds = time.time() - path.stat().st_mtime
        return 0 <= age_seconds <= seconds
    except OSError:
        return False


def _daemon_or_heartbeat_fresh(seconds=15 * 60):
    return _fresh_file(Path("data") / "runtime" / "daemon_health.json", seconds) or _fresh_file(
        Path("data") / "runtime" / "titan_heartbeat.json",
        seconds,
    )


def _fresh_ok_consciousness_context(seconds=24 * 60 * 60):
    context_path = Path("data") / "consciousness_core" / "consciousness_context.json"
    payload = _read_json_safe(context_path)
    status = str((payload or {}).get("status") or "").upper()
    return bool(payload) and _fresh_file(context_path, seconds) and status in {"OK", "HEALTHY"}


def _clear_active_marker(task, started_at=None):
    with _health_lock:
        current = _health.get(task)
        if not isinstance(current, dict):
            return
        if started_at is not None and current.get("active_run_started_at") not in (None, started_at):
            return

        current_status = str(current.get("status") or "").upper()
        last_status = str(current.get("last_status") or "").upper()
        final_status = current_status
        if current_status == "RUNNING":
            final_status = last_status if last_status and last_status != "RUNNING" else "OK"
            current["status"] = final_status
            current["last_status"] = final_status
        elif current_status:
            current["last_status"] = current_status

        current["active_run_started_at"] = None
        current["active_pid"] = None
        current["last_finished_at"] = _now_ist()
        current["last_good_output_path"] = current.get("last_good_output_path") or _last_good_output_path(task)
        if final_status != "RUNNING":
            current["last_timeout_seconds"] = None
        try:
            _atomic_write_json(WORKER_HEALTH_PATH, _health)
        except OSError:
            pass


def _retry_backoff_seconds(task):
    current = _health.get(task, {})
    consecutive_failures = int(current.get("consecutive_failure_count") or 0)
    if consecutive_failures <= 0:
        return 0
    return min(MAX_RETRY_BACKOFF_SECONDS, 2 ** min(consecutive_failures, 8))


def _record_error(task, error, mode):
    last_good_output_path = _health.get(task, {}).get("last_good_output_path") or _last_good_output_path(task)
    consecutive_failures = int(_health.get(task, {}).get("consecutive_failure_count") or 0) + 1
    _write_worker_health(
        task,
        status="DEGRADED",
        last_finished_at=_now_ist(),
        error_count=_health.get(task, {}).get("error_count", 0) + 1,
        consecutive_failure_count=consecutive_failures,
        retry_backoff_seconds=min(MAX_RETRY_BACKOFF_SECONDS, 2 ** min(consecutive_failures, 8)),
        last_error=str(error),
        last_good_output_path=last_good_output_path,
        last_good_output_used=bool(last_good_output_path),
        recovery_action="marked_degraded_preserved_last_good_output",
    )
    _log_runtime_error(
        source=f"continuous_worker_{task}",
        error=error,
        mode=mode,
    )


def _preserved_status_from_last_good(previous_health):
    previous_health = previous_health if isinstance(previous_health, dict) else {}
    for key in ("last_status", "status"):
        status = str(previous_health.get(key) or "").upper()
        if status in NON_DEGRADED_PRESERVE_STATUSES:
            return status
    return "OK"


def _intelligence_handler(handler, state, state_path):
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return handler

    supports_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    supported_names = set(signature.parameters)
    requested_kwargs = {
        "state": state,
        "state_path": str(state_path),
        "intelligence_state": state,
    }

    if supports_kwargs:
        handler_kwargs = requested_kwargs
    else:
        handler_kwargs = {
            name: value
            for name, value in requested_kwargs.items()
            if name in supported_names
        }

    if not handler_kwargs:
        return handler

    return partial(handler, **handler_kwargs)


def _run_worker(task, sleep_seconds, intent):
    mode = (intent or {}).get("runtime_mode", "UNKNOWN")

    _write_worker_health(task, status="STARTING")

    while True:
        lock_name = f"task_{task}"
        lock_acquired = False
        started_at = _now_ist()
        run_started_monotonic = time.monotonic()
        intelligence_state = None
        intelligence_state_path = None
        is_intelligence_task = task in IMPORTANT_INTELLIGENCE_TASKS

        try:
            mode_snapshot = runtime_mode_snapshot()
            current_runtime_mode = mode_snapshot["current_mode"]
            mode = current_runtime_mode

            if not should_run_task(task):
                _write_worker_health(
                    task,
                    status="WAITING_FOR_MODE",
                    last_finished_at=_now_ist(),
                    last_error=None,
                    runtime_mode=current_runtime_mode,
                    mode_allowed=False,
                    last_mode_skip_at=_now_ist(),
                )
                time.sleep(sleep_seconds)
                continue

            skip_task, load_decision = should_skip_task(task)
            if skip_task:
                status = (
                    "SKIPPED_UNCHANGED"
                    if load_decision.get("reason") == "input_signature_unchanged"
                    else "SKIPPED_RECENT"
                )
                if is_intelligence_task:
                    intelligence_state, intelligence_state_path = ensure_intelligence_state(task)
                    intelligence_state["last_status"] = status
                    intelligence_state["last_load_control_skip"] = load_decision
                    intelligence_state["last_input_hash"] = load_decision.get("input_hash")
                    intelligence_state, intelligence_state_path = save_intelligence_state(
                        task,
                        intelligence_state,
                        status,
                        0,
                    )
                _write_worker_health(
                    task,
                    status=status,
                    last_finished_at=_now_ist(),
                    last_error=None,
                    runtime_mode=current_runtime_mode,
                    mode_allowed=True,
                    load_control=load_decision,
                    intelligence_state_path=(
                        str(intelligence_state_path) if intelligence_state_path else None
                    ),
                    intelligence_run_count=(
                        intelligence_state.get("run_count")
                        if intelligence_state is not None
                        else None
                    ),
                    last_status=status,
                    retry_backoff_seconds=0,
                )
                time.sleep(sleep_seconds)
                continue

            previous_health = dict(_health.get(task, {}))
            _write_worker_health(
                task,
                status="RUNNING",
                last_started_at=started_at,
                active_run_started_at=started_at,
                active_pid=os.getpid(),
                active_timeout_seconds=_task_timeout_seconds(task),
                last_timeout_reason=None,
                last_error=None,
                runtime_mode=current_runtime_mode,
                mode_allowed=True,
                last_status="RUNNING",
            )

            handler = get_registered_handler(task)

            if is_intelligence_task:
                intelligence_state, intelligence_state_path = ensure_intelligence_state(task)
                intelligence_state["last_input_hash"] = state_hash(intelligence_state)
                _write_worker_health(
                    task,
                    intelligence_state_path=str(intelligence_state_path),
                    intelligence_run_count=intelligence_state.get("run_count", 0),
                    intelligence_last_status=intelligence_state.get("last_status"),
                    last_status="RUNNING",
                    retry_backoff_seconds=0,
                )

            if not handler:
                if intelligence_state is not None:
                    runtime_seconds = time.monotonic() - run_started_monotonic
                    intelligence_state, intelligence_state_path = save_intelligence_state(
                        task,
                        intelligence_state,
                        "MISSING_HANDLER",
                        runtime_seconds,
                        error=f"no registered handler for {task}",
                    )
                _write_worker_health(
                    task,
                    status="MISSING_HANDLER",
                    last_finished_at=_now_ist(),
                    last_error=f"no registered handler for {task}",
                    intelligence_state_path=(
                        str(intelligence_state_path) if intelligence_state_path else None
                    ),
                    intelligence_run_count=(
                        intelligence_state.get("run_count")
                        if intelligence_state is not None
                        else None
                    ),
                    last_status=(
                        intelligence_state.get("last_status")
                        if intelligence_state is not None
                        else "MISSING_HANDLER"
                    ),
                )
                time.sleep(sleep_seconds)
                continue

            if _is_placeholder_handler(handler):
                if intelligence_state is not None:
                    runtime_seconds = time.monotonic() - run_started_monotonic
                    intelligence_state, intelligence_state_path = save_intelligence_state(
                        task,
                        intelligence_state,
                        "SKIPPED_PLACEHOLDER",
                        runtime_seconds,
                    )
                _write_worker_health(
                    task,
                    status="SKIPPED_PLACEHOLDER",
                    last_finished_at=_now_ist(),
                    last_error=None,
                    intelligence_state_path=(
                        str(intelligence_state_path) if intelligence_state_path else None
                    ),
                    intelligence_run_count=(
                        intelligence_state.get("run_count")
                        if intelligence_state is not None
                        else None
                    ),
                    last_status=(
                        intelligence_state.get("last_status")
                        if intelligence_state is not None
                        else "SKIPPED_PLACEHOLDER"
                    ),
                )
                time.sleep(sleep_seconds)
                continue

            lock_acquired = acquire_lock(
                lock_name,
                stale_after_seconds=_task_lock_stale_seconds(task),
            )
            if not lock_acquired:
                _write_worker_health(
                    task,
                    status="SKIPPED_LOCKED",
                    last_finished_at=_now_ist(),
                    last_error=f"{task} previous run still active",
                    lock_stale_after_seconds=_task_lock_stale_seconds(task),
                )
                time.sleep(sleep_seconds)
                continue

            if intelligence_state is not None:
                handler = _intelligence_handler(
                    handler,
                    intelligence_state,
                    intelligence_state_path,
                )

            timeout_seconds = _task_timeout_seconds(task)
            result = run_with_timeout(
                handler,
                timeout_seconds,
                terminate_grace_seconds=_task_terminate_grace_seconds(task),
            )
            run_count = _health.get(task, {}).get("run_count", 0) + 1
            runtime_seconds = time.monotonic() - run_started_monotonic

            if result.get("status") == "timeout":
                if task == "consciousness_core":
                    try:
                        from consciousness_core.meta_orchestrator import mark_consciousness_degraded

                        mark_consciousness_degraded(
                            f"timeout after {result.get('timeout_seconds')} seconds",
                            state=intelligence_state,
                        )
                    except Exception as degraded_exc:
                        _log_runtime_error(
                            source="continuous_worker_consciousness_core_degraded_fallback",
                            error=degraded_exc,
                            mode=mode,
                        )
                record_task_result(
                    task,
                    "DEGRADED",
                    result=result,
                    runtime_seconds=runtime_seconds,
                    error=f"timeout after {result.get('timeout_seconds')} seconds",
                )
                if intelligence_state is not None:
                    intelligence_state, intelligence_state_path = save_intelligence_state(
                        task,
                        intelligence_state,
                        "DEGRADED",
                        runtime_seconds,
                        error=f"timeout after {result.get('timeout_seconds')} seconds",
                    )
                last_good_output_path = _health.get(task, {}).get("last_good_output_path") or _last_good_output_path(task)
                consecutive_failures = int(_health.get(task, {}).get("consecutive_failure_count") or 0) + 1
                _write_worker_health(
                    task,
                    status="DEGRADED",
                    last_finished_at=_now_ist(),
                    run_count=run_count,
                    last_duration_seconds=round(runtime_seconds, 3),
                    last_timeout_seconds=result.get("timeout_seconds"),
                    last_timeout_reason=result.get("termination_reason"),
                    last_exitcode=result.get("exitcode"),
                    timeout_count=_health.get(task, {}).get("timeout_count", 0) + 1,
                    consecutive_failure_count=consecutive_failures,
                    retry_backoff_seconds=min(MAX_RETRY_BACKOFF_SECONDS, 2 ** min(consecutive_failures, 8)),
                    last_error=(
                        f"timeout after {result.get('timeout_seconds')} seconds "
                        f"reason={result.get('termination_reason')}"
                    ),
                    last_good_output_path=last_good_output_path,
                    last_good_output_used=bool(last_good_output_path),
                    recovery_action="marked_degraded_timeout_preserved_last_good_output",
                    intelligence_state_path=(
                        str(intelligence_state_path) if intelligence_state_path else None
                    ),
                    intelligence_run_count=(
                        intelligence_state.get("run_count")
                        if intelligence_state is not None
                        else None
                    ),
                    last_status=(
                        intelligence_state.get("last_status")
                        if intelligence_state is not None
                        else "DEGRADED"
                    ),
                )
            elif result.get("status") == "ok":
                record_task_result(
                    task,
                    "OK",
                    result=result.get("result") if isinstance(result.get("result"), dict) else result,
                    runtime_seconds=runtime_seconds,
                )
                if intelligence_state is not None:
                    intelligence_state, intelligence_state_path = save_intelligence_state(
                        task,
                        intelligence_state,
                        "OK",
                        runtime_seconds,
                    )
                _write_worker_health(
                    task,
                    status="OK",
                    last_finished_at=_now_ist(),
                    run_count=run_count,
                    last_duration_seconds=round(runtime_seconds, 3),
                    last_timeout_seconds=None,
                    last_timeout_reason=None,
                    last_exitcode=result.get("exitcode"),
                    last_error=None,
                    consecutive_failure_count=0,
                    retry_backoff_seconds=0,
                    last_good_output_path=_last_good_output_path(task),
                    last_good_output_used=False,
                    recovery_action=None,
                    intelligence_state_path=(
                        str(intelligence_state_path) if intelligence_state_path else None
                    ),
                    intelligence_run_count=(
                        intelligence_state.get("run_count")
                        if intelligence_state is not None
                        else None
                    ),
                    last_status=(
                        intelligence_state.get("last_status")
                        if intelligence_state is not None
                        else "OK"
                    ),
                )
            else:
                error = RuntimeError(result.get("error") or f"{task} returned {result}")
                last_good_output_path = _health.get(task, {}).get("last_good_output_path") or _last_good_output_path(task)
                exitcode = result.get("exitcode")
                preserved_nonzero = False
                consciousness_recovered_last_good = (
                    task == "consciousness_core"
                    and exitcode == -9
                    and _fresh_ok_consciousness_context()
                    and _daemon_or_heartbeat_fresh()
                )
                if consciousness_recovered_last_good:
                    preserved_status = "OK_LAST_GOOD"
                    last_good_output_path = last_good_output_path or _last_good_output_path(task)
                    record_task_result(
                        task,
                        preserved_status,
                        result={
                            "status": preserved_status,
                            "exitcode": exitcode,
                            "last_good_output_path": last_good_output_path,
                            "recovery_action": "fresh_consciousness_context_after_exitcode_minus_9",
                        },
                        runtime_seconds=runtime_seconds,
                    )
                    if intelligence_state is not None:
                        intelligence_state, intelligence_state_path = save_intelligence_state(
                            task,
                            intelligence_state,
                            preserved_status,
                            runtime_seconds,
                        )
                    _write_worker_health(
                        task,
                        status=preserved_status,
                        last_finished_at=_now_ist(),
                        run_count=run_count,
                        last_duration_seconds=round(runtime_seconds, 3),
                        last_timeout_seconds=None,
                        last_timeout_reason=result.get("termination_reason"),
                        last_exitcode=exitcode,
                        last_error=None,
                        last_good_output_path=last_good_output_path,
                        last_good_output_used=True,
                        recovery_action="fresh_consciousness_context_after_exitcode_minus_9",
                        consecutive_failure_count=0,
                        retry_backoff_seconds=0,
                        intelligence_state_path=(
                            str(intelligence_state_path) if intelligence_state_path else None
                        ),
                        intelligence_run_count=(
                            intelligence_state.get("run_count")
                            if intelligence_state is not None
                            else None
                        ),
                        last_status=preserved_status,
                    )
                    preserved_nonzero = True
                elif exitcode not in (None, 0) and last_good_output_path:
                    preserved_status = _preserved_status_from_last_good(previous_health)
                    record_task_result(
                        task,
                        preserved_status,
                        result=result,
                        runtime_seconds=runtime_seconds,
                        error=error,
                    )
                    if intelligence_state is not None:
                        intelligence_state, intelligence_state_path = save_intelligence_state(
                            task,
                            intelligence_state,
                            preserved_status,
                            runtime_seconds,
                            error=f"nonzero exitcode={exitcode}; preserved last good output",
                        )
                    _write_worker_health(
                        task,
                        status=preserved_status,
                        last_finished_at=_now_ist(),
                        run_count=run_count,
                        last_duration_seconds=round(runtime_seconds, 3),
                        last_timeout_seconds=None,
                        last_timeout_reason=result.get("termination_reason"),
                        last_exitcode=exitcode,
                        last_error=f"nonzero exitcode={exitcode}; preserved last good output",
                        last_good_output_path=last_good_output_path,
                        last_good_output_used=True,
                        recovery_action="preserved_last_good_output_after_nonzero_exit",
                        consecutive_failure_count=0,
                        retry_backoff_seconds=0,
                        intelligence_state_path=(
                            str(intelligence_state_path) if intelligence_state_path else None
                        ),
                        intelligence_run_count=(
                            intelligence_state.get("run_count")
                            if intelligence_state is not None
                            else None
                        ),
                        last_status=preserved_status,
                    )
                    preserved_nonzero = True
                if preserved_nonzero:
                    continue
                record_task_result(
                    task,
                    "DEGRADED",
                    result=result,
                    runtime_seconds=runtime_seconds,
                    error=error,
                )
                if intelligence_state is not None:
                    intelligence_state, intelligence_state_path = save_intelligence_state(
                        task,
                        intelligence_state,
                        "DEGRADED",
                        runtime_seconds,
                        error=error,
                    )
                _write_worker_health(
                    task,
                    run_count=run_count,
                    last_duration_seconds=round(runtime_seconds, 3),
                    last_timeout_seconds=None,
                    last_timeout_reason=result.get("termination_reason"),
                    last_exitcode=result.get("exitcode"),
                    intelligence_state_path=(
                        str(intelligence_state_path) if intelligence_state_path else None
                    ),
                    intelligence_run_count=(
                        intelligence_state.get("run_count")
                        if intelligence_state is not None
                        else None
                    ),
                    last_status=(
                        intelligence_state.get("last_status")
                        if intelligence_state is not None
                        else "ERROR"
                    ),
                )
                _record_error(task, error, mode)
        except Exception as exc:
            if intelligence_state is not None:
                try:
                    runtime_seconds = time.monotonic() - run_started_monotonic
                    intelligence_state, intelligence_state_path = save_intelligence_state(
                        task,
                        intelligence_state,
                        "DEGRADED",
                        runtime_seconds,
                        error=exc,
                    )
                    _write_worker_health(
                        task,
                        intelligence_state_path=str(intelligence_state_path),
                        intelligence_run_count=intelligence_state.get("run_count"),
                        last_status=intelligence_state.get("last_status"),
                    )
                except Exception as state_exc:
                    print(
                        f"INTELLIGENCE_STATE_ERROR task={task} "
                        f"path={intelligence_state_path} error={state_exc}",
                        flush=True,
                    )
            _record_error(task, exc, mode)
        finally:
            if lock_acquired:
                try:
                    release_lock(lock_name)
                except Exception as exc:
                    _log_runtime_error(
                        source=f"continuous_worker_{task}_release_lock",
                        error=exc,
                        mode=mode,
                    )
            _clear_active_marker(task)

        backoff_seconds = _retry_backoff_seconds(task)
        if backoff_seconds:
            _write_worker_health(
                task,
                retry_backoff_seconds=backoff_seconds,
                recovery_action="retry_backoff_scheduled",
            )
        time.sleep(sleep_seconds + backoff_seconds)


def start_continuous_workers(intent=None):
    global _workers_started

    with _workers_started_lock:
        if _workers_started:
            return False

        for task, sleep_seconds in WORKER_TASKS.items():
            thread = threading.Thread(
                target=_run_worker,
                args=(task, sleep_seconds, intent),
                name=f"titan-worker-{task}",
                daemon=True,
            )
            thread.start()

        _workers_started = True

    print(
        f"continuous workers started count={len(WORKER_TASKS)}",
        flush=True,
    )
    return True


def _cadence_tier_for_task(task):
    for tier, tasks in WORKER_CADENCE_TIERS.items():
        if task in tasks:
            return tier
    return "runtime_support"
