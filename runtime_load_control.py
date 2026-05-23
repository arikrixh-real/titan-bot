import glob
import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime_resilience_status import OFFICIAL_RUNTIME_PATH, read_json_safe
from runtime_safe_json import safe_atomic_write_json


IST = timezone(timedelta(hours=5, minutes=30))
LOAD_CONTROL_STATUS_PATH = Path("data") / "runtime" / "intelligence_load_control_status.json"

HEAVY_TASK_RULES = {
    "report_aggregator": {
        "min_interval_seconds": 15 * 60,
        "input_patterns": [
            "data/runtime/worker_health.json",
            "data/runtime/intelligence_state/*.json",
            "data/runtime/*_status.json",
            "data/research/*.json",
            "data/scenario_simulation/*.json",
            "data/self_reflection/*.json",
            "data/confidence_calibration/*.json",
            "data/no_trade/*.json",
            "data/memory_consolidation/*.json",
            "data/auto_repair/*.json",
            "data/execution_safety/*.json",
            "data/news_intelligence/*.json",
            "data/economic_calendar/*.json",
            "data/microstructure/*.json",
            "data/options_flow/*.json",
            "data/liquidity_map/*.json",
            "reports/*.txt",
        ],
        "skip_if_unchanged": True,
    },
    "consciousness_core": {
        "min_interval_seconds": 30 * 60,
        "input_patterns": [
            "data/report_vault/latest_aggregated_packet.json",
            "data/knowledge_vault/reports/knowledge_to_consciousness_packet.json",
            "data/experience_vault/reports/external_experience_packet.json",
            "data/memory/evolution_state.json",
            "data/research/*.json",
            "data/scenario_simulation/*.json",
            "reports/evolution_report.txt",
        ],
        "skip_if_unchanged": True,
    },
    "experience_vault_runner": {
        "min_interval_seconds": 30 * 60,
        "input_patterns": ["data/experience_vault/**/*"],
        "skip_if_unchanged": False,
    },
    "knowledge_vault_runner": {
        "min_interval_seconds": 30 * 60,
        "input_patterns": ["data/knowledge_vault/**/*"],
        "skip_if_unchanged": False,
    },
    "scenario_simulation": {
        "min_interval_seconds": 60 * 60,
        "input_patterns": ["data/runtime/master_brain_status.json", "data/research/*.json"],
        "skip_if_unchanged": True,
    },
    "backtesting": {
        "min_interval_seconds": 60 * 60,
        "input_patterns": ["data/research/*.json", "data/trade_journal.csv", "data/journals/*"],
        "skip_if_unchanged": True,
    },
    "evolution_engine": {
        "min_interval_seconds": 60 * 60,
        "input_patterns": ["data/trade_journal.csv", "data/journals/*", "data/memory/*.json"],
        "skip_if_unchanged": True,
    },
    "learning_engine": {
        "min_interval_seconds": 30 * 60,
        "input_patterns": ["data/trade_journal.csv", "data/journals/*", "data/consciousness_core/*.json"],
        "skip_if_unchanged": True,
    },
    "historical_replay": {
        "min_interval_seconds": 60 * 60,
        "input_patterns": [
            "data/historical_longterm/*.csv",
            "data/runtime/historical_replay_progress.json",
        ],
        "skip_if_unchanged": False,
    },
}


def now_ist():
    return datetime.now(IST).isoformat()


def _atomic_write_json(path, payload):
    safe_atomic_write_json(path, payload)


def _read_status():
    try:
        with LOAD_CONTROL_STATUS_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_status(status):
    status["updated_at"] = now_ist()
    status["mode"] = "LOAD_CONTROL_ONLY"
    status["official_runtime_path"] = OFFICIAL_RUNTIME_PATH
    status["safety"] = {
        "advisory_only": True,
        "live_mutation": False,
        "direct_strategy_changes": False,
        "broker_orders": False,
        "alert_changes": False,
    }
    resilience_status = read_json_safe(Path("data") / "runtime" / "runtime_resilience_status.json")
    if isinstance(resilience_status, dict):
        status["runtime_resilience_status"] = {
            "status": resilience_status.get("status"),
            "degraded_components": resilience_status.get("degraded_components", []),
            "stale_packet_count": resilience_status.get("stale_packet_summary", {}).get("stale_count"),
            "worker_degraded_count": resilience_status.get("worker_health_summary", {}).get("degraded_count"),
            "last_good_outputs_used": resilience_status.get("last_good_outputs_used", []),
        }
    try:
        _atomic_write_json(LOAD_CONTROL_STATUS_PATH, status)
    except OSError as exc:
        status["last_status_write_error"] = str(exc)


def _file_signature(path):
    stat = path.stat()
    return {
        "path": str(path).replace("\\", "/"),
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
    }


def input_signature(patterns):
    files = []
    excluded = {LOAD_CONTROL_STATUS_PATH.as_posix(), str(LOAD_CONTROL_STATUS_PATH).replace("\\", "/")}
    for pattern in patterns or []:
        for match in sorted(glob.glob(pattern, recursive=True)):
            path = Path(match)
            display_path = str(path).replace("\\", "/")
            if path.is_file() and display_path not in excluded:
                files.append(_file_signature(path))
    digest = hashlib.sha256(
        json.dumps(files, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return {"hash": digest, "file_count": len(files), "files": files[:100]}


def should_skip_task(task, force=False):
    rule = HEAVY_TASK_RULES.get(task)
    if not rule or force:
        return False, {"task": task, "rule_found": bool(rule), "forced": bool(force)}

    status = _read_status()
    tasks = status.setdefault("tasks", {})
    item = tasks.setdefault(task, {"task": task})
    now_ts = datetime.now(timezone.utc).timestamp()
    min_interval = int(rule.get("min_interval_seconds") or 0)
    last_started_ts = float(item.get("last_started_ts") or 0.0)
    age_seconds = now_ts - last_started_ts if last_started_ts else None
    signature = input_signature(rule.get("input_patterns", []))
    last_input_hash = item.get("last_input_hash")

    decision = {
        "task": task,
        "rule": rule,
        "input_hash": signature["hash"],
        "input_file_count": signature["file_count"],
        "last_input_hash": last_input_hash,
        "age_seconds": None if age_seconds is None else round(age_seconds, 3),
    }
    if last_started_ts and age_seconds is not None and age_seconds < min_interval:
        item.update(
            {
                "last_decision": "SKIPPED_RECENT",
                "last_skip_reason": f"min_interval_seconds={min_interval}",
                "last_checked_at": now_ist(),
                "last_input_hash": signature["hash"],
                "input_file_count": signature["file_count"],
                "min_interval_seconds": min_interval,
            }
        )
        _write_status(status)
        decision["reason"] = item["last_skip_reason"]
        return True, decision

    if rule.get("skip_if_unchanged") and last_input_hash and last_input_hash == signature["hash"]:
        item.update(
            {
                "last_decision": "SKIPPED_UNCHANGED",
                "last_skip_reason": "input_signature_unchanged",
                "last_checked_at": now_ist(),
                "last_input_hash": signature["hash"],
                "input_file_count": signature["file_count"],
                "min_interval_seconds": min_interval,
            }
        )
        _write_status(status)
        decision["reason"] = item["last_skip_reason"]
        return True, decision

    item.update(
        {
            "last_decision": "RUN_ALLOWED",
            "last_skip_reason": None,
            "last_checked_at": now_ist(),
            "last_started_at": now_ist(),
            "last_started_ts": now_ts,
            "last_input_hash": signature["hash"],
            "input_file_count": signature["file_count"],
            "min_interval_seconds": min_interval,
            "skip_if_unchanged": bool(rule.get("skip_if_unchanged")),
        }
    )
    _write_status(status)
    return False, decision


def record_task_result(task, status_text, result=None, runtime_seconds=None, error=None):
    status = _read_status()
    tasks = status.setdefault("tasks", {})
    item = tasks.setdefault(task, {"task": task})
    item.update(
        {
            "last_finished_at": now_ist(),
            "last_result_status": status_text,
            "last_runtime_seconds": None if runtime_seconds is None else round(runtime_seconds, 3),
            "last_error": None if error is None else str(error),
        }
    )
    if isinstance(result, dict):
        for key in ("packet_hash", "status", "runner", "warnings"):
            if key in result:
                item[f"result_{key}"] = result.get(key)
    _write_status(status)


def load_control_summary():
    status = _read_status()
    return {
        "path": str(LOAD_CONTROL_STATUS_PATH).replace("\\", "/"),
        "updated_at": status.get("updated_at"),
        "official_runtime_path": status.get("official_runtime_path") or OFFICIAL_RUNTIME_PATH,
        "runtime_resilience_status": status.get("runtime_resilience_status", {}),
        "tasks": status.get("tasks", {}),
        "safety": status.get("safety", {}),
    }
