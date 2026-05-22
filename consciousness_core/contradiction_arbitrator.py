from pathlib import Path

from consciousness_core.institutional_utils import clamp, evidence_item, load_institutional_inputs
from consciousness_core.state import atomic_write_json, now_ist, stable_hash


OUTPUT_PATH = Path("data") / "consciousness_core" / "contradiction_arbitration.json"


def _contradiction(kind, severity, evidence, adjustment, no_trade_bias, investigation):
    explanations = _contextual_explanations(kind, evidence)
    return {
        "contradiction_id": "contradiction_" + stable_hash([kind, evidence])[:16],
        "type": kind,
        "severity": severity,
        "evidence_conflict": evidence,
        "probable_contextual_explanations": explanations,
        "resolution_summary": _resolution_summary(kind, severity, explanations),
        "recommended_confidence_adjustment": adjustment,
        "no_trade_bias": no_trade_bias,
        "investigation_needed": investigation,
    }


def _contextual_explanations(kind, evidence):
    explanations = []
    if "liquidity" in kind or any("liquidity" in str(item).lower() for item in evidence):
        explanations.append(
            {
                "factor": "liquidity/trap condition",
                "summary": "Setup strength may be occurring inside stressed liquidity, absorption, sweep, or trap conditions.",
            }
        )
    if "breadth" in kind:
        explanations.append(
            {
                "factor": "conflicting breadth",
                "summary": "Signal strength is not confirmed by broad market participation.",
            }
        )
    if "news" in kind:
        explanations.append(
            {
                "factor": "news anomaly",
                "summary": "Headline or catalyst strength may be isolated, delayed, or not yet reflected in breadth.",
            }
        )
    if "confidence" in kind:
        explanations.append(
            {
                "factor": "exhaustion condition",
                "summary": "High confidence has weak realized evidence and may reflect overextension or poor sample depth.",
            }
        )
    if "no_trade" in kind:
        explanations.append(
            {
                "factor": "regime mismatch",
                "summary": "A strong setup conflicts with a broader no-trade or unfavorable regime warning.",
            }
        )
    if "manipulation" in kind:
        explanations.append(
            {
                "factor": "liquidity/trap condition",
                "summary": "Setup quality may be distorted by fakeout, sweep, manipulation, or stop-run evidence.",
            }
        )
    if not explanations:
        explanations.append(
            {
                "factor": "volatility difference",
                "summary": "The conflicting evidence may be measured across different volatility conditions or time windows.",
            }
        )
    return explanations[:5]


def _resolution_summary(kind, severity, explanations):
    factors = ", ".join(item["factor"] for item in explanations if item.get("factor"))
    return {
        "type": kind,
        "severity": severity,
        "probable_factors": factors,
        "summary": f"{kind} likely reflects {factors}; keep response advisory and require confirmation before action.",
        "live_mutation": False,
    }


def run_contradiction_arbitrator(output_path=OUTPUT_PATH, **_kwargs):
    inputs = load_institutional_inputs()
    no_trade = inputs["no_trade"]
    confidence = inputs["confidence"]
    news = inputs["news"]
    liquidity = inputs.get("liquidity_intelligence") or {}
    manipulation = inputs.get("manipulation_intelligence") or {}
    if not liquidity:
        from consciousness_core.liquidity_intelligence import run_liquidity_intelligence

        liquidity = run_liquidity_intelligence()
    if not manipulation:
        from consciousness_core.manipulation_intelligence import run_manipulation_intelligence

        manipulation = run_manipulation_intelligence()

    setup_quality = clamp(no_trade.get("low_edge_day", {}).get("edge_score") or no_trade.get("low_edge_day", {}).get("average_recent_setup_score") or 50)
    confidence_score = clamp(confidence.get("confidence_correction", {}).get("corrected_confidence") or confidence.get("calibrated_confidence_score") or 50)
    breadth_score = clamp(no_trade.get("weak_breadth", {}).get("breadth_score") or 50)
    liquidity_stress = clamp(liquidity.get("liquidity_stress", {}).get("score") or 0)
    manipulation_score = clamp(manipulation.get("suspicion_score") or 0)
    no_trade_warning = str(no_trade.get("no_trade_warning") or "NONE").upper()
    news_score = clamp(news.get("news_intelligence_score") or 50)

    contradictions = []
    if setup_quality >= 55 and liquidity_stress >= 55:
        contradictions.append(_contradiction(
            "bullish_setups_vs_bearish_liquidity",
            "HIGH" if liquidity_stress >= 70 else "MEDIUM",
            [evidence_item("no_trade", "setup_quality", setup_quality), evidence_item("liquidity_intelligence", "liquidity_stress", liquidity_stress)],
            -15,
            "WAIT_OR_REDUCE_AGGRESSION",
            "verify participation and absorption before trusting setup quality",
        ))
    if confidence_score >= 55 and int(confidence.get("predicted_vs_actual", {}).get("sample_size") or 0) < 20:
        contradictions.append(_contradiction(
            "high_confidence_vs_weak_evidence",
            "HIGH",
            [evidence_item("confidence_calibration", "confidence_score", confidence_score), evidence_item("confidence_calibration", "sample_size", confidence.get("predicted_vs_actual", {}).get("sample_size"))],
            -20,
            "CAUTION",
            "increase realized sample evidence before promoting conviction",
        ))
    if news_score >= 60 and breadth_score < 45:
        contradictions.append(_contradiction(
            "strong_news_vs_weak_breadth",
            "MEDIUM",
            [evidence_item("news_intelligence", "news_score", news_score), evidence_item("no_trade", "breadth_score", breadth_score)],
            -10,
            "WAIT_FOR_BREADTH_CONFIRMATION",
            "check whether headline strength is isolated or broad-based",
        ))
    if setup_quality >= 55 and manipulation_score >= 45:
        contradictions.append(_contradiction(
            "good_setup_vs_manipulation_risk",
            "HIGH" if manipulation_score >= 65 else "MEDIUM",
            [evidence_item("no_trade", "setup_quality", setup_quality), evidence_item("manipulation_intelligence", "suspicion_score", manipulation_score)],
            -15,
            "WAIT_FOR_CONFIRMATION",
            "inspect trap and sweep signatures before accepting breakout evidence",
        ))
    if setup_quality >= 55 and no_trade_warning not in {"NONE", ""}:
        contradictions.append(_contradiction(
            "strong_setup_vs_no_trade_warning",
            "HIGH",
            [evidence_item("no_trade", "setup_quality", setup_quality), evidence_item("no_trade", "warning", no_trade_warning)],
            -20,
            "NO_TRADE_BIAS",
            "resolve no-trade reason before treating the setup as actionable",
        ))

    payload = {
        "generated_at": now_ist(),
        "contradictions": contradictions,
        "explanation_summaries": [
            item.get("resolution_summary")
            for item in contradictions
            if isinstance(item.get("resolution_summary"), dict)
        ],
        "contradiction_count": len(contradictions),
        "overall_severity": "HIGH" if any(item["severity"] == "HIGH" for item in contradictions) else "MEDIUM" if contradictions else "LOW",
        "aggregate_confidence_adjustment": sum(item["recommended_confidence_adjustment"] for item in contradictions),
        "safety_scope": "read_only_recommendation_only",
    }
    atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    run_contradiction_arbitrator()
