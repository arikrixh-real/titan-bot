import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from engines.time_filter import current_bot_mode
from utils.market_hours import as_ist_datetime, is_trade_window


HISTORICAL_REPLAY_STATUS_PATH = Path("data") / "runtime" / "historical_replay_status.json"
HISTORICAL_REPLAY_PROGRESS_PATH = Path("data") / "runtime" / "historical_replay_progress.json"
HISTORICAL_SOURCE_DIR = Path("data") / "historical_longterm"
DEFAULT_BATCH_SIZE = 250
MAX_PER_RUN = 500


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _bounded_batch_size(value: Any) -> int:
    try:
        requested = int(value or DEFAULT_BATCH_SIZE)
    except (TypeError, ValueError):
        requested = DEFAULT_BATCH_SIZE
    return min(max(1, requested), MAX_PER_RUN)


def _latest_jsonl_records(path: Path, limit: int) -> List[Dict[str, Any]]:
    if limit < 1 or not path.exists():
        return []

    parsed_records: List[Dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    start_line = max(1, len(lines) - limit + 1)
    for offset, raw_line in enumerate(lines[-limit:], start=start_line):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            record.setdefault("_source_line", offset)
            parsed_records.append(record)
    return parsed_records


def _consolidate_latest(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    from engines import memory_consolidation_engine
    from research import consolidate_historical_experience

    memory_data = consolidate_historical_experience.build_memory_data(records)
    report = memory_consolidation_engine.build_memory_consolidation_report(
        memory_data=memory_data,
        trade_history=records,
        context=consolidate_historical_experience.CONTEXT,
    )
    return {
        "records_loaded": len(records),
        "memory_summaries": len(memory_data),
        "memory_data_mode": report.get("memory_data_mode"),
        "memory_quality_score": report.get("memory_quality_score"),
        "live_order_allowed": report.get("live_order_allowed"),
    }


def _rebuild_historical_adaptive_memory(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    from research import build_historical_adaptive_memory as historical_adaptive_memory

    closed_rows = historical_adaptive_memory.synthetic_closed_trade_rows(records)

    with historical_adaptive_memory.patched_adaptive_inputs(closed_rows):
        adaptive_state = historical_adaptive_memory.adaptive_memory_builder.build_adaptive_memory(write_files=True)

    with historical_adaptive_memory.patched_evolution_inputs(closed_rows, dry_run=False):
        evolution_state = historical_adaptive_memory.evolution_engine.run_evolution_engine()

    historical_adaptive_memory.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    historical_adaptive_memory.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    historical_adaptive_memory.write_research_report(
        records_loaded=len(records),
        skipped_records=0,
        closed_rows=closed_rows,
        adaptive_state=adaptive_state,
        evolution_state=evolution_state,
    )

    return {
        "records_loaded": len(records),
        "synthetic_closed_trades": len(closed_rows),
        "total_wins": adaptive_state.get("total_wins"),
        "total_losses": adaptive_state.get("total_losses"),
        "adaptive_confidence": adaptive_state.get("global_confidence", {}).get("adaptive_confidence_score"),
        "evolution_score_boost": evolution_state.get("score_boost"),
        "evolution_filter_strictness": evolution_state.get("filter_strictness"),
        "evolution_ranking_confidence": evolution_state.get("ranking_confidence"),
    }


def run_historical_replay(batch_size: int = DEFAULT_BATCH_SIZE):
    now_ist = as_ist_datetime()
    mode = current_bot_mode(now_ist)
    bounded_batch_size = _bounded_batch_size(batch_size)
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "mode": mode,
        "status": "STARTED",
        "research_only": True,
        "source_dir": str(HISTORICAL_SOURCE_DIR),
        "batch_size": bounded_batch_size,
        "max_per_run": MAX_PER_RUN,
        "safety": {
            "telegram": False,
            "broker": False,
            "supabase": False,
            "live_journal_writes": False,
        },
    }

    progress = {
        **_read_json(HISTORICAL_REPLAY_PROGRESS_PATH),
        "timestamp_ist": payload["timestamp_ist"],
        "mode": mode,
        "source_dir": str(HISTORICAL_SOURCE_DIR),
        "batch_size": bounded_batch_size,
        "max_per_run": MAX_PER_RUN,
    }

    if is_trade_window(now_ist):
        payload["status"] = "SKIPPED_MARKET_HOURS"
        progress.update(
            {
                "status": payload["status"],
                "last_skipped_at_ist": payload["timestamp_ist"],
                "last_skip_reason": "Market hours are active; heavy historical replay is deferred.",
            }
        )
        _write_json(HISTORICAL_REPLAY_STATUS_PATH, payload)
        _write_json(HISTORICAL_REPLAY_PROGRESS_PATH, progress)
        return payload

    try:
        from research.historical_experience_feeder import run_feeder
        from research import consolidate_historical_experience

        _write_json(HISTORICAL_REPLAY_STATUS_PATH, payload)

        feeder_report = run_feeder(
            limit=bounded_batch_size,
            dry_run=False,
            source_dir=HISTORICAL_SOURCE_DIR,
        )
        generated = int(feeder_report.get("records_generated") or 0)
        latest_records = _latest_jsonl_records(consolidate_historical_experience.INPUT_PATH, generated)

        consolidation_report: Optional[Dict[str, Any]] = None
        adaptive_report: Optional[Dict[str, Any]] = None
        if latest_records:
            consolidation_report = _consolidate_latest(latest_records)
            adaptive_report = _rebuild_historical_adaptive_memory(latest_records)

        previous_batches = int(progress.get("batches_completed") or 0)
        previous_records = int(progress.get("total_records_generated") or 0)
        payload.update(
            {
                "status": "COMPLETED" if generated else "COMPLETED_NO_NEW_RECORDS",
                "records_generated": generated,
                "skipped_duplicates": feeder_report.get("skipped_duplicates"),
                "symbols_scanned": feeder_report.get("symbols_scanned"),
                "feeder": feeder_report,
                "consolidation": consolidation_report,
                "adaptive_memory": adaptive_report,
            }
        )
        progress.update(
            {
                "status": payload["status"],
                "last_completed_at_ist": payload["timestamp_ist"],
                "last_records_generated": generated,
                "last_skipped_duplicates": feeder_report.get("skipped_duplicates"),
                "last_symbols_scanned": feeder_report.get("symbols_scanned"),
                "batches_completed": previous_batches + 1,
                "total_records_generated": previous_records + generated,
                "consolidation": consolidation_report,
                "adaptive_memory": adaptive_report,
            }
        )
    except Exception as exc:
        payload.update(
            {
                "status": "FAILED",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )
        progress.update(
            {
                "status": "FAILED",
                "last_failed_at_ist": payload["timestamp_ist"],
                "error_type": payload["error_type"],
                "error": payload["error"],
            }
        )

    _write_json(HISTORICAL_REPLAY_STATUS_PATH, payload)
    _write_json(HISTORICAL_REPLAY_PROGRESS_PATH, progress)
    return payload
