from pathlib import Path

from consciousness_core.experience_utils import is_loss, is_win, load_standard_reports, load_trade_rows, parse_float
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = Path("data") / "consciousness_core" / "confidence_recalibration.json"


def run_confidence_recalibration(output_path=OUTPUT_PATH, **_kwargs):
    rows = load_trade_rows()
    reports = load_standard_reports()
    confidence = reports.get("confidence", {})
    outcome_rows = [row for row in rows if is_win(row) or is_loss(row)]
    high_confidence_losses = [
        row for row in outcome_rows
        if is_loss(row) and parse_float(row.get("score") or row.get("rank_score")) >= 3.0
    ]
    sample_size = confidence.get("predicted_vs_actual", {}).get("sample_size", 0)
    calibrated_score = confidence.get("calibrated_confidence_score", 0.0)
    calibration_warning = confidence.get("calibration_warning")
    weak_evidence = []
    if sample_size < 20:
        weak_evidence.append(f"confidence sample size {sample_size} below target 20")
    if calibration_warning and calibration_warning != "NONE":
        weak_evidence.append(f"calibration warning is {calibration_warning}")
    if confidence.get("calibration_data_mode") == "PROXY":
        weak_evidence.append("confidence calibration is proxy-based")
    if high_confidence_losses:
        weak_evidence.append(f"{len(high_confidence_losses)} high-score losses found in outcomes")

    result = {
        "generated_at": now_ist(),
        "approved_for_test_only": True,
        "overconfidence_warnings": [
            {
                "warning": "high_score_loss",
                "count": len(high_confidence_losses),
                "evidence": [
                    {
                        "symbol": row.get("symbol"),
                        "score": row.get("score") or row.get("rank_score"),
                        "outcome": row.get("outcome"),
                        "pnl": row.get("realized_pnl") or row.get("pnl_points"),
                    }
                    for row in high_confidence_losses[:10]
                ],
            }
        ],
        "weak_calibration_evidence": weak_evidence,
        "confidence_adjustment_suggestions": [
            "shrink confidence until real calibration sample size reaches target",
            "penalize high-score setups after recent stop-loss evidence",
            "separate proxy calibration from real outcome calibration",
        ],
        "sample_size_warning": sample_size < 20,
        "source_calibrated_confidence_score": calibrated_score,
        "source_sample_size": sample_size,
    }
    atomic_write_json(output_path, result)
    return result


if __name__ == "__main__":
    run_confidence_recalibration()
