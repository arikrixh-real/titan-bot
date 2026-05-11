"""
TITAN Phase 34 - Confidence Calibration Engine

Tracks predicted vs actual outcomes and adjusts confidence with reliability,
sample-size shrinkage, decay, and overconfidence controls. Never places orders.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List


REPORT_PATH = os.path.join("data", "confidence_calibration", "latest_confidence_calibration_report.json")


def safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return float(default)
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        return float(value)
    except Exception:
        return float(default)


def safe_text(value, default=""):
    try:
        if value is None:
            return str(default)
        return str(value).strip()
    except Exception:
        return str(default)


def safe_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    return [value]


def clamp(value, min_value=0.0, max_value=100.0):
    try:
        value = safe_float(value, min_value)
        return max(float(min_value), min(float(max_value), value))
    except Exception:
        return float(min_value)


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _raw(setup):
    setup = _as_dict(setup)
    return setup.get("raw") if isinstance(setup.get("raw"), dict) else {}


def _field(setup, key, default=None):
    setup = _as_dict(setup)
    raw = _raw(setup)
    return setup.get(key, raw.get(key, default))


def _symbol(setup):
    setup = _as_dict(setup)
    raw = _raw(setup)
    return safe_text(setup.get("symbol") or setup.get("stock") or raw.get("symbol") or raw.get("stock") or "UNKNOWN")


def _confidence_from_setup(setup):
    value = _field(setup, "confidence_score", _field(setup, "confidence_after_debate", _field(setup, "confidence")))
    text = safe_text(value).upper()
    if text == "HIGH":
        return 80.0
    if text == "MEDIUM":
        return 60.0
    if text == "LOW":
        return 35.0
    if value not in (None, ""):
        return clamp(value)
    for key in ["reflection_score", "debate_score", "probability_score", "final_score", "score"]:
        if _field(setup, key) is not None:
            return clamp(_field(setup, key))
    return 50.0


def _actual_success(item):
    item = _as_dict(item)
    result = safe_text(item.get("actual") or item.get("result") or item.get("outcome") or item.get("status")).upper()
    pnl = safe_float(item.get("pnl") or item.get("pnl_pct") or item.get("profit"), 0.0)
    if result in {"WIN", "PROFIT", "SUCCESS", "TARGET", "TP", "TRUE", "1"}:
        return 1.0
    if result in {"LOSS", "FAILED", "STOP", "STOP_LOSS", "SL", "FALSE", "0"}:
        return 0.0
    if pnl > 0.0:
        return 1.0
    if pnl < 0.0:
        return 0.0
    value = item.get("actual_success")
    if value is not None:
        return 1.0 if safe_float(value, 0.0) >= 0.5 else 0.0
    return None


def _prediction_confidence(item):
    item = _as_dict(item)
    for key in ["predicted_confidence", "confidence", "confidence_score", "probability", "predicted_probability", "score"]:
        value = item.get(key)
        if value is not None:
            return clamp(value)
    return None


def _paired_records(prediction_history=None, outcome_history=None):
    predictions = [item for item in safe_list(prediction_history) if isinstance(item, dict)]
    outcomes = [item for item in safe_list(outcome_history) if isinstance(item, dict)]
    if not predictions and outcomes:
        predictions = outcomes
    if not outcomes and predictions:
        outcomes = predictions

    by_id: Dict[str, Dict[str, Any]] = {}
    for item in outcomes:
        key = safe_text(item.get("id") or item.get("trade_id") or item.get("symbol") or len(by_id))
        by_id[key] = item

    pairs = []
    for index, pred in enumerate(predictions):
        key = safe_text(pred.get("id") or pred.get("trade_id") or pred.get("symbol") or index)
        outcome = by_id.get(key)
        if outcome is None and index < len(outcomes):
            outcome = outcomes[index]
        confidence = _prediction_confidence(pred)
        actual = _actual_success(outcome or pred)
        if confidence is not None and actual is not None:
            merged = dict(pred)
            if isinstance(outcome, dict):
                merged.update({f"outcome_{k}": v for k, v in outcome.items()})
            pairs.append({"confidence": confidence, "actual": actual, "record": merged})
    return pairs


def normalize_calibration_inputs(setup=None, prediction_history=None, outcome_history=None, context=None):
    setup = _as_dict(setup)
    context = _as_dict(context)
    predictions = safe_list(prediction_history or context.get("prediction_history") or context.get("predictions"))
    outcomes = safe_list(outcome_history or context.get("outcome_history") or context.get("trade_results") or context.get("closed_trades"))
    return {
        "setup": dict(setup),
        "context": dict(context),
        "prediction_history": predictions,
        "outcome_history": outcomes,
        "pairs": _paired_records(predictions, outcomes),
        "symbol": _symbol(setup),
        "base_confidence": _confidence_from_setup(setup),
    }


def _data_mode(setup, prediction_history, outcome_history, context):
    pairs = _paired_records(prediction_history, outcome_history)
    setup = _as_dict(setup)
    context = _as_dict(context)
    if len(pairs) >= 3:
        return "REAL_CALIBRATION"
    if any(_field(setup, key) not in (None, "", [], {}) for key in ["confidence", "confidence_score", "score", "final_score", "probability_score"]) or context:
        return "PROXY"
    if pairs:
        return "PROXY"
    return "INSUFFICIENT"


def track_predicted_vs_actual(prediction_history=None, outcome_history=None):
    pairs = _paired_records(prediction_history, outcome_history)
    if not pairs:
        return {"sample_size": 0, "accuracy": 0.0, "mean_confidence": 0.0, "mean_actual": 0.0, "calibration_error": 0.0}
    mean_conf = sum(item["confidence"] for item in pairs) / len(pairs)
    mean_actual = sum(item["actual"] * 100.0 for item in pairs) / len(pairs)
    hits = 0
    for item in pairs:
        predicted_win = item["confidence"] >= 50.0
        actual_win = item["actual"] >= 0.5
        if predicted_win == actual_win:
            hits += 1
    accuracy = (hits / float(len(pairs))) * 100.0
    return {
        "sample_size": len(pairs),
        "accuracy": round(clamp(accuracy), 2),
        "mean_confidence": round(clamp(mean_conf), 2),
        "mean_actual": round(clamp(mean_actual), 2),
        "calibration_error": round(clamp(abs(mean_conf - mean_actual)), 2),
    }


def build_calibration_curve(prediction_history=None, outcome_history=None):
    pairs = _paired_records(prediction_history, outcome_history)
    buckets = []
    for low in range(0, 100, 20):
        high = low + 20
        bucket = [item for item in pairs if low <= item["confidence"] < high or (high == 100 and item["confidence"] == 100)]
        actual_rate = (sum(item["actual"] for item in bucket) / len(bucket) * 100.0) if bucket else 0.0
        avg_conf = (sum(item["confidence"] for item in bucket) / len(bucket)) if bucket else 0.0
        buckets.append(
            {
                "bucket": f"{low}-{high}",
                "count": len(bucket),
                "avg_confidence": round(clamp(avg_conf), 2),
                "actual_win_rate": round(clamp(actual_rate), 2),
            }
        )
    populated = [b for b in buckets if b["count"] > 0]
    curve_error = 0.0
    if populated:
        curve_error = sum(abs(b["avg_confidence"] - b["actual_win_rate"]) for b in populated) / len(populated)
    return {"buckets": buckets, "populated_bucket_count": len(populated), "curve_error": round(clamp(curve_error), 2)}


def calculate_confidence_decay(setup=None, context=None):
    context = _as_dict(context)
    age = safe_float(_field(setup, "signal_age_minutes", context.get("signal_age_minutes")), 0.0)
    volatility = safe_float(context.get("volatility_score") or _field(setup, "volatility_score"), 0.0)
    decay = 0.0
    if age > 30.0:
        decay += min(25.0, (age - 30.0) / 6.0)
    if volatility >= 70.0:
        decay += 8.0
    return {"signal_age_minutes": age, "volatility_score": volatility, "decay_points": round(clamp(decay, 0.0, 40.0), 2)}


def calculate_overconfidence_penalty(setup=None, outcome_history=None):
    confidence = _confidence_from_setup(setup)
    outcomes = [item for item in safe_list(outcome_history) if isinstance(item, dict)]
    recent = outcomes[-10:] if outcomes else []
    losses = sum(1 for item in recent if _actual_success(item) == 0.0)
    loss_rate = (losses / float(len(recent)) * 100.0) if recent else 0.0
    penalty = 0.0
    if confidence >= 75.0 and loss_rate >= 50.0:
        penalty += 24.0
    elif confidence >= 70.0 and loss_rate >= 40.0:
        penalty += 14.0
    if safe_text(_field(setup, "reflection_warning")).upper() in {"REVIEW", "SKIP"}:
        penalty += 8.0
    return {
        "base_confidence": round(confidence, 2),
        "recent_sample_size": len(recent),
        "recent_loss_rate": round(clamp(loss_rate), 2),
        "penalty_points": round(clamp(penalty, 0.0, 45.0), 2),
    }


def calculate_low_sample_shrinkage(prediction_history=None, context=None):
    sample_size = len([item for item in safe_list(prediction_history) if isinstance(item, dict)])
    target = safe_float(_as_dict(context).get("min_calibration_samples"), 20.0)
    if sample_size >= target:
        shrink = 0.0
    else:
        shrink = (1.0 - (sample_size / max(target, 1.0))) * 20.0
    return {"sample_size": sample_size, "target_sample_size": int(target), "shrinkage_points": round(clamp(shrink, 0.0, 20.0), 2)}


def calculate_reliability_score(prediction_history=None, outcome_history=None):
    pva = track_predicted_vs_actual(prediction_history, outcome_history)
    curve = build_calibration_curve(prediction_history, outcome_history)
    sample = safe_float(pva.get("sample_size"), 0.0)
    if sample <= 0:
        return 50.0
    sample_factor = clamp((sample / 20.0) * 100.0)
    reliability = (
        safe_float(pva.get("accuracy"), 0.0) * 0.40
        + (100.0 - safe_float(pva.get("calibration_error"), 0.0)) * 0.35
        + (100.0 - safe_float(curve.get("curve_error"), 0.0)) * 0.15
        + sample_factor * 0.10
    )
    return round(clamp(reliability), 2)


def calculate_regime_specific_calibration(prediction_history=None, outcome_history=None, context=None):
    context = _as_dict(context)
    regime = safe_text(context.get("market_regime") or context.get("regime") or "UNKNOWN").upper()
    pairs = _paired_records(prediction_history, outcome_history)
    filtered = []
    for item in pairs:
        record = _as_dict(item.get("record"))
        item_regime = safe_text(record.get("regime") or record.get("market_regime") or record.get("outcome_regime")).upper()
        if item_regime and item_regime == regime:
            filtered.append(item)
    sample = filtered or pairs
    actual_rate = (sum(item["actual"] for item in sample) / len(sample) * 100.0) if sample else 50.0
    avg_conf = (sum(item["confidence"] for item in sample) / len(sample)) if sample else 50.0
    return {
        "regime": regime,
        "sample_size": len(sample),
        "matched_current_regime": bool(filtered),
        "avg_confidence": round(clamp(avg_conf), 2),
        "actual_win_rate": round(clamp(actual_rate), 2),
        "regime_calibration_error": round(clamp(abs(avg_conf - actual_rate)), 2),
    }


def calculate_strategy_specific_calibration(prediction_history=None, outcome_history=None, setup=None):
    strategy = safe_text(_field(setup, "strategy") or _field(setup, "setup_type") or _field(setup, "pattern") or "UNKNOWN").upper()
    pairs = _paired_records(prediction_history, outcome_history)
    filtered = []
    for item in pairs:
        record = _as_dict(item.get("record"))
        item_strategy = safe_text(record.get("strategy") or record.get("setup_type") or record.get("pattern")).upper()
        if item_strategy and item_strategy == strategy:
            filtered.append(item)
    sample = filtered or pairs
    actual_rate = (sum(item["actual"] for item in sample) / len(sample) * 100.0) if sample else 50.0
    avg_conf = (sum(item["confidence"] for item in sample) / len(sample)) if sample else 50.0
    return {
        "strategy": strategy,
        "sample_size": len(sample),
        "matched_current_strategy": bool(filtered),
        "avg_confidence": round(clamp(avg_conf), 2),
        "actual_win_rate": round(clamp(actual_rate), 2),
        "strategy_calibration_error": round(clamp(abs(avg_conf - actual_rate)), 2),
    }


def calculate_uncertainty_awareness(setup=None, context=None):
    uncertainty = safe_float(_field(setup, "probability_uncertainty", _field(setup, "uncertainty_score", 0.0)), 0.0)
    warnings = sum(
        1
        for key in ["reflection_warning", "debate_warning", "scenario_warning", "news_warning", "calendar_warning"]
        if safe_text(_field(setup, key)).upper() in {"REVIEW", "WAIT", "SKIP"}
    )
    score = clamp(80.0 - warnings * 8.0 - max(0.0, uncertainty - 50.0) * 0.4)
    return {"uncertainty_score": round(clamp(uncertainty), 2), "warning_count": warnings, "uncertainty_awareness_score": round(score, 2)}


def calculate_confidence_correction(setup=None, prediction_history=None, outcome_history=None, context=None):
    base = _confidence_from_setup(setup)
    reliability = calculate_reliability_score(prediction_history, outcome_history)
    decay = calculate_confidence_decay(setup, context)
    penalty = calculate_overconfidence_penalty(setup, outcome_history)
    shrinkage = calculate_low_sample_shrinkage(prediction_history, context)
    uncertainty = calculate_uncertainty_awareness(setup, context)
    reliable_adjustment = (reliability - 50.0) * 0.20
    corrected = base + reliable_adjustment
    corrected -= safe_float(decay.get("decay_points"), 0.0)
    corrected -= safe_float(penalty.get("penalty_points"), 0.0)
    corrected -= safe_float(shrinkage.get("shrinkage_points"), 0.0)
    corrected += (safe_float(uncertainty.get("uncertainty_awareness_score"), 50.0) - 50.0) * 0.05
    return {
        "base_confidence": round(clamp(base), 2),
        "reliability_adjustment": round(reliable_adjustment, 2),
        "decay_points": decay.get("decay_points", 0.0),
        "overconfidence_penalty_points": penalty.get("penalty_points", 0.0),
        "low_sample_shrinkage_points": shrinkage.get("shrinkage_points", 0.0),
        "corrected_confidence": round(clamp(corrected), 2),
    }


def _save_report(report):
    try:
        os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
    except Exception:
        pass


def build_confidence_calibration_report(setup=None, prediction_history=None, outcome_history=None, context=None):
    setup = _as_dict(setup)
    context = _as_dict(context)
    prediction_history = safe_list(prediction_history or context.get("prediction_history") or context.get("predictions"))
    outcome_history = safe_list(outcome_history or context.get("outcome_history") or context.get("trade_results") or context.get("closed_trades"))
    mode = _data_mode(setup, prediction_history, outcome_history, context)
    explanations: List[str] = []

    pva = track_predicted_vs_actual(prediction_history, outcome_history)
    curve = build_calibration_curve(prediction_history, outcome_history)
    decay = calculate_confidence_decay(setup, context)
    penalty = calculate_overconfidence_penalty(setup, outcome_history)
    shrinkage = calculate_low_sample_shrinkage(prediction_history, context)
    reliability = calculate_reliability_score(prediction_history, outcome_history)
    regime_calibration = calculate_regime_specific_calibration(prediction_history, outcome_history, context)
    strategy_calibration = calculate_strategy_specific_calibration(prediction_history, outcome_history, setup)
    uncertainty = calculate_uncertainty_awareness(setup, context)
    correction = calculate_confidence_correction(setup, prediction_history, outcome_history, context)

    calibrated = safe_float(correction.get("corrected_confidence"), 50.0)
    over_penalty = safe_float(penalty.get("penalty_points"), 0.0)
    low_sample = safe_float(shrinkage.get("shrinkage_points"), 0.0)
    warning = "NONE"
    if over_penalty >= 30.0 and reliability < 35.0:
        warning = "SKIP"
    elif over_penalty >= 12.0 or low_sample >= 12.0 or reliability < 45.0:
        warning = "REVIEW"

    if mode == "INSUFFICIENT":
        calibrated = 50.0
        bias = "REVIEW"
        warning = "REVIEW"
        explanations.append("Insufficient calibration history; neutral non-blocking confidence applied.")
    else:
        if warning == "SKIP":
            calibrated -= 18.0
            explanations.append("Severe overconfidence with weak reliability reduced calibrated confidence.")
        elif warning in {"REVIEW", "WAIT"}:
            calibrated -= 5.0
            explanations.append("Calibration requested review; small ranking penalty applied.")
        if reliability >= 65.0 and over_penalty < 10.0:
            bias = "RELIABLE"
        elif over_penalty >= 12.0:
            bias = "OVERCONFIDENT"
        elif safe_float(correction.get("base_confidence"), 50.0) < safe_float(pva.get("mean_actual"), 50.0) - 15.0:
            bias = "UNDERCONFIDENT"
        else:
            bias = "REVIEW"
        explanations.append(f"{mode} confidence calibration used available prediction/outcome evidence.")

    calibrated = round(clamp(calibrated), 2)
    report = {
        "symbol": _symbol(setup),
        "calibration_data_mode": mode,
        "predicted_vs_actual": pva,
        "calibration_curve": curve,
        "confidence_decay": decay,
        "overconfidence_penalty": penalty,
        "low_sample_shrinkage": shrinkage,
        "reliability_score": reliability,
        "regime_specific_calibration": regime_calibration,
        "strategy_specific_calibration": strategy_calibration,
        "uncertainty_awareness": uncertainty,
        "confidence_correction": correction,
        "calibrated_confidence_score": calibrated,
        "calibration_bias": bias,
        "calibration_warning": warning if warning in {"NONE", "WAIT", "SKIP", "REVIEW"} else "REVIEW",
        "live_order_allowed": False,
        "explanations": explanations,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    _save_report(report)
    return report


if __name__ == "__main__":
    sample_setup = {
        "symbol": "TITAN",
        "confidence": "HIGH",
        "score": 72,
        "strategy": "breakout",
        "signal_age_minutes": 12,
        "reflection_warning": "NONE",
    }
    sample_prediction_history = [
        {"id": "1", "symbol": "TITAN", "predicted_confidence": 72, "strategy": "breakout", "regime": "trend"},
        {"id": "2", "symbol": "TITAN", "predicted_confidence": 81, "strategy": "breakout", "regime": "trend"},
        {"id": "3", "symbol": "ABC", "predicted_confidence": 63, "strategy": "reversal", "regime": "range"},
        {"id": "4", "symbol": "XYZ", "predicted_confidence": 58, "strategy": "breakout", "regime": "trend"},
    ]
    sample_outcome_history = [
        {"id": "1", "result": "WIN", "pnl_pct": 1.2},
        {"id": "2", "result": "LOSS", "pnl_pct": -0.7},
        {"id": "3", "result": "WIN", "pnl_pct": 0.8},
        {"id": "4", "result": "WIN", "pnl_pct": 1.0},
    ]
    sample_context = {"market_regime": "trend", "min_calibration_samples": 8, "volatility_score": 42}
    print(
        json.dumps(
            build_confidence_calibration_report(
                sample_setup,
                sample_prediction_history,
                sample_outcome_history,
                sample_context,
            ),
            indent=2,
            sort_keys=True,
        )
    )
