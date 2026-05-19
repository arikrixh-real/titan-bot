import json
import os
import time
from pathlib import Path

from runtime_lock import acquire_lock, refresh_lock, release_lock
from runtime_dispatcher import preview_dispatch
from runtime_scheduler_map import get_scheduler_map
from runtime_health import write_daemon_health
from runtime_error_log import log_runtime_error


LOCK_NAME = "titan_daemon"
PRINT_INTERVAL_SECONDS = 30
TICK_SECONDS = 1
DAEMON_HEALTH_PATH = Path("data") / "runtime" / "daemon_health.json"
RUNTIME_MODE_ENV = "TITAN_RUNTIME_MASTER_BRAIN_MODE"
CONTINUOUS_WORKERS_ENV = "TITAN_CONTINUOUS_WORKERS"


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
):
    payload = write_daemon_health(
        mode=mode,
        ticks_completed=ticks_completed,
        dispatch_count=dispatch_count,
        status=status,
    )
    payload.update(_runtime_intent())
    DAEMON_HEALTH_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload


def main():
    if not acquire_lock(LOCK_NAME):
        print("TITAN daemon already running. Exiting.")
        return

    intent = _runtime_intent()
    continuous_workers_enabled = os.getenv(CONTINUOUS_WORKERS_ENV) == "1"
    print(
        "TITAN daemon starting "
        f"runtime_mode={intent['runtime_mode']} "
        f"execution_owner={intent['execution_owner']} "
        f"live_execution_enabled={intent['live_execution_enabled']} "
        f"telegram_enabled={intent['telegram_enabled']} "
        f"lifecycle_mutation_enabled={intent['lifecycle_mutation_enabled']} "
        f"continuous_workers_enabled={continuous_workers_enabled}",
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

    try:
        if continuous_workers_enabled:
            from runtime_continuous_workers import start_continuous_workers

            start_continuous_workers(intent=intent)

        while True:
            try:
                if continuous_workers_enabled:
                    ticks_completed += 1
                    last_dispatch_count = 0
                else:
                    dispatch_result = preview_dispatch()
                    ticks_completed += 1
                    latest_mode = dispatch_result["mode"]
                    last_dispatch_count = len(dispatch_result["dispatch_preview"])

                _write_daemon_health(
                    mode=latest_mode,
                    ticks_completed=ticks_completed,
                    dispatch_count=last_dispatch_count,
                    status="RUNNING",
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
        )
    finally:
        release_lock(LOCK_NAME)


if __name__ == "__main__":
    main()
