from pathlib import Path

from consciousness_core.experience_utils import load_json
from consciousness_core.institutional_utils import CORE_DIR, clamp
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = CORE_DIR / "recursive_meta_learning.json"


def _quality(score, label, evidence_count):
    return {"score": round(clamp(score), 2), "state": label, "evidence_count": evidence_count}


def _area_name(key):
    return {
        "learning_quality": "learning directives",
        "evolution_quality": "sandbox evolution",
        "research_quality": "autonomous research",
        "debate_quality": "debate agents",
        "reasoning_quality": "causal reasoning",
    }.get(key, key)


def run_recursive_meta_learning(output_path=OUTPUT_PATH, **_kwargs):
    learning = load_json(CORE_DIR / "learning_directives.json", {})
    sandbox = load_json(CORE_DIR / "sandbox_results.json", [])
    research = load_json(CORE_DIR / "autonomous_research.json", {})
    debate = load_json(CORE_DIR / "multi_agent_debate.json", {})
    causal = load_json(CORE_DIR / "deep_causal_reasoning.json", {})
    daily = load_json(CORE_DIR / "daily_review.json", {})

    directives = learning.get("directives", [])
    useful_proposals = [item for item in sandbox if isinstance(item, dict) and item.get("recommendation") == "PROMOTE_TO_PAPER"]
    discoveries = research.get("ranked_discoveries", [])
    contradictions = debate.get("contradictions", []) or debate.get("open_disagreements", [])
    chains = causal.get("strongest_causal_chains", [])

    scores = {
        "learning_quality": _quality(45 + len(directives) * 7, "DIRECTIVE_TRACKED", len(directives)),
        "evolution_quality": _quality(40 + len(useful_proposals) * 12, "PAPER_TEST_GUIDED", len(useful_proposals)),
        "research_quality": _quality(42 + len(discoveries) * 8, "DISCOVERY_TRACKED", len(discoveries)),
        "debate_quality": _quality(65 - len(contradictions) * 6, "CONSENSUS_CHECKED", len(contradictions)),
        "reasoning_quality": _quality(45 + len(chains) * 9, "CAUSAL_CHAIN_TRACKED", len(chains)),
    }
    scalar_scores = {key: value["score"] for key, value in scores.items()}
    weakest_key = min(scalar_scores, key=scalar_scores.get)
    strongest_key = max(scalar_scores, key=scalar_scores.get)
    self_score = round(sum(scalar_scores.values()) / len(scalar_scores), 2)

    payload = {
        "generated_at": now_ist(),
        **scores,
        "self_improvement_score": self_score,
        "weakest_meta_area": _area_name(weakest_key),
        "strongest_meta_area": _area_name(strongest_key),
        "next_self_improvement_focus": f"improve {_area_name(weakest_key)} using paper-only evidence",
        "helpful_learning_directives": directives[:10],
        "useful_proposals": useful_proposals[:10],
        "accurate_debate_indicators": debate.get("agents", {}),
        "daily_review_feedback": {
            "worked": daily.get("what_worked", [])[:5],
            "failed": daily.get("what_failed", [])[:5],
        },
        "safety_scope": "read_only_recommendation_only",
    }
    atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    run_recursive_meta_learning()
