from consciousness_core.experience_utils import load_json
from consciousness_core.institutional_utils import CORE_DIR
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_JSON_PATH = CORE_DIR / "phase_c_summary.json"
OUTPUT_TXT_PATH = CORE_DIR / "phase_c_summary.txt"


def run_phase_c_summary(output_json_path=OUTPUT_JSON_PATH, output_txt_path=OUTPUT_TXT_PATH, **_kwargs):
    scenarios = load_json(CORE_DIR / "real_scenario_simulation.json", {})
    next_day = load_json(CORE_DIR / "next_day_preparation.json", {})
    paper = load_json(CORE_DIR / "paper_testing_ecosystem.json", {})
    data_quality = load_json(CORE_DIR / "data_quality_intelligence.json", {})
    validation = load_json(CORE_DIR / "validation_depth.json", {})
    infra = load_json(CORE_DIR / "institutional_infrastructure_awareness.json", {})

    scenario_list = scenarios.get("scenarios", [])
    final_blockers = []
    final_blockers.extend(validation.get("blockers", []))
    final_blockers.extend(data_quality.get("missing_data_warnings", [])[:5])
    final_blockers.extend(infra.get("missing_capabilities", [])[:5])
    payload = {
        "generated_at": now_ist(),
        "safety_scope": "read_only_recommendation_only",
        "scenario_outlook": {
            "dominant_scenario": scenarios.get("dominant_scenario"),
            "top_scenarios": scenario_list[:3],
        },
        "next_day_plan": {
            "expected_regime": next_day.get("expected_regime", {}),
            "next_day_bias": next_day.get("next_day_bias"),
            "top_risks": next_day.get("top_risks", [])[:5],
            "no_trade_conditions": next_day.get("no_trade_conditions", [])[:8],
        },
        "paper_testing_maturity": paper.get("paper_test_health", {}),
        "data_quality_warnings": {
            "score": data_quality.get("data_quality_score"),
            "stale": data_quality.get("stale_data_warnings", [])[:5],
            "missing": data_quality.get("missing_data_warnings", [])[:5],
            "proxy": data_quality.get("proxy_data_warnings", [])[:5],
            "low_sample": data_quality.get("low_sample_warnings", [])[:5],
        },
        "validation_depth": {
            "score": validation.get("validation_depth_score"),
            "promotion_allowed": validation.get("promotion_allowed", False),
            "blockers": validation.get("blockers", []),
        },
        "institutional_gaps": {
            "current_infra_level": infra.get("current_infra_level"),
            "institutional_gap_score": infra.get("institutional_gap_score"),
            "missing_capabilities": infra.get("missing_capabilities", []),
        },
        "final_remaining_blockers": list(dict.fromkeys(str(item) for item in final_blockers))[:20],
    }
    atomic_write_json(output_json_path, payload)
    lines = [
        "TITAN Phase C Summary",
        f"Generated: {payload['generated_at']}",
        "",
        f"Scenario outlook: {payload['scenario_outlook'].get('dominant_scenario') or 'unknown'}",
        f"Next-day bias: {payload['next_day_plan'].get('next_day_bias') or 'unknown'}",
        f"Paper-test health: {payload['paper_testing_maturity'].get('state')} score={payload['paper_testing_maturity'].get('score')}",
        f"Data quality score: {payload['data_quality_warnings'].get('score')}",
        f"Validation depth score: {payload['validation_depth'].get('score')} promotion_allowed={payload['validation_depth'].get('promotion_allowed')}",
        f"Infrastructure level: {payload['institutional_gaps'].get('current_infra_level')} gap={payload['institutional_gaps'].get('institutional_gap_score')}",
        "",
        "Final remaining blockers:",
    ]
    if payload["final_remaining_blockers"]:
        lines.extend(f"- {item}" for item in payload["final_remaining_blockers"])
    else:
        lines.append("- None beyond mandatory human review and read-only safety scope.")
    lines.append("")
    lines.append("Safety: read-only, sandbox-safe, recommendation-only; no live mutation or execution changes.")
    output_txt_path.parent.mkdir(parents=True, exist_ok=True)
    output_txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload
