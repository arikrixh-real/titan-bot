from pathlib import Path

from consciousness_core.institutional_utils import (
    confidence_quality,
    evidence_item,
    load_institutional_inputs,
    recent_outcome_stats,
)
from consciousness_core.state import atomic_write_json, now_ist, stable_hash


OUTPUT_PATH = Path("data") / "consciousness_core" / "autonomous_research.json"


def _discovery(hypothesis, evidence, confidence, test_design, expected_edge, danger_level, status="PROPOSED"):
    return {
        "research_id": "research_" + stable_hash([hypothesis, evidence])[:16],
        "hypothesis": hypothesis,
        "evidence": evidence,
        "confidence": confidence,
        "test_design": test_design,
        "expected_edge": expected_edge,
        "danger_level": danger_level,
        "status": status,
    }


def run_autonomous_research_scientist(output_path=OUTPUT_PATH, **_kwargs):
    inputs = load_institutional_inputs()
    confidence = inputs["confidence"]
    no_trade = inputs["no_trade"]
    news = inputs["news"]
    real_memory = inputs["real_experience_memory"]
    clusters = inputs["experience_clusters"]
    outcomes = recent_outcome_stats(inputs["trade_rows"])
    confidence_info = confidence_quality(confidence)

    discoveries = [
        _discovery(
            "Low calibration sample size may be overstating setup confidence.",
            [evidence_item("confidence_calibration", "sample_size", confidence_info["sample_size"]), evidence_item("confidence_calibration", "warning", confidence.get("calibration_warning"))],
            0.78 if confidence_info["weak"] else 0.35,
            "Backtest and paper-test confidence buckets by setup/regime without changing live strategy.",
            "Lower false confidence during proxy or zero-sample periods.",
            "HIGH" if confidence_info["weak"] else "MEDIUM",
        ),
        _discovery(
            "No-trade warnings may identify hidden recurring failure regimes.",
            [evidence_item("no_trade", "score", no_trade.get("no_trade_score")), evidence_item("no_trade", "warning", no_trade.get("no_trade_warning"))],
            0.55,
            "Compare outcomes on days with no-trade score above threshold versus normal days.",
            "Avoid low-edge periods using advisory filters only.",
            "MEDIUM",
        ),
        _discovery(
            "Low news memory confidence can create headline-driven contradiction traps.",
            [evidence_item("news_intelligence", "memory_confidence", news.get("news_reaction_memory", {}).get("memory_confidence")), evidence_item("news_intelligence", "warning", news.get("news_warning"))],
            0.7 if str(news.get("news_warning") or "").upper() == "REVIEW" else 0.4,
            "Group paper outcomes by news_warning and reaction memory confidence.",
            "Reduce news-chasing in low-memory environments.",
            "MEDIUM",
        ),
        _discovery(
            "Repeated failure clusters may reveal setup/regime edges hidden by aggregate results.",
            [evidence_item("real_experience_memory", "repeated_failures", real_memory.get("repeated_failure_patterns", [])[:5]), evidence_item("experience_clusters", "clusters", clusters.get("clusters", [])[:5])],
            0.6 if real_memory.get("repeated_failure_patterns") else 0.3,
            "Partition failures by symbol, setup, regime, liquidity state, and news state.",
            "Sharper recommendation-only avoidance rules for recurring weak contexts.",
            "LOW",
        ),
        _discovery(
            "Recent outcome weakness may indicate degraded regime fit.",
            [evidence_item("recent_outcomes", "stats", outcomes)],
            0.65 if outcomes["losses"] > outcomes["wins"] and outcomes["losses"] >= 3 else 0.25,
            "Run rolling regime-fit analysis over recent paper outcomes and validation reports.",
            "Earlier recognition of model decay without live mutation.",
            "MEDIUM",
        ),
    ]

    payload = {
        "generated_at": now_ist(),
        "discoveries": discoveries,
        "ranked_discoveries": sorted(discoveries, key=lambda item: item["confidence"], reverse=True),
        "search_targets": [
            "recurring_failures",
            "hidden_edges",
            "contradiction_causes",
            "low_sample_confidence_failures",
            "news_liquidity_regime_interactions",
        ],
        "safety_scope": "read_only_recommendation_only",
    }
    atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    run_autonomous_research_scientist()
