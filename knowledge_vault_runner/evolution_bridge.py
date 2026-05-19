import time

from .chunker import stable_hash


def build_consciousness_packet(memory, beliefs, research_ideas, run_stats, extraction_warnings):
    top_items = sorted(memory, key=lambda item: item.get("importance", 0), reverse=True)[:50]
    observations = []
    for item in top_items:
        observations.append(
            {
                "type": "knowledge_vault_intelligence",
                "metric": item.get("type", "knowledge_item"),
                "value": item.get("text"),
                "severity": "MEDIUM" if item.get("importance", 0) >= 0.55 else "LOW",
                "entity": "knowledge_vault",
                "actionability_score": item.get("importance", 0),
                "evidence": item.get("evidence", []),
                "safety": "evidence_only_no_live_mutation",
            }
        )
    return {
        "status": "ok",
        "generated_at": time.time(),
        "runner": "knowledge_vault_runner",
        "safety": {
            "live_mutation": False,
            "direct_strategy_changes": False,
            "risk_logic_changes": False,
            "packet_type": "evidence_beliefs_hypotheses_research_ideas",
        },
        "run_stats": run_stats,
        "extraction_warnings": extraction_warnings[:100],
        "top_knowledge_items": top_items,
        "beliefs": beliefs[:50],
        "research_ideas": research_ideas[:50],
        "observations": observations,
        "packet_hash": stable_hash([top_items, beliefs[:50], research_ideas[:50], extraction_warnings]),
    }

