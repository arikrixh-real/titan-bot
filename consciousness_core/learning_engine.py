import hashlib
from pathlib import Path

from consciousness_core.experience_utils import load_json
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = Path("data") / "consciousness_core" / "learning_directives.json"
REAL_MEMORY_PATH = Path("data") / "consciousness_core" / "real_experience_memory.json"
DAILY_REVIEW_PATH = Path("data") / "consciousness_core" / "daily_review.json"
CONFIDENCE_PATH = Path("data") / "consciousness_core" / "confidence_recalibration.json"


def _directive_id(target_engine, reason):
    digest = hashlib.sha1(f"{target_engine}|{reason}".encode("utf-8")).hexdigest()[:12]
    return f"learn_{digest}"


def _directive(target_engine, learning_type, reason, evidence, suggested_adjustment, confidence):
    return {
        "directive_id": _directive_id(target_engine, reason),
        "target_engine": target_engine,
        "learning_type": learning_type,
        "reason": reason,
        "evidence": evidence,
        "suggested_adjustment": suggested_adjustment,
        "confidence": confidence,
        "status": "LEARNED_FOR_TEST",
        "live_apply_allowed": False,
    }


def run_learning_engine(output_path=OUTPUT_PATH, **_kwargs):
    memory = load_json(REAL_MEMORY_PATH, {})
    review = load_json(DAILY_REVIEW_PATH, {})
    confidence = load_json(CONFIDENCE_PATH, {})
    directives = []

    if confidence.get("sample_size_warning") or memory.get("confidence_failure_patterns"):
        directives.append(
            _directive(
                "confidence_calibration",
                "reliability_reduction",
                "confidence calibration is weak or proxy-based",
                confidence.get("weak_calibration_evidence") or memory.get("confidence_failure_patterns", []),
                "reduce confidence trust when calibration sample size or bucket evidence is weak",
                0.76,
            )
        )
    if review.get("what_should_be_avoided_tomorrow"):
        directives.append(
            _directive(
                "no_trade_intelligence",
                "caution_increase",
                "daily review produced avoidance warnings",
                review.get("what_should_be_avoided_tomorrow"),
                "increase no-trade caution during repeated review warning",
                0.72,
            )
        )
    if any("backtesting" in item for item in review.get("what_was_missing", [])):
        directives.append(
            _directive(
                "promotion_gate",
                "validation_requirement",
                "backtesting validation evidence is insufficient",
                review.get("what_was_missing"),
                "require more validation samples before strategy promotion",
                0.82,
            )
        )
    weak_engines = review.get("which_engines_were_weak") or memory.get("engine_reliability_memory", [])
    placeholder_like = [
        item for item in weak_engines
        if "placeholder" in str(item).lower() or "missing" in str(item).lower() or "insufficient" in str(item).lower()
    ]
    if placeholder_like:
        directives.append(
            _directive(
                "runtime_engine_registry",
                "availability_guard",
                "engine evidence indicates placeholder or unavailable behavior",
                placeholder_like,
                "treat placeholder workers as unavailable",
                0.7,
            )
        )
    if review.get("what_needs_paper_testing"):
        directives.append(
            _directive(
                "backtesting_validation",
                "coverage_improvement",
                "paper testing is needed before live learning",
                review.get("what_needs_paper_testing"),
                "prioritize backtesting coverage improvement and paper-only validation",
                0.78,
            )
        )

    result = {
        "generated_at": now_ist(),
        "directive_count": len(directives),
        "directives": directives,
        "live_apply_allowed": False,
    }
    atomic_write_json(output_path, result)
    return result


if __name__ == "__main__":
    run_learning_engine()
