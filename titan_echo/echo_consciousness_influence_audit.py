"""Audit whether Consciousness Core outputs influence operational decisions."""

from __future__ import annotations

from typing import Any

from echo_batch_b_common import ECHO_RUNTIME, all_known_paths, artifact_summary, layer_file_count, matching_paths, text_hits, timestamp_ist, write_json


OUTPUT_PATH = ECHO_RUNTIME / "consciousness_influence_report.json"


def build_report() -> dict[str, Any]:
    paths = all_known_paths()
    core_files = matching_paths(["consciousness_core/"], paths)
    output_paths = matching_paths(["data/consciousness_core/"], paths)
    mb_paths = matching_paths(["titan_master_brain/", "runtime_master_brain.py"], paths)
    consumption_hits = text_hits(
        mb_paths,
        ["data/consciousness_core/consciousness_context.json", "master_brain_shadow_recommendations.json", "consciousness"],
        40,
    )
    decision_hits = text_hits(
        matching_paths(["titan_master_brain/final_decision_engine.py", "titan_master_brain/context_builder.py"], paths),
        ["consciousness_warnings", "final_reflection_rank", "REFLECTION_WEIGHT", "build_self_reflection_report"],
        40,
    )
    passive_hits = text_hits(
        matching_paths(["titan_master_brain/", "engines/roadmap", "engines/meta", "engines/self_reflection"], paths),
        ["advisory sidecar", "shadow_recommendation", "live_apply_allowed", "direct_scoring_change", "rank_score"],
        40,
    )

    exists = bool(core_files or layer_file_count("Consciousness Core layer"))
    outputs = bool(output_paths)
    consumed = bool(consumption_hits)
    rank_evidence = any("final_reflection_rank" in hit["text"] or "REFLECTION_WEIGHT" in hit["text"] for hit in decision_hits)
    direct_core_decision = any("consciousness_context" in hit["text"] and "final" in hit["file"] for hit in decision_hits)
    influence_score = (25 if exists else 0) + (20 if outputs else 0) + (25 if consumed else 0) + (20 if rank_evidence else 0) + (10 if direct_core_decision else 0)

    if direct_core_decision:
        verdict = "CONSCIOUSNESS_ACTIVE"
        passive = "ACTIVE_DECISION_INPUT"
    elif consumed or rank_evidence:
        verdict = "CONSCIOUSNESS_PARTIAL"
        passive = "PARTIAL_CONTEXT_AND_REFLECTION_INFLUENCE"
    elif exists:
        verdict = "CONSCIOUSNESS_PASSIVE"
        passive = "PASSIVE_OUTPUTS_ONLY"
    else:
        verdict = "UNKNOWN"
        passive = "UNKNOWN"

    missing = []
    if not direct_core_decision:
        missing.append("No direct evidence that Consciousness Core artifacts change final Master Brain ranking or gates.")
    if not consumed:
        missing.append("No downstream consumption evidence beyond searched Master Brain references.")
    if passive_hits:
        missing.append("Several related intelligence outputs declare advisory/shadow-only behavior.")

    return {
        "schema": "titan_echo.consciousness_influence_audit.v1",
        "timestamp_ist": timestamp_ist(),
        "consciousness_exists_status": "EXISTS" if exists else "MISSING",
        "output_generation_status": "OUTPUTS_FOUND" if outputs else "NO_OUTPUT_ARTIFACTS_FOUND",
        "downstream_consumption_status": "CONSUMED_BY_MASTER_BRAIN_INPUTS" if consumed else "NO_CONSUMPTION_EVIDENCE",
        "decision_influence_status": "PARTIAL_REFLECTION_RANK_EVIDENCE" if rank_evidence else "NO_DECISION_INFLUENCE_EVIDENCE",
        "passive_vs_active_verdict": passive,
        "consciousness_influence_score": min(influence_score, 100),
        "strongest_evidence": {
            "core_file_count": len(core_files),
            "mapped_layer_file_count": layer_file_count("Consciousness Core layer"),
            "output_artifacts": artifact_summary(output_paths[:15]),
            "downstream_consumption_hits": consumption_hits[:12],
            "decision_or_reflection_hits": decision_hits[:12],
        },
        "missing_evidence": missing,
        "recommended_next_steps": [
            "Add explicit fields showing which consciousness artifact/version was consumed by each decision cycle.",
            "Record before/after final ranking when consciousness warnings or recommendations are applied.",
            "Separate Consciousness Core artifact influence from generic self-reflection engine influence.",
            "Keep shadow recommendations non-mutating until traceable paper/live outcomes validate them.",
        ],
        "verdict": verdict,
    }


def main() -> int:
    report = build_report()
    write_json(OUTPUT_PATH, report)
    print("TITAN ECHO Consciousness influence audit: PASSED")
    print(f"Consciousness influence score: {report['consciousness_influence_score']}")
    print(f"Decision influence status: {report['decision_influence_status']}")
    print(f"Verdict: {report['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
