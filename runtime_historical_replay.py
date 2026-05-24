import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from engines.time_filter import current_bot_mode
from engines.phase38_test_mode_guard import evaluate_phase38_runtime_guard, write_phase38_runtime_status
from utils.market_hours import as_ist_datetime, is_trade_window


HISTORICAL_REPLAY_STATUS_PATH = Path("data") / "runtime" / "historical_replay_status.json"
HISTORICAL_REPLAY_PROGRESS_PATH = Path("data") / "runtime" / "historical_replay_progress.json"
HISTORICAL_SOURCE_DIR = Path("data") / "historical_longterm"
DEFAULT_BATCH_SIZE = 250
MAX_PER_RUN = 500
DEFAULT_SAMPLING_MODE = "stratified"
DEFAULT_YEAR_FOCUS = [2008, 2020, 2022, 2024]
DEFAULT_MAX_PER_SYMBOL = 5
DEFAULT_MAX_PER_YEAR = 100


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


def _active_replay_config(
    sampling_mode: str = DEFAULT_SAMPLING_MODE,
    year_focus: Optional[Union[str, Iterable[int]]] = None,
    max_per_symbol: Optional[int] = DEFAULT_MAX_PER_SYMBOL,
    max_per_year: Optional[int] = DEFAULT_MAX_PER_YEAR,
) -> Dict[str, Any]:
    clean_sampling_mode = sampling_mode if sampling_mode in {"sequential", "stratified"} else DEFAULT_SAMPLING_MODE
    clean_year_focus: List[int] = []
    raw_year_focus = DEFAULT_YEAR_FOCUS if year_focus is None else year_focus
    if isinstance(raw_year_focus, str):
        year_values = [value.strip() for value in raw_year_focus.split(",")]
    else:
        year_values = list(raw_year_focus)
    for value in year_values:
        try:
            clean_year_focus.append(int(value))
        except (TypeError, ValueError):
            continue

    return {
        "sampling_mode": clean_sampling_mode,
        "year_focus": clean_year_focus,
        "max_per_symbol": max(1, int(max_per_symbol)) if max_per_symbol is not None else None,
        "max_per_year": max(1, int(max_per_year)) if max_per_year is not None else None,
    }


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
        adaptive_state = historical_adaptive_memory.adaptive_memory_builder.build_adaptive_memory(write_files=False)
    historical_adaptive_memory.tag_historical_state(adaptive_state)

    with historical_adaptive_memory.patched_evolution_inputs(closed_rows, dry_run=False):
        evolution_state = historical_adaptive_memory.evolution_engine.run_evolution_engine()
    historical_adaptive_memory.tag_historical_state(evolution_state)

    historical_adaptive_memory.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    historical_adaptive_memory.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    historical_adaptive_memory.write_historical_adaptive_outputs(adaptive_state)
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


def _refresh_reinforcement_learning_from_replay(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    from engines import reinforcement_learning_layer

    memory = reinforcement_learning_layer.refresh_reinforcement_memory_from_replay(
        records,
        write_files=True,
    )
    return {
        "status": "CONNECTED_SHADOW",
        "research_only": memory.get("research_only", True),
        "advisory_only": memory.get("advisory_only", True),
        "shadow_mode": memory.get("shadow_mode", True),
        "records_processed": memory.get("records_processed"),
        "memory_priority": memory.get("memory_priority"),
        "exploration_exploitation_score": memory.get("exploration_exploitation_score"),
        "policy_stability": memory.get("policy_stability"),
        "memory_path": str(reinforcement_learning_layer.REINFORCEMENT_MEMORY_PATH),
        "report_path": str(reinforcement_learning_layer.REINFORCEMENT_REPORT_PATH),
        "runtime_status_path": str(reinforcement_learning_layer.REINFORCEMENT_STATUS_PATH),
        "safety": memory.get("safety"),
    }


def _top_bucket_summaries(buckets: Any, fields: List[str], limit: int = 5) -> List[Dict[str, Any]]:
    if not isinstance(buckets, dict):
        return []

    summaries: List[Dict[str, Any]] = []
    for name, bucket in buckets.items():
        if not isinstance(bucket, dict):
            continue
        summary = {"name": name}
        for field in fields:
            summary[field] = bucket.get(field)
        summaries.append(summary)

    return sorted(
        summaries,
        key=lambda item: int(item.get("samples") or 0),
        reverse=True,
    )[:limit]


def _summarize_volatility_memory(memory: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_type": memory.get("source_type"),
        "advisory_only": memory.get("advisory_only"),
        "affects_live_execution_directly": memory.get("affects_live_execution_directly"),
        "record_count": memory.get("record_count"),
        "phase_count": len(memory.get("phase_buckets") or {}),
        "top_phase_buckets": _top_bucket_summaries(
            memory.get("phase_buckets"),
            ["samples", "wins", "losses", "win_rate", "avg_compression_score"],
        ),
    }


def _summarize_trap_memory(memory: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_type": memory.get("source_type"),
        "advisory_only": memory.get("advisory_only"),
        "affects_live_execution_directly": memory.get("affects_live_execution_directly"),
        "record_count": memory.get("record_count"),
        "matched_trap_records": memory.get("matched_trap_records"),
        "pattern_count": len(memory.get("pattern_buckets") or {}),
        "top_pattern_buckets": _top_bucket_summaries(
            memory.get("pattern_buckets"),
            ["samples", "wins", "losses", "loss_rate"],
        ),
    }


def _summarize_advanced_regime(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    active = snapshot.get("active_regime") if isinstance(snapshot.get("active_regime"), dict) else {}
    historical = (
        snapshot.get("historical_replay_context")
        if isinstance(snapshot.get("historical_replay_context"), dict)
        else {}
    )
    return {
        "phase12_shadow_mode": snapshot.get("phase12_shadow_mode"),
        "runtime_bounded": snapshot.get("runtime_bounded"),
        "primary_regime": active.get("primary"),
        "regime_confidence": active.get("confidence"),
        "transition_detected": active.get("transition_detected"),
        "historical_replay_context": {
            "advisory_only": historical.get("advisory_only", True),
            "historical_win_rate": historical.get("historical_win_rate"),
            "historical_filter_strictness": historical.get("historical_filter_strictness"),
            "historical_score_boost": historical.get("historical_score_boost"),
        },
    }


def _summarize_confidence_decay_memory(memory: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_type": memory.get("source_type"),
        "advisory_only": memory.get("advisory_only"),
        "replay_research_only": memory.get("replay_research_only"),
        "affects_live_execution_directly": memory.get("affects_live_execution_directly"),
        "rank_adjustment": memory.get("rank_adjustment"),
        "recommended_live_weight": memory.get("recommended_live_weight"),
        "record_count": memory.get("record_count"),
        "age_bucket_count": len(memory.get("age_buckets") or {}),
        "setup_age_bucket_count": len(memory.get("setup_age_buckets") or {}),
        "top_age_buckets": _top_bucket_summaries(
            memory.get("age_buckets"),
            ["samples", "wins", "losses", "loss_rate", "avg_confidence", "avg_signal_age_minutes"],
        ),
        "top_setup_age_buckets": _top_bucket_summaries(
            memory.get("setup_age_buckets"),
            ["samples", "wins", "losses", "loss_rate", "avg_confidence", "avg_signal_age_minutes"],
        ),
    }


def _summarize_transition_instability_memory(memory: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_type": memory.get("source_type"),
        "advisory_only": memory.get("advisory_only"),
        "replay_research_only": memory.get("replay_research_only"),
        "affects_live_execution_directly": memory.get("affects_live_execution_directly"),
        "rank_adjustment": memory.get("rank_adjustment"),
        "recommended_live_weight": memory.get("recommended_live_weight"),
        "record_count": memory.get("record_count"),
        "instability_bucket_count": len(memory.get("instability_buckets") or {}),
        "transition_instability_bucket_count": len(memory.get("transition_instability_buckets") or {}),
        "recent_transition_events": len(memory.get("recent_transition_events") or []),
        "top_instability_buckets": _top_bucket_summaries(
            memory.get("instability_buckets"),
            ["samples", "wins", "losses", "loss_rate", "avg_transition_strength"],
        ),
        "top_transition_instability_buckets": _top_bucket_summaries(
            memory.get("transition_instability_buckets"),
            ["samples", "wins", "losses", "loss_rate", "avg_transition_strength"],
        ),
    }


def _summarize_multi_timeframe_conflict_memory(memory: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_type": memory.get("source_type"),
        "advisory_only": memory.get("advisory_only"),
        "replay_research_only": memory.get("replay_research_only"),
        "affects_live_execution_directly": memory.get("affects_live_execution_directly"),
        "rank_adjustment": memory.get("rank_adjustment"),
        "recommended_live_weight": memory.get("recommended_live_weight"),
        "record_count": memory.get("record_count"),
        "conflict_bucket_count": len(memory.get("conflict_buckets") or {}),
        "symbol_conflict_bucket_count": len(memory.get("symbol_conflict_buckets") or {}),
        "top_conflict_buckets": _top_bucket_summaries(
            memory.get("conflict_buckets"),
            ["samples", "wins", "losses", "loss_rate", "avg_score"],
        ),
        "top_symbol_conflict_buckets": _top_bucket_summaries(
            memory.get("symbol_conflict_buckets"),
            ["samples", "wins", "losses", "loss_rate", "avg_score"],
        ),
    }


def _summarize_no_trade_refinement_memory(memory: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_type": memory.get("source_type"),
        "advisory_only": memory.get("advisory_only"),
        "replay_research_only": memory.get("replay_research_only"),
        "affects_live_execution_directly": memory.get("affects_live_execution_directly"),
        "rank_adjustment": memory.get("rank_adjustment"),
        "recommended_live_weight": memory.get("recommended_live_weight"),
        "record_count": memory.get("record_count"),
        "refinement_bucket_count": len(memory.get("refinement_buckets") or {}),
        "symbol_refinement_bucket_count": len(memory.get("symbol_refinement_buckets") or {}),
        "top_refinement_buckets": _top_bucket_summaries(
            memory.get("refinement_buckets"),
            ["samples", "wins", "losses", "win_rate", "avg_no_trade_score"],
        ),
        "top_symbol_refinement_buckets": _top_bucket_summaries(
            memory.get("symbol_refinement_buckets"),
            ["samples", "wins", "losses", "win_rate", "avg_no_trade_score"],
        ),
    }


def _refresh_research_memory_engines(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    warnings: List[Dict[str, Any]] = []
    report: Dict[str, Any] = {
        "research_only": True,
        "advisory_only": True,
        "records_loaded": len(records),
        "warnings": warnings,
    }

    try:
        from engines import volatility_memory_engine

        volatility_memory = volatility_memory_engine.refresh_volatility_memory(records)
        report["volatility_memory"] = _summarize_volatility_memory(volatility_memory)
    except Exception as exc:
        warnings.append(
            {
                "engine": "engines.volatility_memory_engine",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )

    try:
        from engines import trap_memory_engine

        trap_memory = trap_memory_engine.refresh_trap_memory(records)
        report["trap_memory"] = _summarize_trap_memory(trap_memory)
    except Exception as exc:
        warnings.append(
            {
                "engine": "engines.trap_memory_engine",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )

    try:
        from engines import advanced_regime_intelligence

        advanced_regime = advanced_regime_intelligence.refresh_advanced_regime_intelligence(force=True)
        snapshot = advanced_regime.get("snapshot") if isinstance(advanced_regime.get("snapshot"), dict) else advanced_regime
        report["advanced_regime_intelligence"] = _summarize_advanced_regime(snapshot)
    except Exception as exc:
        warnings.append(
            {
                "engine": "engines.advanced_regime_intelligence",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )

    try:
        from engines import confidence_decay_memory_engine

        confidence_decay_memory = confidence_decay_memory_engine.refresh_confidence_decay_memory(records)
        report["confidence_decay_memory"] = _summarize_confidence_decay_memory(confidence_decay_memory)
    except Exception as exc:
        warnings.append(
            {
                "engine": "engines.confidence_decay_memory_engine",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )

    try:
        from engines import transition_instability_memory_engine

        transition_instability_memory = transition_instability_memory_engine.refresh_transition_instability_memory(records)
        report["transition_instability_memory"] = _summarize_transition_instability_memory(transition_instability_memory)
    except Exception as exc:
        warnings.append(
            {
                "engine": "engines.transition_instability_memory_engine",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )

    try:
        from engines import multi_timeframe_conflict_memory_engine

        multi_timeframe_conflict_memory = multi_timeframe_conflict_memory_engine.refresh_multi_timeframe_conflict_memory(records)
        report["multi_timeframe_conflict_memory"] = _summarize_multi_timeframe_conflict_memory(multi_timeframe_conflict_memory)
    except Exception as exc:
        warnings.append(
            {
                "engine": "engines.multi_timeframe_conflict_memory_engine",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )

    try:
        from engines import no_trade_refinement_memory_engine

        no_trade_refinement_memory = no_trade_refinement_memory_engine.refresh_no_trade_refinement_memory(records)
        report["no_trade_refinement_memory"] = _summarize_no_trade_refinement_memory(no_trade_refinement_memory)
    except Exception as exc:
        warnings.append(
            {
                "engine": "engines.no_trade_refinement_memory_engine",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )

    return report


def run_historical_replay(
    batch_size: int = DEFAULT_BATCH_SIZE,
    sampling_mode: str = DEFAULT_SAMPLING_MODE,
    year_focus: Optional[Union[str, Iterable[int]]] = None,
    max_per_symbol: Optional[int] = DEFAULT_MAX_PER_SYMBOL,
    max_per_year: Optional[int] = DEFAULT_MAX_PER_YEAR,
):
    now_ist = as_ist_datetime()
    mode = current_bot_mode(now_ist)
    bounded_batch_size = _bounded_batch_size(batch_size)
    replay_config = _active_replay_config(
        sampling_mode=sampling_mode,
        year_focus=year_focus,
        max_per_symbol=max_per_symbol,
        max_per_year=max_per_year,
    )
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "mode": mode,
        "status": "STARTED",
        "research_only": True,
        "source_dir": str(HISTORICAL_SOURCE_DIR),
        "batch_size": bounded_batch_size,
        "max_per_run": MAX_PER_RUN,
        **replay_config,
        "safety": {
            "telegram": False,
            "broker": False,
            "supabase": False,
            "live_journal_writes": False,
        },
    }
    phase38_guard = evaluate_phase38_runtime_guard(
        {
            "runtime_mode": os.getenv("TITAN_RUNTIME_MASTER_BRAIN_MODE") or mode,
            "current_mode": mode,
            "research_only": True,
            "replay_active": True,
            "live_execution_enabled": False,
            "telegram_enabled": False,
            "broker_enabled": False,
        }
    )
    payload["phase38_runtime_guard"] = phase38_guard
    try:
        write_phase38_runtime_status(payload)
    except OSError:
        pass

    progress = {
        **_read_json(HISTORICAL_REPLAY_PROGRESS_PATH),
        "timestamp_ist": payload["timestamp_ist"],
        "mode": mode,
        "source_dir": str(HISTORICAL_SOURCE_DIR),
        "batch_size": bounded_batch_size,
        "max_per_run": MAX_PER_RUN,
        **replay_config,
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

    if not phase38_guard.get("phase38_runtime_allowed"):
        payload["status"] = "SKIPPED_PHASE38_FAIL_CLOSED"
        progress.update(
            {
                "status": payload["status"],
                "last_skipped_at_ist": payload["timestamp_ist"],
                "last_skip_reason": "Phase 38 blocked replay/live runtime combination.",
                "phase38_runtime_guard": phase38_guard,
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
            **replay_config,
        )
        generated = int(feeder_report.get("records_generated") or 0)
        latest_records = _latest_jsonl_records(consolidate_historical_experience.INPUT_PATH, generated)

        consolidation_report: Optional[Dict[str, Any]] = None
        adaptive_report: Optional[Dict[str, Any]] = None
        research_memory_report: Optional[Dict[str, Any]] = None
        reinforcement_learning_report: Optional[Dict[str, Any]] = None
        if latest_records:
            consolidation_report = _consolidate_latest(latest_records)
            adaptive_report = _rebuild_historical_adaptive_memory(latest_records)
            research_memory_report = _refresh_research_memory_engines(latest_records)
            reinforcement_learning_report = _refresh_reinforcement_learning_from_replay(latest_records)

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
                "reinforcement_learning": reinforcement_learning_report,
                "volatility_memory": (research_memory_report or {}).get("volatility_memory"),
                "trap_memory": (research_memory_report or {}).get("trap_memory"),
                "advanced_regime_intelligence": (research_memory_report or {}).get("advanced_regime_intelligence"),
                "confidence_decay_memory": (research_memory_report or {}).get("confidence_decay_memory"),
                "transition_instability_memory": (research_memory_report or {}).get("transition_instability_memory"),
                "multi_timeframe_conflict_memory": (research_memory_report or {}).get("multi_timeframe_conflict_memory"),
                "no_trade_refinement_memory": (research_memory_report or {}).get("no_trade_refinement_memory"),
                "research_memory_refresh": research_memory_report,
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
                "reinforcement_learning": reinforcement_learning_report,
                "research_memory_refresh": research_memory_report,
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
