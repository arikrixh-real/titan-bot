"""Summarize TITAN ECHO Batch B control and influence audits."""

from __future__ import annotations

from typing import Any

from echo_batch_b_common import ECHO_RUNTIME, load_json, timestamp_ist, unique, write_json


OUTPUT_PATH = ECHO_RUNTIME / "batch_b_summary.json"


def verdicts(unified: dict[str, Any], consciousness: dict[str, Any], master: dict[str, Any]) -> list[str]:
    result = []
    result.append(unified.get("verdict") or "UNKNOWN")
    result.append(consciousness.get("verdict") or "UNKNOWN")
    if master.get("current_authority_verdict") == "MASTER_BRAIN_CURRENT_TOP":
        result.append("MASTER_BRAIN_CURRENT_TOP")
    else:
        result.append("UNKNOWN")
    return result


def build_report() -> dict[str, Any]:
    unified = load_json(ECHO_RUNTIME / "unified_brain_gap_report.json", {})
    consciousness = load_json(ECHO_RUNTIME / "consciousness_influence_report.json", {})
    master = load_json(ECHO_RUNTIME / "master_brain_influence_report.json", {})
    influence = load_json(ECHO_RUNTIME / "system_influence_map.json", {})

    actual = influence.get("current_control_hierarchy") or [
        "Runtime/Daemon",
        "Scanner",
        "Filters/Risk",
        "Master Brain read-only/advisory status",
    ]
    expected = [
        "Ari",
        "ECHO",
        "Unified Brain",
        "Consciousness Core",
        "Master Brain",
        "Scanner/Filters/Risk",
        "Execution/Outcome Tracker",
        "Learning/Evolution/Memory",
    ]

    missing = []
    missing.extend(unified.get("missing_components", []))
    missing.extend(consciousness.get("missing_evidence", []))
    missing.extend(influence.get("missing_influence_links", []))

    return {
        "schema": "titan_echo.batch_b_summary.v1",
        "timestamp_ist": timestamp_ist(),
        "current_real_top_authority": master.get("current_authority_verdict", "UNKNOWN"),
        "unified_brain_gap_score": int(unified.get("unified_brain_gap_score", 100)),
        "consciousness_influence_score": int(consciousness.get("consciousness_influence_score", 0)),
        "master_brain_influence_score": int(master.get("master_brain_influence_score", 0)),
        "system_influence_score": int(influence.get("system_influence_score", 0)),
        "strongest_real_influence_paths": influence.get("top_influence_chains", []),
        "weakest_or_missing_influence_paths": unique(missing, 15),
        "actual_control_hierarchy": actual,
        "expected_final_hierarchy": expected,
        "gap_between_current_and_target": [
            "Unified Brain is missing or not connected.",
            "Consciousness Core is not proven to directly change final decisions.",
            "Master Brain exists and is consumed, but current runtime evidence is read-only/advisory.",
            "Learning/evolution outcome improvement is only partially proven from Batch A.",
        ],
        "recommended_next_missions": [
            "Build Unified Brain shadow artifact contract and checker.",
            "Add consciousness-to-decision trace IDs with before/after rank fields.",
            "Add Master Brain cycle lineage from scanner candidate to outcome tracker.",
            "Run a paper-only influence experiment before any live integration.",
        ],
        "verdict": verdicts(unified, consciousness, master),
    }


def main() -> int:
    report = build_report()
    write_json(OUTPUT_PATH, report)
    print("TITAN ECHO Batch B summary: PASSED")
    print(f"Current real top authority: {report['current_real_top_authority']}")
    print(f"Unified Brain gap score: {report['unified_brain_gap_score']}")
    print(f"Consciousness influence score: {report['consciousness_influence_score']}")
    print(f"Master Brain influence score: {report['master_brain_influence_score']}")
    print(f"System influence score: {report['system_influence_score']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
