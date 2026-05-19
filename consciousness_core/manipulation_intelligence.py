from pathlib import Path

from consciousness_core.institutional_utils import clamp, evidence_item, has_terms, load_institutional_inputs, recommendation
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = Path("data") / "consciousness_core" / "manipulation_intelligence.json"


def _pattern(name, active, score, evidence, warning):
    return {
        "pattern": name,
        "active": bool(active),
        "score": round(clamp(score), 2),
        "evidence": evidence,
        "warning": warning,
    }


def run_manipulation_intelligence(output_path=OUTPUT_PATH, **_kwargs):
    inputs = load_institutional_inputs()
    liquidity = inputs["liquidity_map"]
    micro = inputs["microstructure"]
    news = inputs["news"]
    no_trade = inputs["no_trade"]
    confidence = inputs["confidence"]
    weaknesses = inputs["weaknesses"]

    stop_clusters = liquidity.get("stop_loss_clusters", {})
    trap_zones = liquidity.get("breakout_trap_zones", {})
    sweeps = micro.get("liquidity_sweeps", {})
    spoof = micro.get("spoof_like_detection", {})
    positive_exhaustion = news.get("positive_news_exhaustion", {})
    weak_news = str(news.get("news_warning") or "").upper() == "REVIEW" or news.get("news_reaction_memory", {}).get("memory_confidence", 0) == 0
    contradiction_trap = no_trade.get("contradiction_overload", {}).get("is_contradiction_overload") or has_terms(weaknesses, ("contradiction", "conflict"))

    patterns = [
        _pattern(
            "stop_hunt_signature",
            stop_clusters.get("active") or sweeps.get("active"),
            max(clamp(stop_clusters.get("cluster_risk_score")), clamp(sweeps.get("risk_score"))),
            [
                evidence_item("liquidity_map", "stop_loss_clusters", stop_clusters),
                evidence_item("microstructure", "liquidity_sweeps", sweeps),
            ],
            "possible sweep through clustered stops before direction confirms",
        ),
        _pattern(
            "fake_breakout",
            trap_zones.get("active"),
            trap_zones.get("trap_risk_score") or 0.0,
            [evidence_item("liquidity_map", "breakout_trap_zones", trap_zones)],
            "breakout quality is suspect near mapped trap zones",
        ),
        _pattern(
            "liquidity_trap",
            liquidity.get("liquidity_warning") == "REVIEW" or liquidity.get("liquidity_data_mode") == "INSUFFICIENT",
            55.0 if liquidity.get("liquidity_warning") == "REVIEW" else 35.0,
            [evidence_item("liquidity_map", "warning", liquidity.get("liquidity_warning"))],
            "liquidity evidence is too weak for aggressive conviction",
        ),
        _pattern(
            "exhaustion_trap",
            positive_exhaustion.get("active"),
            positive_exhaustion.get("risk_score") or 0.0,
            [evidence_item("news_intelligence", "positive_news_exhaustion", positive_exhaustion)],
            "positive news may already be crowded or exhausted",
        ),
        _pattern(
            "engineered_reversal",
            spoof.get("active") or micro.get("hf_volatility_burst", {}).get("active"),
            max(clamp(spoof.get("risk_score")), clamp(micro.get("hf_volatility_burst", {}).get("risk_score"))),
            [
                evidence_item("microstructure", "spoof_like_detection", spoof),
                evidence_item("microstructure", "hf_volatility_burst", micro.get("hf_volatility_burst", {})),
            ],
            "microstructure reversal risk should reduce confidence",
        ),
        _pattern(
            "contradiction_trap",
            contradiction_trap,
            no_trade.get("contradiction_overload", {}).get("danger_score") or (50.0 if contradiction_trap else 0.0),
            [evidence_item("no_trade", "contradiction_overload", no_trade.get("contradiction_overload", {}))],
            "setup evidence is internally conflicted",
        ),
        _pattern(
            "low_confidence_news_trap",
            weak_news,
            60.0 if weak_news else 0.0,
            [
                evidence_item("news_intelligence", "news_warning", news.get("news_warning")),
                evidence_item("confidence_calibration", "calibration_warning", confidence.get("calibration_warning")),
            ],
            "headline context has low memory confidence and should not justify aggression",
        ),
    ]

    active_patterns = [pattern for pattern in patterns if pattern["active"] or pattern["score"] >= 50]
    suspicion_score = clamp(sum(pattern["score"] for pattern in active_patterns) / max(1, len(active_patterns)) + 5 * max(0, len(active_patterns) - 2))
    no_trade_recommendations = []
    if suspicion_score >= 65:
        no_trade_recommendations.append(recommendation("strong_no_trade_bias", "manipulation suspicion is elevated"))
    elif suspicion_score >= 40:
        no_trade_recommendations.append(recommendation("wait_for_confirmation_bias", "trap risk is present but not decisive"))
    else:
        no_trade_recommendations.append(recommendation("normal_caution_bias", "no strong manipulation pattern is active"))

    payload = {
        "generated_at": now_ist(),
        "suspicion_score": round(suspicion_score, 2),
        "manipulation_patterns": patterns,
        "danger_zones": [
            {"zone": "stop_loss_clusters", "details": stop_clusters},
            {"zone": "breakout_trap_zones", "details": trap_zones},
            {"zone": "gap_zones", "details": liquidity.get("gap_zones", {})},
        ],
        "trap_patterns": active_patterns,
        "no_trade_recommendations": no_trade_recommendations,
        "safety_scope": "read_only_recommendation_only",
    }
    atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    run_manipulation_intelligence()
