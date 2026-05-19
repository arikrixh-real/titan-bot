from .deduplicator import merge_items


def build_beliefs(existing_beliefs, memory_items):
    candidates = []
    for item in memory_items:
        item_type = item.get("type")
        if item_type not in {"rule", "risk_warning", "market_psychology", "institutional_concept"}:
            continue
        confidence = min(0.2 + (item.get("seen_count", 1) * 0.12) + (item.get("importance", 0) * 0.45), 0.85)
        candidates.append(
            {
                "type": "knowledge_belief",
                "topic": item_type,
                "text": item.get("text"),
                "confidence": round(confidence, 3),
                "importance": item.get("importance", 0),
                "status": "evidence_only_pending_validation",
                "safety": "does_not_change_live_strategy_or_risk",
                "evidence": item.get("evidence", [])[:8],
            }
        )
    beliefs, stats = merge_items(existing_beliefs, candidates)
    return beliefs[:300], stats


def build_research_ideas(existing_ideas, memory_items):
    candidates = []
    for item in memory_items:
        if item.get("type") not in {"testable_hypothesis", "strategy_idea"}:
            continue
        candidates.append(
            {
                "type": "research_idea",
                "text": item.get("text"),
                "importance": item.get("importance", 0),
                "status": "needs_backtest_or_paper_validation",
                "evidence": item.get("evidence", [])[:8],
            }
        )
    ideas, stats = merge_items(existing_ideas, candidates)
    return ideas[:300], stats

