from consciousness_core.experience_utils import load_json
from consciousness_core.institutional_utils import CORE_DIR
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_JSON_PATH = CORE_DIR / "recursive_intelligence_summary.json"
OUTPUT_TXT_PATH = CORE_DIR / "recursive_intelligence_summary.txt"


def run_recursive_intelligence_summary(output_json_path=OUTPUT_JSON_PATH, output_txt_path=OUTPUT_TXT_PATH, **_kwargs):
    meta = load_json(CORE_DIR / "recursive_meta_learning.json", {})
    ecosystem = load_json(CORE_DIR / "evolution_ecosystem.json", {})
    amplification = load_json(CORE_DIR / "intelligence_amplification.json", {})
    attention = load_json(CORE_DIR / "adaptive_attention.json", {})
    score = load_json(CORE_DIR / "self_improvement_score.json", {})
    goals = load_json(CORE_DIR / "autonomous_goal_hierarchy.json", {})
    memory = load_json(CORE_DIR / "evolution_memory_civilization.json", {})

    strongest = ecosystem.get("strongest_mutations", [])[:10]
    weakest = ecosystem.get("weakest_mutations", [])[:10]
    payload = {
        "generated_at": now_ist(),
        "recursive_growth": {
            "overall_recursive_score": score.get("overall_recursive_score"),
            "recursive_growth_status": score.get("recursive_growth_status"),
            "self_improvement_score": meta.get("self_improvement_score"),
        },
        "evolution_ecosystem_state": {
            "evolution_cycles": ecosystem.get("evolution_cycles"),
            "active_mutation_count": len(ecosystem.get("active_mutations", [])),
            "retired_mutation_count": len(ecosystem.get("retired_mutations", [])),
            "next_evolution_direction": ecosystem.get("next_evolution_direction"),
        },
        "intelligence_amplification": amplification,
        "adaptive_attention": attention.get("attention_items", [])[:10],
        "strongest_mutations": strongest,
        "weakest_areas": {
            "weakest_meta_area": meta.get("weakest_meta_area"),
            "weakest_mutations": weakest,
            "recurring_failures": ecosystem.get("recurring_failures", [])[:10],
        },
        "self_improvement_trajectory": {
            "trend": amplification.get("improvement_trend"),
            "growth_state": amplification.get("intelligence_growth_state"),
            "next_focus": meta.get("next_self_improvement_focus"),
            "top_goal": goals.get("top_goal"),
        },
        "memory_civilization_state": {
            "short_term_items": len(memory.get("short_term_memory", {})),
            "medium_term_items": len(memory.get("medium_term_memory", {})),
            "long_term_items": len(memory.get("long_term_memory", {})),
            "permanent_market_laws": len(memory.get("permanent_market_laws", [])),
        },
        "recursive_intelligence_status": "RECOMMENDATION_ONLY_RECURSIVE_INFRASTRUCTURE",
        "safety_scope": "read_only_sandbox_recommendation_only_no_live_mutation",
    }
    atomic_write_json(output_json_path, payload)

    lines = [
        "TITAN Mega Phase B Recursive Intelligence Summary",
        f"Generated: {payload['generated_at']}",
        "",
        "Recursive growth:",
        f"- Overall score: {payload['recursive_growth']['overall_recursive_score']}",
        f"- Status: {payload['recursive_growth']['recursive_growth_status']}",
        f"- Meta self-improvement score: {payload['recursive_growth']['self_improvement_score']}",
        "",
        "Evolution ecosystem:",
        f"- Cycles: {payload['evolution_ecosystem_state']['evolution_cycles']}",
        f"- Active mutations: {payload['evolution_ecosystem_state']['active_mutation_count']}",
        f"- Retired mutations: {payload['evolution_ecosystem_state']['retired_mutation_count']}",
        f"- Next direction: {payload['evolution_ecosystem_state']['next_evolution_direction']}",
        "",
        "Intelligence amplification:",
        f"- Score: {amplification.get('amplification_score')}",
        f"- Trend: {amplification.get('improvement_trend')}",
        f"- Growth state: {amplification.get('intelligence_growth_state')}",
        "",
        "Adaptive attention:",
    ]
    for item in payload["adaptive_attention"][:5]:
        lines.append(f"- {item.get('priority')} {item.get('focus_area')}: {item.get('reason')} weight={item.get('resource_weight')}")
    lines.append("")
    lines.append("Strongest mutations:")
    if strongest:
        lines.extend(f"- {item.get('genome_id')}: score={item.get('sandbox_score')} risk={item.get('risk_score')}" for item in strongest[:5])
    else:
        lines.append("- None yet.")
    lines.append("")
    lines.append("Weakest areas:")
    lines.append(f"- Meta area: {meta.get('weakest_meta_area')}")
    if ecosystem.get("recurring_failures"):
        lines.append("- Recurring failure: " + str(ecosystem["recurring_failures"][0]))
    lines.append("")
    lines.append("Self-improvement trajectory:")
    lines.append(f"- Next focus: {meta.get('next_self_improvement_focus')}")
    lines.append(f"- Top goal: {(goals.get('top_goal') or {}).get('title')}")
    lines.append("")
    lines.append("Safety: read-only, sandbox-safe, recommendation-only; no broker, Telegram, Supabase, live strategy, live risk, or worker lock mutation.")
    output_txt_path.parent.mkdir(parents=True, exist_ok=True)
    output_txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    run_recursive_intelligence_summary()
