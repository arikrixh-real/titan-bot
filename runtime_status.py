import json
from pathlib import Path

from engines.time_filter import get_mode_permissions
from engines.phase38_test_mode_guard import evaluate_phase38_runtime_guard, write_phase38_runtime_status
from runtime_mode_router import runtime_mode_snapshot
from utils.market_hours import IST, as_ist_datetime


STATUS_PATH = Path("data") / "runtime" / "titan_runtime_status.json"
HISTORICAL_REPLAY_STATUS_PATH = Path("data") / "runtime" / "historical_replay_status.json"
HISTORICAL_REPLAY_PROGRESS_PATH = Path("data") / "runtime" / "historical_replay_progress.json"
PHASE_STATUS_ARTIFACTS = {
    "phase21_autonomous_research": {
        "path": Path("data") / "research" / "autonomous_research_report.json",
        "placement": "master_controller_research_sidecar",
        "mode": "research_only",
        "fields": ("research_mode", "research_priority_score"),
    },
    "phase22_backtesting_validation": {
        "path": Path("data") / "research" / "backtesting_validation_report.json",
        "placement": "master_controller_validation_sidecar",
        "mode": "research_only",
        "fields": ("validation_status", "validation_score"),
    },
    "phase23_paper_trading": {
        "path": Path("data") / "paper_trading" / "latest_paper_trading_report.json",
        "fallback_path": Path("data") / "runtime" / "paper_engine_status.json",
        "placement": "master_controller_paper_sidecar",
        "mode": "paper_only",
        "fields": ("paper_trading_status", "risk_status", "current_balance"),
    },
    "phase24_broker_execution_safety": {
        "path": Path("data") / "execution_safety" / "latest_execution_safety_report.json",
        "placement": "master_controller_execution_safety_sidecar",
        "mode": "safety_only",
        "fields": ("status", "broker_execution_mode", "execution_allowed"),
    },
    "phase25_smart_execution": {
        "path": Path("data") / "execution_safety" / "latest_smart_execution_report.json",
        "placement": "master_controller_execution_quality_sidecar",
        "mode": "advisory_only",
        "fields": ("execution_mode", "execution_recommendation", "execution_quality_score"),
    },
    "phase36_memory_consolidation": {
        "path": Path("data") / "memory_consolidation" / "latest_memory_consolidation_report.json",
        "placement": "master_controller_memory_sidecar",
        "mode": "research_only",
        "fields": ("memory_data_mode", "memory_quality_score", "memory_warning"),
    },
    "phase37_auto_repair": {
        "path": Path("data") / "auto_repair" / "latest_auto_repair_report.json",
        "placement": "master_controller_diagnostic_sidecar",
        "mode": "diagnostic_only",
        "fields": ("repair_data_mode", "repair_status", "severity_score"),
    },
}


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


def _phase_status_summaries():
    summaries = {}
    for phase, spec in PHASE_STATUS_ARTIFACTS.items():
        path = spec["path"]
        payload = _read_json_safe(path)
        artifact_path = path
        if not payload and spec.get("fallback_path"):
            artifact_path = spec["fallback_path"]
            payload = _read_json_safe(artifact_path)

        summary = {
            "connected": bool(payload),
            "artifact_path": str(artifact_path).replace("\\", "/"),
            "pyramid_placement": payload.get("pyramid_placement") or spec["placement"],
            "mode": spec["mode"],
            "advisory_only": payload.get("advisory_only", True),
            "research_only": payload.get("research_only", spec["mode"] == "research_only"),
            "paper_only": payload.get("paper_only", spec["mode"] == "paper_only"),
            "shadow_mode": payload.get("shadow_mode", True),
            "safety": {
                "live_order_allowed": bool(payload.get("live_order_allowed", False)),
                "live_rank_mutation_allowed": bool(payload.get("live_rank_mutation_allowed", False)),
                "broker_orders": bool(payload.get("broker_orders", False)),
                "telegram_changes": bool(payload.get("telegram_changes", False)),
                "supabase_writes": bool(payload.get("supabase_writes", False)),
                "auto_file_changes_allowed": bool(payload.get("auto_file_changes_allowed", False)),
            },
            "values": {},
        }
        for field in spec["fields"]:
            if field in payload:
                summary["values"][field] = payload.get(field)
        summaries[phase] = summary
    return summaries


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
        "phase_sidecar_status": _phase_status_summaries(),
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
