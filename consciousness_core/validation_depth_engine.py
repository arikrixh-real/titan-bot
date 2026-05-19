from consciousness_core.experience_utils import load_json, load_standard_reports, load_trade_rows
from consciousness_core.institutional_utils import CORE_DIR, clamp
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = CORE_DIR / "validation_depth.json"


def run_validation_depth_engine(output_path=OUTPUT_PATH, **_kwargs):
    reports = load_standard_reports()
    sandbox = load_json(CORE_DIR / "sandbox_results.json", [])
    paper = load_json(CORE_DIR / "paper_testing_ecosystem.json", {})
    backtesting = reports.get("backtesting", {})
    confidence = load_json(CORE_DIR / "confidence_recalibration.json", {}) or reports.get("confidence", {})
    meta_learning = load_json(CORE_DIR / "meta_learning.json", {})
    trades = load_trade_rows()

    sandbox_count = len(sandbox)
    trade_count = len(trades)
    active_paper = len(paper.get("active_paper_tests", []))
    current_sample = int(paper.get("current_sample_size") or trade_count)
    required_sample = int(paper.get("required_sample_size") or 50)
    confidence_sample = int(confidence.get("predicted_vs_actual", {}).get("sample_size") or 0)

    evidence_sample_score = clamp((trade_count / 100) * 100, 0, 100)
    out_of_sample_score = clamp(35 if backtesting else 0)
    if backtesting and "out_of_sample" in str(backtesting).lower():
        out_of_sample_score = 65
    paper_test_score = clamp((current_sample / max(1, required_sample)) * 80 + active_paper * 3, 0, 100)
    statistical_confidence = clamp((confidence_sample / 50) * 70 + min(20, sandbox_count * 2), 0, 100)
    validation_depth_score = round(
        evidence_sample_score * 0.25
        + out_of_sample_score * 0.2
        + paper_test_score * 0.3
        + statistical_confidence * 0.25,
        2,
    )

    blockers = []
    if trade_count < 50:
        blockers.append("trade outcome evidence below 50 samples")
    if confidence_sample < 20:
        blockers.append("confidence calibration evidence below 20 samples")
    if paper_test_score < 70:
        blockers.append("paper-test depth below promotion threshold")
    if out_of_sample_score < 60:
        blockers.append("out-of-sample validation not strong enough")
    if meta_learning.get("learning_status") in {"IMMATURE", "WEAK"}:
        blockers.append("meta-learning status is not mature")

    promotion_allowed = validation_depth_score >= 85 and not blockers
    payload = {
        "generated_at": now_ist(),
        "safety_scope": "read_only_recommendation_only",
        "validation_depth_score": validation_depth_score,
        "evidence_sample_score": round(evidence_sample_score, 2),
        "out_of_sample_score": round(out_of_sample_score, 2),
        "paper_test_score": round(paper_test_score, 2),
        "statistical_confidence": round(statistical_confidence, 2),
        "promotion_allowed": bool(promotion_allowed),
        "blockers": blockers
        or [
            "live promotion still requires human review and external governance despite sufficient evidence",
        ],
        "evidence_counts": {
            "sandbox_results": sandbox_count,
            "trade_outcomes": trade_count,
            "active_paper_tests": active_paper,
            "paper_current_sample_size": current_sample,
            "paper_required_sample_size": required_sample,
            "confidence_sample_size": confidence_sample,
        },
    }
    atomic_write_json(output_path, payload)
    return payload
