import json
from pathlib import Path

from engines.time_filter import get_mode_permissions
from engines.phase38_test_mode_guard import evaluate_phase38_runtime_guard, write_phase38_runtime_status
from runtime_mode_router import runtime_mode_snapshot
from utils.market_hours import IST, as_ist_datetime


STATUS_PATH = Path("data") / "runtime" / "titan_runtime_status.json"
HISTORICAL_REPLAY_STATUS_PATH = Path("data") / "runtime" / "historical_replay_status.json"
HISTORICAL_REPLAY_PROGRESS_PATH = Path("data") / "runtime" / "historical_replay_progress.json"


def _read_json_safe(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _historical_replay_status_summary():
    status = _read_json_safe(HISTORICAL_REPLAY_STATUS_PATH)
    progress = _read_json_safe(HISTORICAL_REPLAY_PROGRESS_PATH)
    if not status and not progress:
        return {
            "status": "WAITING",
            "enabled_off_market": True,
            "cadence_seconds": 3600,
            "safety": {
                "telegram": False,
                "broker": False,
                "live_trade_mutation": False,
            },
        }

    return {
        "status": status.get("status") or progress.get("status") or "UNKNOWN",
        "last_run_at_ist": status.get("timestamp_ist"),
        "last_completed_at_ist": progress.get("last_completed_at_ist"),
        "last_skipped_at_ist": progress.get("last_skipped_at_ist"),
        "last_skip_reason": progress.get("last_skip_reason"),
        "last_records_generated": progress.get("last_records_generated"),
        "total_records_generated": progress.get("total_records_generated"),
        "batches_completed": progress.get("batches_completed"),
        "enabled_off_market": True,
        "cadence_seconds": 3600,
        "safety": {
            "telegram": False,
            "broker": False,
            "live_trade_mutation": False,
        },
    }


def build_runtime_status(value=None):
    now = as_ist_datetime(value)
    permissions = get_mode_permissions(now)
    phase38_guard = evaluate_phase38_runtime_guard(
        {
            "runtime_mode": permissions["mode"],
            "current_mode": permissions["mode"],
            "live_execution_enabled": False,
            "telegram_enabled": "telegram_alerts" in permissions["live_allowed_engines"],
            "broker_enabled": False,
        }
    )

    return {
        "timestamp_ist": now.astimezone(IST).isoformat(),
        "mode": permissions["mode"],
        "live_allowed_engines": permissions["live_allowed_engines"],
        "research_allowed_engines": permissions["research_allowed_engines"],
        "blocked_engines": permissions["blocked_engines"],
        "reason": permissions["reason"],
        "phase38_runtime_guard": phase38_guard,
        "historical_replay": _historical_replay_status_summary(),
    }


def write_runtime_status(path=STATUS_PATH, value=None):
    status = build_runtime_status(value)
    status["runtime_mode"] = runtime_mode_snapshot()
    phase38_context = {
        **status.get("runtime_mode", {}),
        "runtime_mode": status.get("mode"),
        "telegram_enabled": "telegram_alerts" in status.get("live_allowed_engines", []),
        "broker_enabled": False,
    }
    status["phase38_runtime_guard"] = evaluate_phase38_runtime_guard(phase38_context)
    write_phase38_runtime_status(phase38_context)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    return status


if __name__ == "__main__":
    write_runtime_status()
