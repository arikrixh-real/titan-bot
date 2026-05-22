from consciousness_core.deduplication import SEVERITY_RANK, append_evidence, stronger_label
from consciousness_core.experience_utils import safe_float
from consciousness_core.state import stable_hash


IMPORTANT_PLACEHOLDER_WORKERS = {
    "learning_engine",
    "experience_memory",
    "scenario_simulation",
    "daily_review",
    "replay_batch",
    "next_day_preparation",
}

LAST_DUPLICATES_MERGED = 0


def _weakness(kind, severity, affected_engine, evidence, investigation, action):
    basis = {
        "kind": kind,
        "affected_engine": affected_engine,
        "evidence_hash": stable_hash(evidence),
    }
    return {
        "weakness_id": "weakness_" + stable_hash(basis)[:16],
        "type": kind,
        "evidence": evidence,
        "severity": severity,
        "affected_engine": affected_engine,
        "recommended_investigation": investigation,
        "proposed_action": action,
    }


def _text(value):
    return str(value or "").upper()


def get_last_duplicates_merged():
    return LAST_DUPLICATES_MERGED


def _cluster_key(weakness):
    return (
        str(weakness.get("affected_engine") or "").strip().lower(),
        str(weakness.get("type") or "").strip().lower(),
        str(weakness.get("proposed_action") or "").strip().lower(),
    )


def _cluster_weaknesses(weaknesses):
    global LAST_DUPLICATES_MERGED
    LAST_DUPLICATES_MERGED = 0
    clustered = {}
    for weakness in weaknesses:
        key = _cluster_key(weakness)
        current = clustered.get(key)
        if not current:
            clustered[key] = weakness
            continue
        LAST_DUPLICATES_MERGED += 1
        current["severity"] = stronger_label(current.get("severity"), weakness.get("severity"), SEVERITY_RANK)
        current["evidence"] = append_evidence(current.get("evidence"), weakness.get("evidence"))
        current["recommended_investigation"] = current.get("recommended_investigation") or weakness.get("recommended_investigation")
    return list(clustered.values())


def hunt_weaknesses(observation_packet, reflection=None):
    weaknesses = []
    observations = observation_packet.get("observations", [])
    for observation in observations:
        obs_type = observation.get("type")
        metric = observation.get("metric")
        value = observation.get("value")
        numeric_value = safe_float(value)
        entity = observation.get("entity") or observation.get("source")
        severity = str(observation.get("severity") or "LOW").upper()
        evidence = [observation]

        if obs_type == "worker_health" and metric == "worker_status" and _text(value) in {"ERROR", "TIMEOUT", "MISSING_HANDLER"}:
            weaknesses.append(
                _weakness(
                    "worker_failure",
                    "HIGH" if _text(value) in {"ERROR", "TIMEOUT"} else "MEDIUM",
                    entity,
                    evidence,
                    f"Inspect {entity} runtime logs, last_error, timeout path, and dependency availability.",
                    "stabilize worker execution before trusting downstream intelligence from this engine",
                )
            )
        if obs_type == "worker_health" and metric in {"error_count", "timeout_count"} and int(value or 0) > 0:
            weaknesses.append(
                _weakness(
                    "repeated_worker_failures",
                    "HIGH" if int(value or 0) >= 2 else "MEDIUM",
                    entity,
                    evidence,
                    f"Review why {entity} has {metric}={value}.",
                    "add targeted diagnostics and reduce dependence on stale outputs until stable",
                )
            )
        if obs_type == "intelligence_state" and metric == "last_status" and _text(value) in {"SKIPPED_PLACEHOLDER", "MISSING_HANDLER", "NOT_IMPLEMENTED"}:
            weaknesses.append(
                _weakness(
                    "placeholder_important_worker",
                    "MEDIUM",
                    entity,
                    evidence,
                    f"Confirm whether {entity} is intentionally placeholder or blocking intelligence coverage.",
                    "replace placeholder worker with a real read-only implementation or lower its strategic weight",
                )
            )
        if entity in IMPORTANT_PLACEHOLDER_WORKERS and metric == "last_status" and _text(value) in {"SKIPPED_PLACEHOLDER", "NOT_IMPLEMENTED"}:
            weaknesses.append(
                _weakness(
                    "placeholder_important_worker",
                    "HIGH",
                    entity,
                    evidence,
                    f"{entity} is an important intelligence worker but currently placeholder.",
                    "implement the worker or mark its outputs unavailable so strategy does not assume coverage",
                )
            )
        if obs_type == "missing_critical_report":
            weaknesses.append(
                _weakness(
                    "missing_critical_report",
                    "HIGH",
                    entity,
                    evidence,
                    f"Find why required source {value} is absent.",
                    "restore report generation or explicitly mark the source unavailable in consuming workers",
                )
            )
        if metric in {"calibrated_confidence_score", "reliability_score"} and numeric_value is not None and numeric_value < 40:
            weaknesses.append(
                _weakness(
                    "weak_confidence_calibration",
                    "MEDIUM",
                    "confidence_calibration",
                    evidence,
                    "Compare predicted confidence against closed trade outcomes and calibration sample size.",
                    "reduce confidence contribution until calibration has enough reliable outcome samples",
                )
            )
        if metric == "high_confidence_loss":
            weaknesses.append(
                _weakness(
                    "high_confidence_loss",
                    "HIGH",
                    "confidence_model",
                    evidence,
                    "Study why a high-score trade reached stop loss or negative PnL.",
                    "require extra sector/regime confirmation after similar high-confidence losses",
                )
            )
        if obs_type == "backtest_validation" and metric == "validation_status" and _text(value) in {"NO_DATA", "NO_TEST_DATA", "FAILED"}:
            weaknesses.append(
                _weakness(
                    "poor_backtesting_validation",
                    "MEDIUM",
                    "backtesting",
                    evidence,
                    "Check why validation lacks enough historical or out-of-sample samples.",
                    "block promotion of strategy changes until backtest or paper validation is populated",
                )
            )
        if obs_type == "backtest_validation" and metric in {"sample_size", "quality_score", "validation_score"} and safe_float(value, 0.0) <= 0:
            weaknesses.append(
                _weakness(
                    "poor_backtesting_validation",
                    "MEDIUM",
                    "backtesting",
                    evidence,
                    f"{metric} is zero in validation evidence.",
                    "require more sample data before approving strategy parameter changes",
                )
            )
        if obs_type == "no_trade" and (severity == "HIGH" or _text(value) not in {"NONE", "ALLOW", "FALSE"}):
            weaknesses.append(
                _weakness(
                    "no_trade_warning",
                    severity,
                    "no_trade",
                    evidence,
                    "Inspect no-trade trigger and cross-check with market regime/news/contradiction evidence.",
                    "increase no-trade protection in test mode when the same warning recurs",
                )
            )
        if "auto_repair" in observation.get("source", "") and metric in {"severity_score", "auto_repair_score"}:
            if (metric == "severity_score" and safe_float(value, 0.0) >= 20) or (metric == "auto_repair_score" and safe_float(value, 100.0) < 70):
                weaknesses.append(
                    _weakness(
                        "auto_repair_issue",
                        "MEDIUM",
                        "auto_repair",
                        evidence,
                        "Review diagnostic items and suspected modules from auto-repair output.",
                        "add compile/import checks for suspected modules before runtime promotion",
                    )
                )
        if metric == "total_closed_trades" and int(value or 0) < 5:
            weaknesses.append(
                _weakness(
                    "evolution_stagnation",
                    "MEDIUM",
                    "evolution_engine",
                    evidence,
                    "Evolution has too few closed trades to justify confident parameter shifts.",
                    "keep strategy changes in study/test queue until enough closed trades accumulate",
                )
            )
        if metric == "win_rate" and numeric_value is not None and numeric_value < 0.5:
            weaknesses.append(
                _weakness(
                    "strategy_underperformance",
                    "MEDIUM",
                    "strategy_memory",
                    evidence,
                    "Review losing symbols/sides/setups and compare winner/loser score distributions.",
                    "tighten filters for underperforming setup clusters in backtest only",
                )
            )

    for message in (reflection or {}).get("confidence_warnings", []):
        weaknesses.append(
            _weakness(
                "confidence_warning",
                "MEDIUM",
                "confidence_calibration",
                [{"source": "reflection_engine", "message": message}],
                "Validate confidence warning against actual outcomes.",
                "avoid increasing confidence weights until warning is resolved",
            )
        )
    for message in (reflection or {}).get("regime_warnings", []):
        weaknesses.append(
            _weakness(
                "regime_warning",
                "MEDIUM",
                "market_regime_update",
                [{"source": "reflection_engine", "message": message}],
                "Check regime warning against no-trade and trade outcome evidence.",
                "tighten regime filter in test mode only",
            )
        )
    if observation_packet.get("missing_patterns"):
        weaknesses.append(
            _weakness(
                "missing_optional_data",
                "LOW",
                "data_collector",
                [{"missing_patterns": observation_packet["missing_patterns"]}],
                "Separate expected absent optional sources from broken pipelines.",
                "do not infer strategy changes from unavailable optional data",
            )
        )
    return _cluster_weaknesses(weaknesses)[:100]
