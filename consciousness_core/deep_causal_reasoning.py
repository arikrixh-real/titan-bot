from pathlib import Path

from consciousness_core.institutional_utils import (
    chain_id,
    clamp,
    confidence_quality,
    evidence_item,
    load_institutional_inputs,
)
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = Path("data") / "consciousness_core" / "deep_causal_reasoning.json"


def _causal_chain(name, steps, score, confidence, evidence, impact):
    return {
        "chain_id": chain_id([name, steps, score, confidence, impact]),
        "name": name,
        "steps": steps,
        "strength_score": round(clamp(score), 2),
        "confidence": round(clamp(confidence, 0.0, 1.0), 3),
        "evidence": evidence,
        "impact": impact,
    }


def run_deep_causal_reasoning(output_path=OUTPUT_PATH, **_kwargs):
    inputs = load_institutional_inputs()
    news = inputs["news"]
    no_trade = inputs["no_trade"]
    confidence = inputs["confidence"]
    liquidity_report = inputs["liquidity_map"]
    micro = inputs["microstructure"]
    world = inputs["world_model_memory"]
    causal = inputs["causal_reasoning"]

    news_warning = str(news.get("news_warning") or "").upper()
    news_memory = clamp(news.get("news_reaction_memory", {}).get("memory_confidence") or 0.0)
    volatility_score = clamp(no_trade.get("market_toxicity", {}).get("vix_or_volatility") or no_trade.get("choppy_market", {}).get("volatility_score") or 0.0)
    liquidity_score = clamp(liquidity_report.get("liquidity_map_score") or 50.0)
    breadth_score = clamp(no_trade.get("weak_breadth", {}).get("breadth_score") or 50.0)
    sector_score = clamp(inputs["sector_strength"].get("sector_strength_score") or 50.0)
    setup_quality = clamp(no_trade.get("low_edge_day", {}).get("edge_score") or no_trade.get("low_edge_day", {}).get("average_recent_setup_score") or 50.0)
    outcome_probability = clamp(confidence.get("confidence_correction", {}).get("corrected_confidence") or confidence.get("calibrated_confidence_score") or 50.0)
    confidence_info = confidence_quality(confidence)

    news_chain_strength = clamp(
        (100 - news_memory) * 0.2
        + volatility_score * 0.15
        + (100 - liquidity_score) * 0.2
        + (100 - breadth_score) * 0.15
        + sector_score * 0.1
        + setup_quality * 0.1
        + outcome_probability * 0.1
    )
    macro_liquidity_stress = clamp(
        no_trade.get("liquidity_danger", {}).get("danger_score") or (100 - liquidity_score) * 0.5
    )
    institutional_behavior_score = clamp(micro.get("smart_money_pressure", {}).get("score") or liquidity_report.get("smart_money_footprints", {}).get("score") or 40.0)
    regime_risk = clamp(no_trade.get("no_trade_score") or macro_liquidity_stress * 0.5)

    chains = [
        _causal_chain(
            "news_to_outcome_probability",
            ["news", "volatility", "liquidity", "breadth", "sector_strength", "setup_quality", "outcome_probability"],
            news_chain_strength,
            0.35 if news_warning == "REVIEW" else 0.6,
            [
                evidence_item("news_intelligence", "news_warning", news.get("news_warning")),
                evidence_item("news_intelligence", "memory_confidence", news_memory),
                evidence_item("no_trade", "breadth_score", breadth_score),
                evidence_item("confidence_calibration", "corrected_confidence", outcome_probability),
            ],
            "confidence_impacting",
        ),
        _causal_chain(
            "macro_to_risk_level",
            ["macro", "liquidity", "institutional_behavior", "regime", "risk_level"],
            clamp(macro_liquidity_stress * 0.45 + (100 - institutional_behavior_score) * 0.2 + regime_risk * 0.35),
            0.45,
            [
                evidence_item("economic_calendar", "available", bool(inputs["economic_calendar"])),
                evidence_item("liquidity_map", "liquidity_score", liquidity_score),
                evidence_item("microstructure", "smart_money_pressure", institutional_behavior_score),
                evidence_item("no_trade", "no_trade_score", no_trade.get("no_trade_score")),
            ],
            "regime_impacting",
        ),
        _causal_chain(
            "weak_evidence_to_confidence_reduction",
            ["proxy_data", "small_sample", "calibration_uncertainty", "confidence_adjustment"],
            75.0 if confidence_info["weak"] else 30.0,
            0.75,
            [
                evidence_item("confidence_calibration", "sample_size", confidence_info["sample_size"]),
                evidence_item("confidence_calibration", "calibration_warning", confidence.get("calibration_warning")),
            ],
            "confidence_impacting",
        ),
    ]

    contradiction_chains = []
    if setup_quality >= 55 and liquidity_score < 45:
        contradiction_chains.append(
            _causal_chain(
                "good_setup_vs_weak_liquidity",
                ["setup_quality_positive", "liquidity_weak", "execution_quality_uncertain"],
                70.0,
                0.55,
                [evidence_item("no_trade", "setup_quality", setup_quality), evidence_item("liquidity_map", "liquidity_score", liquidity_score)],
                "contradiction",
            )
        )
    if news_warning == "REVIEW" and outcome_probability >= 50:
        contradiction_chains.append(
            _causal_chain(
                "confidence_vs_low_news_reliability",
                ["confidence_positive", "news_memory_low", "headline_edge_uncertain"],
                65.0,
                0.5,
                [evidence_item("news_intelligence", "warning", news_warning), evidence_item("confidence_calibration", "outcome_probability", outcome_probability)],
                "contradiction",
            )
        )

    all_chains = chains + contradiction_chains
    strongest = sorted(all_chains, key=lambda item: item["strength_score"], reverse=True)[:10]
    weakest_links = [
        {"link": "news_reaction_memory", "reason": "low or absent news outcome memory", "confidence": news_memory},
        {"link": "confidence_calibration", "reason": confidence_info["reason"], "sample_size": confidence_info["sample_size"]},
        {"link": "sector_strength", "reason": "sector evidence may be absent or neutral", "score": sector_score},
    ]

    payload = {
        "generated_at": now_ist(),
        "strongest_causal_chains": strongest,
        "weakest_causal_links": weakest_links,
        "contradiction_chains": contradiction_chains,
        "confidence_impacting_chains": [chain for chain in all_chains if chain["impact"] == "confidence_impacting"],
        "regime_impacting_chains": [chain for chain in all_chains if chain["impact"] == "regime_impacting"],
        "source_causal_lessons_seen": len(causal.get("causal_lessons", [])),
        "world_model_market_laws_seen": world.get("market_laws", []),
        "safety_scope": "read_only_recommendation_only",
    }
    atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    run_deep_causal_reasoning()
