"""Audit whether a real Unified Brain layer exists and influences TITAN."""

from __future__ import annotations

from typing import Any

from echo_batch_b_common import ECHO_RUNTIME, all_known_paths, layer_file_count, matching_paths, text_hits, timestamp_ist, unique, write_json


OUTPUT_PATH = ECHO_RUNTIME / "unified_brain_gap_report.json"


def build_report() -> dict[str, Any]:
    paths = all_known_paths()
    implementation_paths = [
        path
        for path in paths
        if not path.startswith("titan_echo/") and not path.startswith("data/runtime/echo/")
    ]
    unified_files = matching_paths(["unified_brain", "unified-brain", "unified brain"], implementation_paths)
    layer_count = layer_file_count("Unified Brain layer")
    graph_hits = [
        hit
        for hit in text_hits(["data/runtime/echo/titan_connection_graph.json"], ["unified_brain"], 10)
        if "echo_unified_brain" not in hit.get("text", "")
    ]
    master_hits = text_hits(
        matching_paths(["runtime_master_brain.py", "titan_master_brain"], paths),
        ["unified_brain", "Unified Brain"],
        20,
    )
    consumer_hits = text_hits(
        unified_files,
        ["consciousness", "learning", "evolution", "master_brain", "final_decision"],
        20,
    )

    exists = bool(unified_files or layer_count)
    connected = bool(graph_hits or master_hits or consumer_hits)
    influences_master = bool(master_hits)
    consumes_meta_outputs = bool(consumer_hits)
    score = round(
        (
            (25 if exists else 0)
            + (15 if layer_count else 0)
            + (20 if connected else 0)
            + (25 if influences_master else 0)
            + (15 if consumes_meta_outputs else 0)
        )
    )

    missing = []
    if not exists:
        missing.append("Unified Brain files/modules are not present in the file index or filesystem scan.")
    if not layer_count:
        missing.append("Unified Brain layer has zero mapped files in titan_architecture_map.json.")
    if not connected:
        missing.append("No import/path/text evidence connects Unified Brain to runtime, Master Brain, or decision systems.")
    if not influences_master:
        missing.append("No evidence that Master Brain reads Unified Brain output.")
    if not consumes_meta_outputs:
        missing.append("No evidence that Unified Brain consumes learning, evolution, or consciousness outputs.")

    return {
        "schema": "titan_echo.unified_brain_gap_analysis.v1",
        "timestamp_ist": timestamp_ist(),
        "unified_brain_exists_status": "EXISTS" if exists else "MISSING",
        "running_status": "UNKNOWN_NO_RUNTIME_ARTIFACT" if exists else "NO_EVIDENCE",
        "connection_status": "CONNECTED" if connected else "NO_EVIDENCE",
        "influence_status": "INFLUENCES_MASTER_BRAIN" if influences_master else "NO_EVIDENCE_OF_INFLUENCE",
        "unified_brain_gap_score": 100 - score,
        "evidence": {
            "mapped_layer_file_count": layer_count,
            "matched_files": unified_files[:50],
            "graph_or_map_hits": graph_hits,
            "master_brain_reference_hits": master_hits,
            "meta_output_consumption_hits": consumer_hits,
        },
        "missing_components": missing,
        "required_interfaces": [
            "read-only input interface from Learning/Evolution/Consciousness outputs",
            "versioned Unified Brain state artifact under data/runtime or data/memory",
            "Master Brain consumption contract with explicit fields and freshness",
            "decision-trace IDs proving Unified Brain output changed final ranking or gating",
            "health/status artifact proving whether Unified Brain is running",
        ],
        "recommended_build_steps": [
            "Define Unified Brain schema and freshness contract before connecting it to decisions.",
            "Add read-only aggregation from consciousness, learning, evolution, outcome, memory, and news artifacts.",
            "Expose a runtime status artifact with mode, last_success, source hashes, and advisory/live flags.",
            "Wire Master Brain to consume the artifact in shadow mode first.",
            "Add decision trace fields that show before/after ranking when Unified Brain advice is used.",
        ],
        "risk_level": "HIGH" if not exists else "MEDIUM",
        "verdict": "UNIFIED_BRAIN_MISSING" if not exists else "UNIFIED_BRAIN_PARTIAL",
    }


def main() -> int:
    report = build_report()
    write_json(OUTPUT_PATH, report)
    print("TITAN ECHO Unified Brain gap analysis: PASSED")
    print(f"Unified Brain status: {report['unified_brain_exists_status']}")
    print(f"Unified Brain gap score: {report['unified_brain_gap_score']}")
    print(f"Influence status: {report['influence_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
