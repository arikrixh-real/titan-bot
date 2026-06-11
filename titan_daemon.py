import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime_lock import acquire_lock, refresh_lock, release_lock
from runtime_dispatcher import preview_dispatch
from runtime_scheduler_map import get_scheduler_map
from runtime_health import write_daemon_health
from runtime_error_log import log_runtime_error
from engines.phase38_test_mode_guard import evaluate_phase38_runtime_guard, write_phase38_runtime_status
from runtime_resilience_status import (
    OFFICIAL_RUNTIME_PATH,
    update_existing_status_outputs,
    write_runtime_resilience_status,
)
from runtime_safe_json import safe_atomic_write_json
from utils.market_hours import IST, as_ist_datetime, is_trade_window


LOCK_NAME = "titan_daemon"
PRINT_INTERVAL_SECONDS = 30
TICK_SECONDS = 1
DAEMON_HEALTH_PATH = Path("data") / "runtime" / "daemon_health.json"
SCANNER_SCHEDULER_STATUS_PATH = Path("data") / "runtime" / "scanner_scheduler_status.json"
RUNTIME_MODE_ENV = "TITAN_RUNTIME_MASTER_BRAIN_MODE"
CONTINUOUS_WORKERS_ENV = "TITAN_CONTINUOUS_WORKERS"
SCANNER_SCHEDULER_ENABLED_ENV = "TITAN_SCANNER_SCHEDULER_ENABLED"
DAEMON_PROOF_ONLY_ENV = "TITAN_DAEMON_PROOF_ONLY"
SCANNER_INVOCATION_INTERVAL_SECONDS = 300

SAFETY_FLAGS = {
    "advisory_only": True,
    "affects_live_ranking": False,
    "affects_execution": False,
    "broker_mutation": False,
    "telegram_mutation": False,
    "supabase_mutation": False,
    "live_order_behavior": False,
    "recommended_live_weight": 0.0,
    "rank_adjustment": 0.0,
}


def _now_ist():
    return datetime.now(IST)


def _parse_timestamp(value):
    if value in (None, ""):
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed.astimezone(IST)
    except Exception:
        return None


def _read_json_safe(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_scanner_scheduler_status(path=SCANNER_SCHEDULER_STATUS_PATH, **updates):
    now_ist = as_ist_datetime(updates.pop("now", None))
    previous = _read_json_safe(path)
    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "scheduler_active": bool(updates.get("scheduler_active", previous.get("scheduler_active", False))),
        "scanner_invocation_enabled": bool(updates.get("scanner_invocation_enabled", previous.get("scanner_invocation_enabled", False))),
        "last_scanner_invocation": updates.get("last_scanner_invocation", previous.get("last_scanner_invocation")),
        "last_scanner_success": updates.get("last_scanner_success", previous.get("last_scanner_success")),
        "last_scanner_exception": updates.get("last_scanner_exception", previous.get("last_scanner_exception")),
        "invocation_count": int(updates.get("invocation_count", previous.get("invocation_count", 0) or 0)),
        "failed_invocation_count": int(updates.get("failed_invocation_count", previous.get("failed_invocation_count", 0) or 0)),
        "next_expected_invocation": updates.get("next_expected_invocation", previous.get("next_expected_invocation")),
        "scheduler_mode": updates.get("scheduler_mode", previous.get("scheduler_mode", "UNKNOWN")),
        "trade_window": bool(updates.get("trade_window", previous.get("trade_window", False))),
        "research_mode": bool(updates.get("research_mode", previous.get("research_mode", False))),
        "last_skip_reason": updates.get("last_skip_reason", previous.get("last_skip_reason")),
        "safety_flags": dict(SAFETY_FLAGS),
    }
    safe_atomic_write_json(path, payload)
    return payload


def _scanner_scheduler_enabled():
    return str(os.getenv(SCANNER_SCHEDULER_ENABLED_ENV, "1")).strip() not in {"0", "false", "False", "NO", "no"}


def _daemon_proof_only_enabled():
    return str(os.getenv(DAEMON_PROOF_ONLY_ENV, "")).strip() in {"1", "true", "True", "YES", "yes"}


def _next_expected_from(now_ist):
    return (now_ist + timedelta(seconds=SCANNER_INVOCATION_INTERVAL_SECONDS)).isoformat()


def run_scanner_scheduler_tick(
    *,
    now=None,
    scanner_runner=None,
    status_path=SCANNER_SCHEDULER_STATUS_PATH,
    scheduler_mode="DAEMON_LOOP",
    force=False,
):
    now_ist = as_ist_datetime(now)
    trade_window = is_trade_window(now_ist)
    research_mode = not trade_window
    enabled = _scanner_scheduler_enabled()
    previous = _read_json_safe(status_path)
    invocation_count = int(previous.get("invocation_count") or 0)
    failed_count = int(previous.get("failed_invocation_count") or 0)
    last_success_dt = _parse_timestamp(previous.get("last_scanner_success"))

    base = {
        "now": now_ist,
        "scheduler_active": True,
        "scanner_invocation_enabled": enabled,
        "scheduler_mode": scheduler_mode,
        "trade_window": trade_window,
        "research_mode": research_mode,
    }

    if not enabled:
        return _write_scanner_scheduler_status(
            status_path,
            **base,
            last_scanner_exception=None,
            last_skip_reason="scanner_scheduler_disabled_by_env",
            next_expected_invocation=_next_expected_from(now_ist),
        )

    if not trade_window and not force:
        return _write_scanner_scheduler_status(
            status_path,
            **base,
            last_scanner_exception=None,
            last_skip_reason="outside_trade_window_standby",
            next_expected_invocation=_next_expected_from(now_ist),
        )

    due = force or last_success_dt is None or (now_ist - last_success_dt).total_seconds() >= SCANNER_INVOCATION_INTERVAL_SECONDS
    if not due:
        return _write_scanner_scheduler_status(
            status_path,
            **base,
            last_scanner_exception=None,
            last_skip_reason="cadence_wait",
            next_expected_invocation=(last_success_dt + timedelta(seconds=SCANNER_INVOCATION_INTERVAL_SECONDS)).isoformat(),
        )

    invocation_time = now_ist.isoformat()
    invocation_count += 1
    lock_name = "task_scanner"
    lock_acquired = acquire_lock(lock_name, stale_after_seconds=420)
    if not lock_acquired:
        return _write_scanner_scheduler_status(
            status_path,
            **base,
            last_scanner_invocation=invocation_time,
            invocation_count=invocation_count,
            failed_invocation_count=failed_count,
            last_scanner_exception=None,
            last_skip_reason="scanner_task_lock_active",
            next_expected_invocation=_next_expected_from(now_ist),
        )
    _write_scanner_scheduler_status(
        status_path,
        **base,
        last_scanner_invocation=invocation_time,
        invocation_count=invocation_count,
        failed_invocation_count=failed_count,
        last_scanner_exception=None,
        last_skip_reason=None,
        next_expected_invocation=_next_expected_from(now_ist),
    )
    try:
        if scanner_runner is None:
            from runtime_scanner import run_scanner

            scanner_runner = run_scanner
        scanner_runner()
    except Exception as exc:
        failed_count += 1
        log_runtime_error(source="titan_daemon_scanner_scheduler", error=exc, mode=scheduler_mode)
        return _write_scanner_scheduler_status(
            status_path,
            **base,
            last_scanner_invocation=invocation_time,
            invocation_count=invocation_count,
            failed_invocation_count=failed_count,
            last_scanner_exception=f"{type(exc).__name__}:{exc}",
            last_skip_reason=None,
            next_expected_invocation=_next_expected_from(now_ist),
        )
    finally:
        release_lock(lock_name)

    return _write_scanner_scheduler_status(
        status_path,
        **base,
        last_scanner_invocation=invocation_time,
        last_scanner_success=as_ist_datetime(None).isoformat(),
        invocation_count=invocation_count,
        failed_invocation_count=failed_count,
        last_scanner_exception=None,
        last_skip_reason=None,
        next_expected_invocation=_next_expected_from(now_ist),
    )


def _runtime_intent():
    runtime_mode = str(os.getenv(RUNTIME_MODE_ENV) or "READ_ONLY").strip().upper()

    if runtime_mode == "REAL":
        return {
            "runtime_mode": "REAL",
            "execution_owner": "VPS_REAL_SOLE_LIVE_OWNER",
            "execution_contract": (
                "VPS REAL mode is the sole live execution owner; Telegram and "
                "lifecycle mutation are enabled through the real master controller."
            ),
            "live_execution_enabled": True,
            "telegram_enabled": True,
            "lifecycle_mutation_enabled": True,
        }

    if runtime_mode in {"LIVE", "TEST", "RESEARCH_ONLY", "SHADOW", "PAPER"}:
        return {
            "runtime_mode": runtime_mode,
            "execution_owner": "NONE",
            "execution_contract": (
                f"{runtime_mode} mode is Phase 38 validated and fail-closed in "
                "the daemon path; no live execution, no Telegram, no journaling, "
                "no outcomes, no lifecycle mutation."
            ),
            "live_execution_enabled": False,
            "telegram_enabled": False,
            "lifecycle_mutation_enabled": False,
        }

    if runtime_mode == "HEALTH":
        return {
            "runtime_mode": "HEALTH_ONLY",
            "execution_owner": "HEALTH_CHECK_ONLY",
            "execution_contract": (
                "Health check only; no live execution, no Telegram, "
                "no journaling, no outcomes, no lifecycle mutation."
            ),
            "live_execution_enabled": False,
            "telegram_enabled": False,
            "lifecycle_mutation_enabled": False,
        }

    return {
        "runtime_mode": "READ_ONLY",
        "execution_owner": "NONE",
        "execution_contract": (
            "Marker/observation mode only; no live execution, no Telegram, "
            "no journaling, no outcomes."
        ),
        "live_execution_enabled": False,
        "telegram_enabled": False,
        "lifecycle_mutation_enabled": False,
    }


def _write_daemon_health(
    *,
    mode,
    ticks_completed,
    dispatch_count,
    status="RUNNING",
    run_id=None,
    started_at_ist=None,
    shutdown_marker=None,
    restart_marker=None,
    duplicate_marker=None,
):
    payload = write_daemon_health(
        mode=mode,
        ticks_completed=ticks_completed,
        dispatch_count=dispatch_count,
        status=status,
    )
    payload.update(_runtime_intent())
    phase38_guard = evaluate_phase38_runtime_guard(payload)
    payload["phase38_runtime_guard"] = phase38_guard
    try:
        write_phase38_runtime_status(payload)
    except OSError:
        pass
    payload.update(
        {
            "official_runtime_path": OFFICIAL_RUNTIME_PATH,
            "duplicate_prevention": f"runtime_lock:{LOCK_NAME}",
            "run_id": run_id,
            "started_at_ist": started_at_ist,
            "shutdown_marker": shutdown_marker,
            "restart_marker": restart_marker,
            "duplicate_marker": duplicate_marker,
        }
    )
    DAEMON_HEALTH_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    try:
        resilience_status = write_runtime_resilience_status()
        update_existing_status_outputs(resilience_status)
    except Exception as exc:
        log_runtime_error(
            source="titan_daemon_resilience_status",
            error=exc,
            mode=mode,
        )
    return payload


def main():
    run_id = uuid.uuid4().hex
    started_at_ist = None
    if not acquire_lock(LOCK_NAME):
        try:
            resilience_status = write_runtime_resilience_status()
            update_existing_status_outputs(resilience_status)
        except Exception as exc:
            log_runtime_error(
                source="titan_daemon_duplicate_resilience_status",
                error=exc,
                mode="DUPLICATE_BLOCKED",
            )
        print("TITAN daemon already running. Exiting.")
        return

    intent = _runtime_intent()
    continuous_workers_enabled = os.getenv(CONTINUOUS_WORKERS_ENV) == "1"
    daemon_proof_only = _daemon_proof_only_enabled()
    started_at_ist = _write_daemon_health(
        mode="STARTING",
        ticks_completed=0,
        dispatch_count=0,
        status="STARTING",
        run_id=run_id,
        restart_marker="daemon_start_marker_written",
    ).get("timestamp_ist")
    print(
        "TITAN daemon starting "
        f"official_runtime_path={OFFICIAL_RUNTIME_PATH} "
        f"runtime_mode={intent['runtime_mode']} "
        f"execution_owner={intent['execution_owner']} "
        f"live_execution_enabled={intent['live_execution_enabled']} "
        f"telegram_enabled={intent['telegram_enabled']} "
        f"lifecycle_mutation_enabled={intent['lifecycle_mutation_enabled']} "
        f"continuous_workers_enabled={continuous_workers_enabled} "
        f"daemon_proof_only={daemon_proof_only}",
        flush=True,
    )
    print(f"TITAN daemon contract: {intent['execution_contract']}", flush=True)
    print(
        "SCHEDULER_MAP_MARKET_MODE="
        f"{json.dumps(get_scheduler_map('MARKET_MODE'), separators=(',', ':'), sort_keys=True)}",
        flush=True,
    )

    last_printed_at = 0.0
    ticks_completed = 0
    last_dispatch_count = 0
    latest_mode = "CONTINUOUS_WORKERS" if continuous_workers_enabled else "UNKNOWN"
    shutdown_written = False

    try:
        if continuous_workers_enabled and not daemon_proof_only:
            from runtime_continuous_workers import start_continuous_workers

            start_continuous_workers(intent=intent)

        while True:
            try:
                if daemon_proof_only:
                    from runtime_heartbeat import write_heartbeat

                    write_heartbeat()
                    ticks_completed += 1
                    latest_mode = "DAEMON_PROOF_IDLE"
                    last_dispatch_count = 0
                elif continuous_workers_enabled:
                    ticks_completed += 1
                    last_dispatch_count = 0
                else:
                    dispatch_result = preview_dispatch()
                    ticks_completed += 1
                    latest_mode = dispatch_result["mode"]
                    last_dispatch_count = len(dispatch_result["dispatch_preview"])

                if not daemon_proof_only:
                    run_scanner_scheduler_tick(
                        scheduler_mode=latest_mode,
                        force=False,
                    )
                _write_daemon_health(
                    mode=latest_mode,
                    ticks_completed=ticks_completed,
                    dispatch_count=last_dispatch_count,
                    status="RUNNING",
                    run_id=run_id,
                    started_at_ist=started_at_ist,
                )
                refresh_lock(LOCK_NAME)

                now = time.monotonic()
                if now - last_printed_at >= PRINT_INTERVAL_SECONDS:
                    print(
                        "TITAN daemon running "
                        f"mode={latest_mode} "
                        f"runtime_mode={intent['runtime_mode']} "
                        f"execution_owner={intent['execution_owner']} "
                        f"ticks_completed={ticks_completed} "
                        f"last_dispatch_count={last_dispatch_count} "
                        f"continuous_workers_enabled={continuous_workers_enabled}",
                        flush=True,
                    )
                    last_printed_at = now
            except Exception as exc:
                log_runtime_error(
                    source="titan_daemon_tick",
                    error=exc,
                    mode=latest_mode,
                )

            time.sleep(TICK_SECONDS)
    except KeyboardInterrupt:
        print("TITAN daemon stopped.")
        _write_daemon_health(
            mode=latest_mode,
            ticks_completed=ticks_completed,
            dispatch_count=last_dispatch_count,
            status="STOPPED",
            run_id=run_id,
            started_at_ist=started_at_ist,
            shutdown_marker="keyboard_interrupt_graceful_stop",
        )
        shutdown_written = True
    finally:
        if started_at_ist and not shutdown_written:
            _write_daemon_health(
                mode=latest_mode,
                ticks_completed=ticks_completed,
                dispatch_count=last_dispatch_count,
                status="STOPPING",
                run_id=run_id,
                started_at_ist=started_at_ist,
                shutdown_marker="daemon_lock_release_pending",
            )
        release_lock(LOCK_NAME)


if __name__ == "__main__":
    main()
