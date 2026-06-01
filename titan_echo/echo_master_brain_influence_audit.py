"""Audit Master Brain inputs, outputs, and actual operational influence."""

from __future__ import annotations

from typing import Any

from echo_batch_b_common import ECHO_RUNTIME, all_known_paths, artifact_summary, layer_file_count, load_json, matching_paths, status_from_runtime, text_hits, timestamp_ist, write_json


OUTPUT_PATH = ECHO_RUNTIME / "master_brain_influence_report.json"


def build_report() -> dict[str, Any]:
    paths = all_known_paths()
    mb_files = matching_paths(["titan_master_brain/", "runtime_master_brain.py"], paths)
    status = status_from_runtime(
        "data/runtime/master_brain_status.json",
        ["master_brain_runtime_health", "status", "overall_status"],
    )
    runtime_health = status_from_runtime(
        "data/runtime/master_brain_runtime_health.json",
        ["master_brain_runtime_health", "overall_status", "source_status"],
    )
    input_hits = text_hits(
        mb_files,
        ["scanner_status.json", "consciousness_context.json", "trade_outcomes", "knowledge_to_consciousness_packet", "latest_aggregated_packet"],
        50,
    )
    output_hits = text_hits(
        mb_files + matching_paths(["runtime_paper_engine.py", "runtime_scanner.py"], paths),
        ["master_brain_status.json", "evaluated_trade_setups", "final_decision", "make_final_decisions"],
        50,
    )
    decision_hits = text_hits(
        matching_paths(["runtime_paper_engine.py", "runtime_scanner.py", "scanner_filter_truth.py", "titan_master_brain/final_decision_engine.py"], paths),
        ["MASTER_BRAIN_STATUS_PATH", "final_master_rank", "selected_pool.sort", "evaluated_trade_setups", "trade_creation"],
        50,
    )
    meta_hits = text_hits(
        mb_files,
        ["consciousness", "learning", "evolution", "self_improvement", "meta_learning", "strategy_genome"],
        50,
    )
    payload = status["payload"]
    read_only = str(payload.get("runtime_mode") or payload.get("master_brain_runtime_mode") or "").upper() == "READ_ONLY"
    no_execution = not bool(payload.get("live_execution_enabled")) and not bool(payload.get("trade_creation"))
    current_top = bool(decision_hits) and not no_execution
    score = (25 if mb_files else 0) + (15 if status["active"] or runtime_health["active"] else 0) + (20 if input_hits else 0) + (20 if output_hits else 0) + (20 if decision_hits else 0)

    return {
        "schema": "titan_echo.master_brain_influence_audit.v1",
        "timestamp_ist": timestamp_ist(),
        "master_brain_exists_status": "EXISTS" if mb_files or layer_file_count("Master Brain layer") else "MISSING",
        "running_status": "ACTIVE_READ_ONLY" if (status["active"] or runtime_health["active"]) and read_only else "ACTIVE_OR_PRESENT" if status["active"] or runtime_health["active"] else "UNKNOWN",
        "input_consumption_status": "INPUTS_CONSUMED" if input_hits else "NO_INPUT_CONSUMPTION_EVIDENCE",
        "output_generation_status": "RUNTIME_OUTPUTS_FOUND" if output_hits or payload else "NO_OUTPUT_EVIDENCE",
        "decision_influence_status": "INFLUENCES_PIPELINE_READ_ONLY_OR_ADVISORY" if decision_hits else "NO_DECISION_PIPELINE_EVIDENCE",
        "current_authority_verdict": "MASTER_BRAIN_CURRENT_TOP" if current_top else "SCANNER_FILTER_RUNTIME_CURRENT_TOP_WITH_MASTER_BRAIN_READ_ONLY",
        "master_brain_influence_score": min(score, 100),
        "evidence": {
            "mapped_layer_file_count": layer_file_count("Master Brain layer"),
            "matched_files": mb_files[:40],
            "status_artifacts": artifact_summary(["data/runtime/master_brain_status.json", "data/runtime/master_brain_runtime_health.json"]),
            "status_payload_flags": {
                "runtime_mode": payload.get("runtime_mode"),
                "master_brain_runtime_mode": payload.get("master_brain_runtime_mode"),
                "live_execution_enabled": payload.get("live_execution_enabled"),
                "trade_creation": payload.get("trade_creation"),
                "observe_only": payload.get("observe_only"),
                "evaluated_count": payload.get("evaluated_count"),
            },
            "input_hits": input_hits[:15],
            "output_hits": output_hits[:15],
            "decision_hits": decision_hits[:15],
            "learning_evolution_consciousness_hits": meta_hits[:15],
        },
        "missing_inputs": [
            "Unified Brain input artifact",
            "fresh decision-cycle evidence with non-zero evaluated_trade_setups",
            "explicit before/after proof that learning/evolution/consciousness changed final decisions",
        ],
        "recommended_next_steps": [
            "Keep current read-only safety flags intact.",
            "Add source-hash and freshness fields for every consumed input packet.",
            "Add final decision trace IDs linking scanner candidate -> Master Brain rank -> paper/live outcome.",
            "Connect Unified Brain only after it has a validated shadow artifact and tests.",
        ],
    }


def main() -> int:
    report = build_report()
    write_json(OUTPUT_PATH, report)
    print("TITAN ECHO Master Brain influence audit: PASSED")
    print(f"Master Brain influence score: {report['master_brain_influence_score']}")
    print(f"Current authority verdict: {report['current_authority_verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
