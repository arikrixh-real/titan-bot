import json
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime_engine_registry import get_registered_handler
from runtime_error_log import log_runtime_error
from runtime_lock import acquire_lock, release_lock
from runtime_timeout import run_with_timeout


IST = timezone(timedelta(hours=5, minutes=30))
WORKER_HEALTH_PATH = Path("data") / "runtime" / "worker_health.json"
DEFAULT_TASK_TIMEOUT_SECONDS = 60
TASK_TIMEOUT_SECONDS = {
    "ohlc_refresh": 120,
    "setup_engine": 240,
    "master_brain": 240,
    "scanner": 120,
    "news_pulse": 45,
    "light_news_pulse": 45,
    "outcome_tracker": 45,
    "evolution_engine": 60,
}

WORKER_TASKS = {
    "heartbeat": 1,
    "runtime_status": 1,
    "dashboard_sync": 3,
    "live_price_monitor": 3,
    "risk_watchdog": 3,
    "pnl_refresh": 5,
    "outcome_tracker": 10,
    "broker_health_check": 10,
    "volatility_check": 10,
    "market_pressure_check": 10,
    "news_pulse": 15,
    "news_intelligence": 15,
    "experience_memory": 20,
    "daily_review": 30,
    "runtime_snapshot_logger": 30,
    "market_regime_update": 30,
    "sector_strength": 30,
    "learning_engine": 60,
    "scenario_simulation": 90,
    "next_day_preparation": 120,
    "replay_batch": 180,
    "memory_compression": 180,
    "synthetic_simulation": 180,
    "historical_replay": 180,
    "backtesting": 300,
    "evolution_engine": 300,
    "scanner": 180,
    "setup_engine": 240,
    "master_brain": 240,
    "ohlc_refresh": 300,
    "journal": 180,
    "paper_engine": 240,
}

_health_lock = threading.Lock()
_health = {}
_workers_started = False
_workers_started_lock = threading.Lock()


def _now_ist():
    return datetime.now(IST).isoformat()


def _task_timeout_seconds(task):
    return TASK_TIMEOUT_SECONDS.get(task, DEFAULT_TASK_TIMEOUT_SECONDS)


def _atomic_write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as temp_file:
            json.dump(payload, temp_file, indent=2, sort_keys=True)
            temp_file.write("\n")
            temp_path = Path(temp_file.name)

        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


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
            },
        )
        current.update(updates)
        try:
            _atomic_write_json(WORKER_HEALTH_PATH, _health)
        except OSError:
            pass


def _log_runtime_error(source, error, mode):
    try:
        log_runtime_error(source=source, error=error, mode=mode)
    except OSError:
        pass


def _record_error(task, error, mode):
    _write_worker_health(
        task,
        status="ERROR",
        last_finished_at=_now_ist(),
        error_count=_health.get(task, {}).get("error_count", 0) + 1,
        last_error=str(error),
    )
    _log_runtime_error(
        source=f"continuous_worker_{task}",
        error=error,
        mode=mode,
    )


def _run_worker(task, sleep_seconds, intent):
    mode = (intent or {}).get("runtime_mode", "UNKNOWN")

    _write_worker_health(task, status="STARTING")

    while True:
        lock_name = f"task_{task}"
        lock_acquired = False
        started_at = _now_ist()

        try:
            _write_worker_health(
                task,
                status="RUNNING",
                last_started_at=started_at,
                last_error=None,
            )

            handler = get_registered_handler(task)
            if not handler:
                _write_worker_health(
                    task,
                    status="MISSING_HANDLER",
                    last_finished_at=_now_ist(),
                    last_error=f"no registered handler for {task}",
                )
                time.sleep(sleep_seconds)
                continue

            lock_acquired = acquire_lock(lock_name)
            if not lock_acquired:
                _write_worker_health(
                    task,
                    status="SKIPPED_LOCKED",
                    last_finished_at=_now_ist(),
                )
                time.sleep(sleep_seconds)
                continue

            result = run_with_timeout(handler, _task_timeout_seconds(task))
            run_count = _health.get(task, {}).get("run_count", 0) + 1

            if result.get("status") == "timeout":
                _write_worker_health(
                    task,
                    status="TIMEOUT",
                    last_finished_at=_now_ist(),
                    run_count=run_count,
                    timeout_count=_health.get(task, {}).get("timeout_count", 0) + 1,
                    last_error=f"timeout after {result.get('timeout_seconds')} seconds",
                )
            elif result.get("status") == "ok":
                _write_worker_health(
                    task,
                    status="OK",
                    last_finished_at=_now_ist(),
                    run_count=run_count,
                    last_error=None,
                )
            else:
                error = RuntimeError(result.get("error") or f"{task} returned {result}")
                _write_worker_health(task, run_count=run_count)
                _record_error(task, error, mode)
        except Exception as exc:
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

        time.sleep(sleep_seconds)


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
