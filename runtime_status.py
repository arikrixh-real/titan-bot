import json
from datetime import datetime
from pathlib import Path

from engines.time_filter import get_mode_permissions
from engines.phase38_test_mode_guard import evaluate_phase38_runtime_guard, write_phase38_runtime_status
from runtime_mode_router import runtime_mode_snapshot
from utils.market_hours import IST, as_ist_datetime


STATUS_PATH = Path("data") / "runtime" / "titan_runtime_status.json"
HISTORICAL_REPLAY_STATUS_PATH = Path("data") / "runtime" / "historical_replay_status.json"
HISTORICAL_REPLAY_PROGRESS_PATH = Path("data") / "runtime" / "historical_replay_progress.json"
HISTORICAL_EXPERIENCE_REPORT_PATH = (
    Path("data") / "experience_vault" / "imported_trade_logs" / "historical_experience_import_report.json"
)
HISTORICAL_EXPERIENCE_CSV_PATH = (
    Path("data") / "experience_vault" / "imported_trade_logs" / "historical_experience_import.csv"
)
HISTORICAL_EXPERIENCE_JSONL_PATH = (
    Path("data") / "experience_vault" / "imported_trade_logs" / "historical_experience_import.jsonl"
)
PHASE39_STALE_REPLAY_SECONDS = 24 * 60 * 60
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
    "phase40_accuracy_validation": {
        "path": Path("data") / "runtime" / "accuracy_validation_status.json",
        "fallback_path": Path("data") / "memory" / "accuracy_validation_state.json",
        "placement": "master_controller_accuracy_validation_sidecar",
        "mode": "advisory_only",
        "fields": ("status", "run_count", "closed_records_this_run", "new_record_ids_this_run"),
    },
    "phase41_meta_learning": {
        "path": Path("data") / "runtime" / "meta_learning_status.json",
        "fallback_path": Path("data") / "memory" / "meta_learning_state.json",
        "placement": "master_controller_meta_learning_sidecar",
        "mode": "advisory_only",
        "fields": ("status", "run_count", "priority_count", "phase40_run_count_seen"),
    },
    "phase42_strategy_genome_architecture": {
        "path": Path("data") / "runtime" / "strategy_genome_status.json",
        "fallback_path": Path("data") / "memory" / "strategy_genome_memory.json",
        "placement": "master_controller_strategy_genome_sidecar",
        "mode": "advisory_only",
        "fields": ("status", "run_count", "family_count", "active_regime"),
    },
    "phase43_meta_regime_intelligence": {
        "path": Path("data") / "runtime" / "meta_regime_intelligence_status.json",
        "fallback_path": Path("data") / "memory" / "meta_regime_intelligence_state.json",
        "placement": "master_controller_meta_regime_sidecar",
        "mode": "advisory_only",
        "fields": (
            "status",
            "run_count",
            "phase42_consumed",
            "phase42_run_count_seen",
            "transition_risk_score",
            "strategy_regime_mismatch_score",
            "global_meta_regime_risk_score",
        ),
    },
}
PHASE39_MEMORY_ARTIFACTS = {
    "adaptive_memory": {
        "path": Path("data") / "memory" / "historical_adaptive_intelligence_state.json",
        "report_path": Path("reports") / "historical_adaptive_intelligence_report.txt",
        "progress_key": "adaptive_memory",
    },
    "rl_shadow_refresh": {
        "path": Path("data") / "memory" / "reinforcement_learning_memory.json",
        "report_path": Path("reports") / "phase20_reinforcement_learning_report.txt",
        "runtime_path": Path("data") / "runtime" / "reinforcement_learning_status.json",
        "progress_key": "reinforcement_learning",
    },
    "volatility_memory": {
        "path": Path("data") / "memory" / "volatility_expansion_compression_memory.json",
        "report_path": Path("reports") / "volatility_memory_report.txt",
    },
    "trap_memory": {
        "path": Path("data") / "memory" / "trap_fakeout_memory.json",
        "report_path": Path("reports") / "trap_memory_report.txt",
    },
    "confidence_decay_memory": {
        "path": Path("data") / "memory" / "confidence_decay_memory.json",
        "report_path": Path("reports") / "confidence_decay_memory_report.txt",
    },
    "transition_instability_memory": {
        "path": Path("data") / "memory" / "transition_instability_memory.json",
        "report_path": Path("reports") / "transition_instability_memory_report.txt",
    },
    "multi_timeframe_conflict_memory": {
        "path": Path("data") / "memory" / "multi_timeframe_conflict_memory.json",
        "report_path": Path("reports") / "multi_timeframe_conflict_memory_report.txt",
    },
    "no_trade_refinement_memory": {
        "path": Path("data") / "memory" / "no_trade_refinement_memory.json",
        "report_path": Path("reports") / "no_trade_refinement_memory_report.txt",
    },
}
PHASE39_REPLAY_FIELD_GROUPS = {
    "replay_realism": (
        "replay_realism",
        "signal_age_minutes",
        "holding_period_days",
        "session_context_label",
        "entry_timing_label",
        "exit_timing_label",
        "holding_time_label",
        "decay_risk_label",
        "replay_realism_confidence",
    ),
    "semantic_replay_labels": (
        "semantic_labels",
        "trap_label",
        "fake_breakout_label",
        "liquidity_sweep_label",
        "regime_label",
        "volatility_state_label",
        "mtf_alignment_label",
        "gap_behavior_label",
        "panic_euphoria_label",
    ),
    "interpretation_engine": (
        "interpreted_outcome_label",
        "failure_reason_label",
        "success_reason_label",
        "behavioral_pattern_label",
        "emotional_market_proxy",
        "market_context_label",
        "conviction_quality_label",
        "experience_weight",
    ),
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


def _read_latest_jsonl_record_safe(path):
    meta = {
        "available": False,
        "reason": "missing",
        "line_number": None,
        "invalid_line_count": 0,
    }
    try:
        path = Path(path)
        if not path.exists():
            return {}, meta
        meta["reason"] = "empty"
        latest_record = {}
        latest_line_number = None
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                meta["reason"] = "no_valid_json_object"
                try:
                    payload = json.loads(line)
                except Exception:
                    meta["invalid_line_count"] += 1
                    continue
                if not isinstance(payload, dict):
                    meta["invalid_line_count"] += 1
                    continue
                latest_record = payload
                latest_line_number = line_number
    except Exception:
        meta["reason"] = "unreadable"
        return {}, meta
    if latest_record:
        meta["available"] = True
        meta["reason"] = "ok"
        meta["line_number"] = latest_line_number
    return latest_record, meta


def _read_csv_header_safe(path):
    try:
        path = Path(path)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as handle:
            header = handle.readline().strip()
    except Exception:
        return []
    return [item.strip() for item in header.split(",") if item.strip()]


def _parse_datetime_safe(value):
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _age_seconds_from_timestamp(value, now):
    parsed = _parse_datetime_safe(value)
    if parsed is None:
        return None
    current = as_ist_datetime(now)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=current.tzinfo)
    return max(0.0, (current - parsed.astimezone(current.tzinfo)).total_seconds())


def _path_available(path):
    if path is None:
        return False
    try:
        return Path(path).exists()
    except OSError:
        return False


def _phase39_artifact_summary(name, spec, progress):
    progress_key = spec.get("progress_key") or name
    progress_payload = progress.get(progress_key)
    artifact_path = spec.get("path")
    report_path = spec.get("report_path")
    runtime_path = spec.get("runtime_path")
    connected = (
        bool(progress_payload)
        or _path_available(artifact_path)
        or _path_available(report_path)
        or _path_available(runtime_path)
    )

    return {
        "connected": connected,
        "active": connected,
        "artifact_path": str(artifact_path).replace("\\", "/") if artifact_path else None,
        "report_path": str(report_path).replace("\\", "/") if report_path else None,
        "runtime_status_path": str(runtime_path).replace("\\", "/") if runtime_path else None,
        "progress_key": progress_key,
        "progress_present": bool(progress_payload),
        "advisory_only": True,
        "research_only": True,
        "shadow_mode": True,
    }


def _phase39_replay_field_status(jsonl_record):
    field_source = set(jsonl_record.keys())
    summaries = {}
    for group, fields in PHASE39_REPLAY_FIELD_GROUPS.items():
        present = sorted(field for field in fields if field in field_source)
        summaries[group] = {
            "active": bool(present),
            "fields_present": present,
            "fields_expected": list(fields),
            "advisory_only": True,
            "research_only": True,
            "shadow_mode": True,
        }
    return summaries


def _phase39_research_memory_observatory(now=None):
    """
    Phase 39 is visibility-only. It reads existing replay/research artifacts and
    never participates in live ranking, execution, alert filtering, or scanning.
    """
    status = _read_json_safe(HISTORICAL_REPLAY_STATUS_PATH)
    progress = _read_json_safe(HISTORICAL_REPLAY_PROGRESS_PATH)
    import_report = _read_json_safe(HISTORICAL_EXPERIENCE_REPORT_PATH)
    jsonl_record, jsonl_record_meta = _read_latest_jsonl_record_safe(HISTORICAL_EXPERIENCE_JSONL_PATH)
    replay_fields = _phase39_replay_field_status(jsonl_record)

    latest_replay_timestamp = (
        progress.get("last_completed_at_ist")
        or status.get("timestamp_ist")
        or import_report.get("generated_at")
    )
    latest_replay_record_count = progress.get("last_records_generated")
    if latest_replay_record_count is None:
        latest_replay_record_count = import_report.get("records_generated")
    stale_age_seconds = _age_seconds_from_timestamp(latest_replay_timestamp, now)
    stale_replay = stale_age_seconds is None or stale_age_seconds > PHASE39_STALE_REPLAY_SECONDS

    research_refresh = progress.get("research_memory_refresh") if isinstance(progress.get("research_memory_refresh"), dict) else {}
    maturity_engines = {}
    for name in (
        "volatility_memory",
        "trap_memory",
        "confidence_decay_memory",
        "transition_instability_memory",
        "multi_timeframe_conflict_memory",
        "no_trade_refinement_memory",
    ):
        summary = _phase39_artifact_summary(name, PHASE39_MEMORY_ARTIFACTS[name], progress)
        summary["progress_present"] = name in research_refresh
        summary["active"] = summary["connected"] or name in research_refresh
        maturity_engines[name] = summary

    adaptive_memory = _phase39_artifact_summary("adaptive_memory", PHASE39_MEMORY_ARTIFACTS["adaptive_memory"], progress)
    rl_shadow_refresh = _phase39_artifact_summary("rl_shadow_refresh", PHASE39_MEMORY_ARTIFACTS["rl_shadow_refresh"], progress)
    research_memory_refresh_active = bool(research_refresh)

    warnings = []
    if not jsonl_record_meta["available"]:
        warnings.append(f"phase39_latest_jsonl_record_{jsonl_record_meta['reason']}")
    if stale_replay:
        warnings.append("phase39_replay_artifacts_stale")
    for group, summary in replay_fields.items():
        if not summary["active"]:
            warnings.append(f"phase39_{group}_not_visible_in_latest_import")
    if not research_memory_refresh_active:
        warnings.append("phase39_research_memory_refresh_not_visible")
    if not adaptive_memory["active"]:
        warnings.append("phase39_adaptive_memory_refresh_not_visible")
    if not rl_shadow_refresh["active"]:
        warnings.append("phase39_rl_shadow_refresh_not_visible")

    safety = {
        "visibility_only": True,
        "advisory_only": True,
        "research_only": True,
        "shadow_mode": True,
        "live_rank_mutation_allowed": False,
        "scanner_changes": False,
        "broker_orders": False,
        "telegram_changes": False,
        "supabase_writes": False,
        "dashboard_changes": False,
        "execution_packet_changes": False,
        "alert_filter_changes": False,
        "live_order_behavior_changes": False,
        "autonomous_mutation": False,
    }

    return {
        "phase": "PHASE_39_RUNTIME_VISIBILITY_RESEARCH_MEMORY_OBSERVATORY",
        "name": "Runtime Visibility / Research Memory Observatory",
        "status": "WARNING" if warnings else "OK",
        "pyramid_placement": "runtime_status_visibility_only",
        "connected_to_runtime_status": True,
        "connected_to_master_controller": False,
        "affects_live_ranking_or_execution": False,
        "latest_replay_generation_timestamp": latest_replay_timestamp,
        "latest_replay_record_count": latest_replay_record_count,
        "replay_artifact_age_seconds": round(stale_age_seconds, 3) if stale_age_seconds is not None else None,
        "stale_replay_threshold_seconds": PHASE39_STALE_REPLAY_SECONDS,
        "stale_replay": stale_replay,
        "replay_status": progress.get("status") or status.get("status") or import_report.get("status") or "UNKNOWN",
        "latest_jsonl_record_status": jsonl_record_meta,
        "replay_realism_active": replay_fields["replay_realism"]["active"],
        "semantic_replay_labels_active": replay_fields["semantic_replay_labels"]["active"],
        "interpretation_engine_active": replay_fields["interpretation_engine"]["active"],
        "replay_field_visibility": replay_fields,
        "adaptive_memory_refreshed": adaptive_memory["active"],
        "adaptive_memory": adaptive_memory,
        "research_memory_refresh_active": research_memory_refresh_active,
        "research_memory_refresh_keys": sorted(research_refresh.keys()),
        "rl_shadow_refresh_active": rl_shadow_refresh["active"],
        "rl_shadow_refresh": rl_shadow_refresh,
        "experience_maturity_memory_engines_active": any(item["active"] for item in maturity_engines.values()),
        "experience_maturity_memory_engines": maturity_engines,
        "runtime_safety_summary": safety,
        "warnings": warnings,
    }


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
                "affects_live_ranking": bool(payload.get("affects_live_ranking", False)),
                "affects_execution": bool(payload.get("affects_execution", False)),
                "broker_orders": bool(payload.get("broker_orders", False)),
                "broker_mutation": bool(payload.get("broker_mutation", False)),
                "telegram_changes": bool(payload.get("telegram_changes", False)),
                "telegram_mutation": bool(payload.get("telegram_mutation", False)),
                "supabase_mutation": bool(payload.get("supabase_mutation", False)),
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
        "phase39_research_memory_observatory": _phase39_research_memory_observatory(now),
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
