"""Build a read-only system influence map for TITAN."""

from __future__ import annotations

from typing import Any

from echo_batch_b_common import ECHO_RUNTIME, all_known_paths, text_hits, timestamp_ist, write_json


OUTPUT_PATH = ECHO_RUNTIME / "system_influence_map.json"


SUBSYSTEMS = [
    "ECHO",
    "Unified Brain",
    "Consciousness Core",
    "Master Brain",
    "Scanner",
    "Filters",
    "Risk",
    "Execution",
    "Outcome Tracker",
    "Learning",
    "Evolution",
    "Memory",
    "News",
    "Supabase",
    "Dashboard",
    "Runtime",
]


def link(source: str, target: str, strength: str, evidence: list[dict[str, Any]], confidence: str) -> dict[str, Any]:
    return {
        "from": source,
        "to": target,
        "influence_strength": strength,
        "evidence": evidence[:8],
        "confidence": confidence,
    }


def build_report() -> dict[str, Any]:
    paths = all_known_paths()
    implementation_paths = [
        path
        for path in paths
        if not path.startswith("titan_echo/") and not path.startswith("data/runtime/echo/")
    ]
    evidence = {
        "scanner_master": text_hits(["runtime_master_brain.py", "runtime_scanner.py"], ["scanner_status.json", "master_brain_status.json"], 20),
        "master_execution": text_hits(["runtime_paper_engine.py", "titan_master_brain/master_controller.py"], ["master_brain_status.json", "prepare_execution_packets", "send_telegram_signals", "trade_creation"], 20),
        "master_decision": text_hits(["titan_master_brain/final_decision_engine.py"], ["final_master_rank", "selected_pool.sort", "make_final_decisions"], 20),
        "consciousness_master": text_hits(["titan_master_brain/input_aggregator.py", "titan_master_brain/context_builder.py"], ["consciousness_context.json", "master_brain_shadow_recommendations.json", "consciousness_warnings"], 20),
        "risk_scanner": text_hits(["runtime_scanner.py", "engines/setup_engine.py", "engines/risk_engine.py"], ["calculate_rr", "risk_quality_score", "risk_filter", "phase1_blocked"], 20),
        "dashboard_runtime": text_hits(["dashboard.py", "runtime_dashboard_sync.py"], ["data/runtime", "scanner_status", "master_brain_status"], 20),
        "news": text_hits(["runtime_scanner.py", "engines/news_intelligence_2_engine.py", "intelligence/news_engine.py"], ["news", "news_warning", "news_filter"], 20),
        "supabase": text_hits(["titan_master_brain/master_controller.py", "titan_brain/supabase_client.py", "titan_brain/db.py"], ["supabase", "create_client", "supabase_writes"], 20),
        "outcome_learning": text_hits(["journal/outcome_tracker.py", "runtime_outcome_tracker.py", "learning_evolution_truth.py", "engines/learning_engine.py"], ["outcome", "learning", "evolution", "trade_results"], 20),
        "unified": text_hits(implementation_paths, ["unified_brain", "Unified Brain"], 20),
    }

    links = [
        link("Scanner", "Master Brain", "MEDIUM", evidence["scanner_master"], "HIGH" if evidence["scanner_master"] else "LOW"),
        link("Master Brain", "Execution", "MEDIUM_READ_ONLY", evidence["master_execution"], "HIGH" if evidence["master_execution"] else "LOW"),
        link("Master Brain", "Filters", "HIGH_IN_CODE", evidence["master_decision"], "HIGH" if evidence["master_decision"] else "LOW"),
        link("Consciousness Core", "Master Brain", "LOW_TO_MEDIUM_CONTEXT", evidence["consciousness_master"], "MEDIUM" if evidence["consciousness_master"] else "LOW"),
        link("Risk", "Scanner", "HIGH", evidence["risk_scanner"], "HIGH" if evidence["risk_scanner"] else "LOW"),
        link("News", "Filters", "LOW_TO_MEDIUM", evidence["news"], "MEDIUM" if evidence["news"] else "LOW"),
        link("Runtime", "Dashboard", "HIGH_STATUS_VISIBILITY", evidence["dashboard_runtime"], "HIGH" if evidence["dashboard_runtime"] else "LOW"),
        link("Supabase", "Master Brain", "LOW_RUNTIME_DISABLED", evidence["supabase"], "MEDIUM" if evidence["supabase"] else "LOW"),
        link("Outcome Tracker", "Learning", "MEDIUM", evidence["outcome_learning"], "MEDIUM" if evidence["outcome_learning"] else "LOW"),
        link("Learning", "Evolution", "LOW_TO_MEDIUM", evidence["outcome_learning"], "MEDIUM" if evidence["outcome_learning"] else "LOW"),
    ]

    by_subsystem: dict[str, dict[str, Any]] = {
        name: {"subsystem": name, "influences": [], "influenced_by": [], "influence_strength": "UNKNOWN", "evidence": [], "confidence": "LOW"}
        for name in SUBSYSTEMS
    }
    for item in links:
        by_subsystem[item["from"]]["influences"].append(item["to"])
        by_subsystem[item["from"]]["evidence"].extend(item["evidence"][:3])
        by_subsystem[item["to"]]["influenced_by"].append(item["from"])
    for name, item in by_subsystem.items():
        strengths = [edge["influence_strength"] for edge in links if edge["from"] == name]
        item["influence_strength"] = strengths[0] if strengths else "NONE_PROVEN" if name in {"Unified Brain"} else "UNKNOWN_OR_PASSIVE"
        item["confidence"] = "HIGH" if item["evidence"] else "LOW"

    dead_paths = []
    if not evidence["unified"]:
        dead_paths.append({"path": "Unified Brain -> Consciousness Core -> Master Brain", "reason": "Unified Brain files/connections not found."})
    passive_modules = [
        {"subsystem": "ECHO", "reason": "Audit/approval layer writes ECHO artifacts, not operational decisions."},
        {"subsystem": "Consciousness Core", "reason": "Consumed as context/shadow recommendations; direct final decision mutation not proven."},
        {"subsystem": "Dashboard", "reason": "Runtime visibility layer."},
    ]

    score = 55
    if evidence["master_decision"]:
        score += 15
    if evidence["consciousness_master"]:
        score += 10
    if not evidence["unified"]:
        score -= 20

    return {
        "schema": "titan_echo.system_influence_map.v1",
        "timestamp_ist": timestamp_ist(),
        "system_influence_score": max(0, min(score, 100)),
        "subsystems": list(by_subsystem.values()),
        "top_influence_chains": [
            "Scanner -> Master Brain -> paper/execution status",
            "Risk/filter engines -> Scanner final_validated_setups",
            "Master Brain final_decision_engine -> selected/rejected setup ranking",
        ],
        "weak_influence_chains": [
            "Consciousness Core -> Master Brain decision changes",
            "Learning/Evolution -> live ranking/outcome improvement",
            "Supabase -> current runtime authority",
        ],
        "dead_paths": dead_paths,
        "passive_modules": passive_modules,
        "missing_influence_links": [
            "Unified Brain layer to Master Brain",
            "Consciousness recommendation to final decision trace",
            "Learning/evolution update to changed ranking and later outcome",
        ],
        "current_control_hierarchy": [
            "Runtime/Daemon",
            "Scanner",
            "Filters/Risk",
            "Master Brain read-only/advisory status",
            "Paper/Execution safety gates",
            "Dashboard/ECHO visibility",
        ],
        "recommended_integration_upgrades": [
            "Create Unified Brain shadow artifact and connect it read-only.",
            "Add source-consumption hashes and decision-cycle IDs across scanner, Master Brain, and outcome tracker.",
            "Promote Consciousness Core from context to bounded decision influence only after paper evidence.",
        ],
        "raw_links": links,
    }


def main() -> int:
    report = build_report()
    write_json(OUTPUT_PATH, report)
    print("TITAN ECHO system influence map: PASSED")
    print(f"System influence score: {report['system_influence_score']}")
    print(f"Current hierarchy: {' > '.join(report['current_control_hierarchy'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
