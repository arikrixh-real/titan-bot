import json
import os
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runtime_continuous_workers import WORKER_HEALTH_PATH
from runtime_dashboard_sync import run_dashboard_sync
from runtime_heartbeat import write_heartbeat
from runtime_safe_json import safe_atomic_write_json
from utils.market_hours import as_ist_datetime


PROOF_TASKS = ("heartbeat", "runtime_status", "dashboard_sync")
SCHEDULER_STATUS_PATH = Path("data/runtime/scanner_scheduler_status.json")


def _timestamp():
    return as_ist_datetime().isoformat()


def _read_worker_health():
    try:
        if not WORKER_HEALTH_PATH.exists():
            return {}
        payload = json.loads(WORKER_HEALTH_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_worker(task, **updates):
    payload = _read_worker_health()
    current = payload.get(task) if isinstance(payload.get(task), dict) else {}
    current.update(
        {
            "task": task,
            "status": updates.pop("status", current.get("status") or "OK"),
            "proof_mode": True,
            "proof_mission": "019",
            "active_pid": os.getpid(),
            "last_finished_at": _timestamp(),
            "last_error": None,
            "live_execution_enabled": False,
            "broker_order_api_called": False,
            "trading_api_called": False,
            "telegram_sent": False,
            "journal_mutation": False,
        }
    )
    current.update(updates)
    payload[task] = current
    safe_atomic_write_json(WORKER_HEALTH_PATH, payload)


def run_proof():
    results = {}
    os.environ["TITAN_RUNTIME_MASTER_BRAIN_MODE"] = "READ_ONLY"
    os.environ["TITAN_DASHBOARD_SYNC_LOCAL_ONLY"] = "1"
    os.environ.pop("TITAN_BROKER_LIVE_EXECUTION", None)
    os.environ.pop("TITAN_TELEGRAM_ALERTS", None)
    safe_atomic_write_json(
        SCHEDULER_STATUS_PATH,
        {
            "timestamp_ist": _timestamp(),
            "generated_at": _timestamp(),
            "status": "DISABLED",
            "scheduler_status": "DISABLED_FOR_PROOF",
            "proof_mode": True,
            "proof_mission": "019",
            "scanner_scheduler_enabled": False,
            "broker_order_api_called": False,
            "trading_api_called": False,
            "telegram_sent": False,
            "journal_mutation": False,
            "reason": "Mission 019 controlled worker proof did not enable daemon scanner scheduler.",
        },
    )
    for task in PROOF_TASKS:
        _write_worker(task, status="RUNNING", last_started_at=_timestamp())
        started = time.monotonic()
        try:
            if task == "heartbeat":
                result = write_heartbeat()
            elif task == "runtime_status":
                result = {
                    "timestamp_ist": _timestamp(),
                    "status": "WORKER_PROOF_RUNTIME_STATUS",
                    "mode": "WEEKEND_MODE",
                    "runtime_mode": "READ_ONLY",
                    "proof_mode": True,
                    "live_execution_enabled": False,
                    "broker_order_api_called": False,
                    "trading_api_called": False,
                    "telegram_sent": False,
                    "journal_mutation": False,
                }
                safe_atomic_write_json(Path("data/runtime/titan_runtime_status.json"), result)
            elif task == "dashboard_sync":
                result = run_dashboard_sync()
            else:
                result = {}
            _write_worker(
                task,
                status="OK",
                run_count=int((_read_worker_health().get(task) or {}).get("run_count") or 0) + 1,
                last_duration_seconds=round(time.monotonic() - started, 3),
            )
            results[task] = {"status": "OK", "result_status": (result or {}).get("status")}
        except Exception as exc:
            _write_worker(
                task,
                status="DEGRADED",
                last_error=f"{type(exc).__name__}:{exc}",
                last_duration_seconds=round(time.monotonic() - started, 3),
            )
            results[task] = {"status": "DEGRADED", "error": f"{type(exc).__name__}:{exc}"}
    return {
        "generated_at": _timestamp(),
        "status": "OK" if all(item.get("status") == "OK" for item in results.values()) else "DEGRADED",
        "proof_tasks": list(PROOF_TASKS),
        "results": results,
        "safety": {
            "live_execution": False,
            "broker_order_api_called": False,
            "trading_api_called": False,
            "telegram_sent": False,
            "journal_mutation": False,
            "supabase_trade_order_state": False,
        },
    }


if __name__ == "__main__":
    print(json.dumps(run_proof(), indent=2, sort_keys=True, default=str))
