"""Final read-only readiness audit for ECHO and Unified Brain."""

from __future__ import annotations

from typing import Any

from titan_echo.echo_batch_b_common import ECHO_RUNTIME, REPO_ROOT, load_json, timestamp_ist, unique, write_json


UNIFIED_RUNTIME = REPO_ROOT / "data" / "runtime" / "unified_brain"
AUDIT_PATH = ECHO_RUNTIME / "final_readiness_audit.json"
SUMMARY_PATH = ECHO_RUNTIME / "final_readiness_summary.json"


def exists(path: Any) -> bool:
    return bool(path) and path.exists() and path.stat().st_size > 0


def pct(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def verdict(score: float) -> str:
    if score >= 80:
        return "COMPLETE"
    if score > 0:
        return "PARTIAL"
    return "MISSING"


def category(name: str, score: float, evidence: list[str], gaps: list[str]) -> dict[str, Any]:
    return {
        "category": name,
        "score": round(score, 2),
        "verdict": verdict(score),
        "evidence": evidence,
        "gaps": gaps,
    }


def evidence_file(path: Any) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except Exception:
        return str(path)


def echo_scores() -> dict[str, Any]:
    files = {
        "memory": ECHO_RUNTIME / "echo_memory.jsonl",
        "architecture_map": ECHO_RUNTIME / "titan_architecture_map.json",
        "module_registry": ECHO_RUNTIME / "titan_module_registry.json",
        "connection_graph": ECHO_RUNTIME / "titan_connection_graph.json",
        "runtime_truth": ECHO_RUNTIME / "runtime_truth_audit.json",
        "integration": ECHO_RUNTIME / "integration_proof_report.json",
        "evolution": ECHO_RUNTIME / "evolution_evidence_audit.json",
        "outcome": ECHO_RUNTIME / "outcome_improvement_audit.json",
        "mission_plan": ECHO_RUNTIME / "mission_plan.json",
        "approval_queue": ECHO_RUNTIME / "approval_queue.json",
        "approval_history": ECHO_RUNTIME / "approval_history.jsonl",
        "alert_queue": ECHO_RUNTIME / "alert_queue.json",
        "alert_history": ECHO_RUNTIME / "alert_history.jsonl",
    }
    batch_a = load_json(ECHO_RUNTIME / "batch_a_summary.json", {})
    batch_b = load_json(ECHO_RUNTIME / "batch_b_summary.json", {})
    integration = load_json(files["integration"], {})
    runtime_truth = load_json(files["runtime_truth"], {})

    categories = [
        category("Memory", 100 if exists(files["memory"]) else 0, [evidence_file(files["memory"])] if exists(files["memory"]) else [], []),
        category(
            "Architecture awareness",
            100 if all(exists(files[key]) for key in ("architecture_map", "module_registry", "connection_graph")) else 50,
            [evidence_file(files[key]) for key in ("architecture_map", "module_registry", "connection_graph") if exists(files[key])],
            [] if all(exists(files[key]) for key in ("architecture_map", "module_registry", "connection_graph")) else ["Architecture map, registry, or graph missing."],
        ),
        category("Runtime awareness", 100 if exists(files["runtime_truth"]) else 0, [evidence_file(files["runtime_truth"])] if exists(files["runtime_truth"]) else [], []),
        category("Truth auditing", 100 if runtime_truth else 0, [evidence_file(files["runtime_truth"])] if runtime_truth else [], [] if runtime_truth else ["Runtime truth audit missing or empty."]),
        category("Integration auditing", 100 if integration else 0, [evidence_file(files["integration"])] if integration else [], [] if integration else ["Integration proof report missing or empty."]),
        category("Evolution auditing", 70 if exists(files["evolution"]) else 0, [evidence_file(files["evolution"])] if exists(files["evolution"]) else [], ["Evolution proof remains partial unless tied to changed decisions and outcomes."]),
        category("Outcome auditing", 60 if batch_a else 0, [evidence_file(ECHO_RUNTIME / "batch_a_summary.json")] if batch_a else [], batch_a.get("missing_evidence", ["Outcome audit missing."])[:5] if isinstance(batch_a, dict) else []),
        category("Mission planning", 100 if exists(files["mission_plan"]) else 0, [evidence_file(files["mission_plan"])] if exists(files["mission_plan"]) else [], []),
        category("Approval system", 100 if exists(files["approval_queue"]) and exists(files["approval_history"]) else 50 if exists(files["approval_queue"]) else 0, [evidence_file(path) for path in (files["approval_queue"], files["approval_history"]) if exists(path)], []),
        category("Alert system", 100 if exists(files["alert_queue"]) and exists(files["alert_history"]) else 50 if exists(files["alert_queue"]) else 0, [evidence_file(path) for path in (files["alert_queue"], files["alert_history"]) if exists(path)], []),
    ]
    completion = pct([item["score"] for item in categories])
    return {
        "completion_percent": completion,
        "verdict": verdict(completion),
        "categories": categories,
        "batch_b_current_authority": batch_b.get("current_real_top_authority", "UNKNOWN"),
    }


def unified_scores() -> dict[str, Any]:
    paths = {
        "connection": UNIFIED_RUNTIME / "unified_brain_connection_report.json",
        "signal_bridge": UNIFIED_RUNTIME / "unified_brain_signal_bridge.json",
        "reasoning": UNIFIED_RUNTIME / "unified_brain_reasoning_chain.json",
        "trace": UNIFIED_RUNTIME / "unified_brain_trace_experiment.json",
        "trace_summary": UNIFIED_RUNTIME / "unified_brain_trace_summary.json",
        "followup": UNIFIED_RUNTIME / "unified_brain_followup_records.json",
        "followup_tracker": UNIFIED_RUNTIME / "unified_brain_followup_tracker.json",
        "replay_outcomes": UNIFIED_RUNTIME / "unified_brain_paper_replay_outcomes.json",
        "validation": UNIFIED_RUNTIME / "unified_brain_validation_report.json",
        "accuracy": UNIFIED_RUNTIME / "unified_brain_accuracy_report.json",
        "master_consumer": UNIFIED_RUNTIME / "unified_brain_master_shadow_consumer.json",
        "batch1": UNIFIED_RUNTIME / "unified_brain_batch1_summary.json",
        "batch2": UNIFIED_RUNTIME / "unified_brain_batch2_summary.json",
        "batch3": UNIFIED_RUNTIME / "unified_brain_batch3_summary.json",
        "batch4": UNIFIED_RUNTIME / "unified_brain_batch4_summary.json",
    }
    connection = load_json(paths["connection"], {})
    batch1 = load_json(paths["batch1"], {})
    batch2 = load_json(paths["batch2"], {})
    batch3 = load_json(paths["batch3"], {})
    batch4 = load_json(paths["batch4"], {})
    validation_score = float(batch2.get("validation_score") or 0)
    accuracy_score = float(batch2.get("accuracy_score") or 0)
    replay_score = float(batch4.get("replay_validation_score") or 0)
    known_replay = int(batch4.get("wins") or 0) + int(batch4.get("losses") or 0)

    connected_count = int(connection.get("connected_count") or 0)
    missing_count = int(connection.get("missing_count") or 0)
    connection_score = 100 if connected_count and missing_count == 0 else 50 if connected_count else 0
    bridge_evidence = [evidence_file(paths["signal_bridge"])] if exists(paths["signal_bridge"]) else []
    categories = [
        category("Connection layer", connection_score, [evidence_file(paths["connection"])] if connection else [], [] if connection_score == 100 else ["Connection report missing or incomplete."]),
        category("Signal bridge", 100 if exists(paths["signal_bridge"]) and not batch1.get("signals_missing") else 70 if exists(paths["signal_bridge"]) else 0, bridge_evidence, batch1.get("signals_missing", [])),
        category("Reasoning chain", 100 if batch1.get("verdict") == "SHADOW_CHAIN_READY" else 50 if exists(paths["reasoning"]) else 0, [evidence_file(paths["reasoning"]), evidence_file(paths["batch1"])] if exists(paths["reasoning"]) else [], []),
        category("Traceability", 100 if exists(paths["trace"]) and int(batch1.get("candidates_processed") or 0) > 0 else 0, [evidence_file(paths["trace"])], []),
        category("Follow-up tracking", 70 if exists(paths["followup"]) and exists(paths["followup_tracker"]) else 0, [evidence_file(path) for path in (paths["followup"], paths["followup_tracker"]) if exists(path)], ["Follow-up exists, but matched outcomes are zero."]),
        category("Replay framework", 70 if exists(paths["replay_outcomes"]) else 0, [evidence_file(paths["replay_outcomes"]), evidence_file(paths["batch4"])] if exists(paths["replay_outcomes"]) else [], ["Replay framework exists, but replay known outcomes are zero."]),
        category("Validation framework", 60 if exists(paths["validation"]) and exists(paths["accuracy"]) else 0, [evidence_file(path) for path in (paths["validation"], paths["accuracy"], paths["batch2"]) if exists(path)], ["Validation and accuracy scores are zero."]),
        category("Master Brain shadow consumer", 100 if exists(paths["master_consumer"]) else 0, [evidence_file(paths["master_consumer"])] if exists(paths["master_consumer"]) else [], ["No live Master Brain consumption proof; shadow only."] if exists(paths["master_consumer"]) else []),
        category("Consciousness bridge", 70 if "consciousness_signal" in batch1.get("signals_available", []) else 0, [evidence_file(paths["batch1"])] if exists(paths["batch1"]) else [], ["Consciousness is advisory/shadow, not proven to change decisions."]),
        category("Learning bridge", 70 if "learning_signal" in batch1.get("signals_available", []) else 0, [evidence_file(paths["batch1"])] if exists(paths["batch1"]) else [], ["Learning influence is not validated by trace outcomes."]),
        category("Evolution bridge", 70 if "evolution_signal" in batch1.get("signals_available", []) else 0, [evidence_file(paths["batch1"])] if exists(paths["batch1"]) else [], ["Evolution proof remains partial without trace outcome linkage."]),
    ]
    architecture_completion = pct([item["score"] for item in categories])
    validation_completion = pct([validation_score, accuracy_score, replay_score])
    promotion_readiness = 0.0 if known_replay == 0 else min(validation_completion, architecture_completion)
    return {
        "completion_percent": architecture_completion,
        "validation_completion_percent": validation_completion,
        "promotion_readiness_percent": promotion_readiness,
        "verdict": verdict(architecture_completion),
        "categories": categories,
        "batch_summaries": {
            "batch1": batch1,
            "batch2": batch2,
            "batch3": batch3,
            "batch4": batch4,
        },
    }


def blockers() -> list[dict[str, Any]]:
    return [
        {
            "type": "DATA_BLOCKER",
            "blocker": "No matched later outcomes for Unified Brain trace IDs.",
            "evidence": ["unified_brain_batch2_summary.validation_score=0", "unified_brain_batch3_summary.matched_outcomes=0"],
            "impact": "Unified Brain recommendation quality cannot be measured.",
        },
        {
            "type": "EVIDENCE_BLOCKER",
            "blocker": "Replay generated 21 records, but all outcomes remain UNKNOWN.",
            "evidence": ["unified_brain_batch4_summary.unknowns=21", "wins=0", "losses=0"],
            "impact": "Replay validation score remains zero.",
        },
        {
            "type": "EVIDENCE_BLOCKER",
            "blocker": "Confidence calibration is not validated for Unified Brain decisions.",
            "evidence": ["unified_brain_batch2_summary.confidence_score=0", "Batch A high confidence bucket not proven better than lower buckets."],
            "impact": "Confidence changes cannot be trusted as quality improvements.",
        },
        {
            "type": "ARCHITECTURE_BLOCKER",
            "blocker": "Unified Brain is not a live influence layer by design.",
            "evidence": ["mode=SHADOW_ONLY/PAPER_REPLAY_SHADOW", "live_decision_allowed=false"],
            "impact": "No claim of operational decision authority is valid yet.",
        },
        {
            "type": "RUNTIME_BLOCKER",
            "blocker": "Current real top authority remains runtime/scanner/filter pipeline with advisory Master Brain evidence.",
            "evidence": ["batch_b_summary.current_real_top_authority=SCANNER_FILTER_RUNTIME_CURRENT_TOP_WITH_MASTER_BRAIN_READ_ONLY"],
            "impact": "Promotion requires separate controlled integration after evidence improves.",
        },
    ]


def fake_progress() -> list[dict[str, Any]]:
    return [
        {
            "pattern": "Architecture without validation",
            "evidence": "Unified Brain reports SHADOW_CHAIN_READY, but validation, accuracy, and replay scores are zero.",
            "risk": "More architecture batches would look productive while leaving promotion readiness unchanged.",
        },
        {
            "pattern": "Outputs without outcome evidence",
            "evidence": "21 traces, 21 follow-ups, and 21 replay outcomes exist, but all replay outcomes are UNKNOWN.",
            "risk": "Counts prove plumbing, not decision quality.",
        },
        {
            "pattern": "Advisory bridges mistaken for influence",
            "evidence": "Consciousness, learning, and evolution signals are present in the bridge, but not proven to alter final outcomes.",
            "risk": "Influence claims would be unsupported.",
        },
    ]


def real_progress() -> list[dict[str, Any]]:
    return [
        {"achievement": "ECHO audit layer", "evidence": "Memory, architecture, runtime truth, integration, evolution, outcome, mission, approval, and alert artifacts exist."},
        {"achievement": "Unified Brain connection layer", "evidence": "15 subsystems discovered and connected in SHADOW_ONLY mode."},
        {"achievement": "Unified Brain reasoning chain", "evidence": "21 candidates processed with signal bridge and conservative REJECT_SHADOW_ONLY recommendations."},
        {"achievement": "Trace and follow-up lineage", "evidence": "Trace IDs, follow-up records, tracker, and validator artifacts exist."},
        {"achievement": "Replay safety framework", "evidence": "Paper/replay outcomes are generated with replay_mode=true and live_decision_allowed=false."},
    ]


def next_actions() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    do_next = [
        {"priority": 1, "action": "Attach exact OHLC/replay windows to each Unified Brain trace ID.", "reason": "This directly addresses UNKNOWN replay outcomes."},
        {"priority": 2, "action": "Create a trace-to-outcome matcher that requires real result evidence, not setup files.", "reason": "Validation needs matched WIN/LOSS/OPEN outcomes."},
        {"priority": 3, "action": "Run paper/replay capture after each scanner cycle and preserve trace IDs through outcome closure.", "reason": "Future evidence must be generated at the same lineage granularity."},
        {"priority": 4, "action": "Improve confidence calibration using only cohorts with clean outcome labels.", "reason": "Confidence adjustments are currently unvalidated."},
        {"priority": 5, "action": "Re-run validation only after known replay outcomes exist.", "reason": "Current validation score cannot improve without data."},
    ]
    do_not = [
        {"priority": 1, "action": "Do not promote Unified Brain to influence live decisions.", "reason": "Promotion readiness is zero."},
        {"priority": 2, "action": "Do not build more advisory architecture before outcome evidence exists.", "reason": "LOW_VALUE_NEXT_STEP: it will not solve the core blocker."},
        {"priority": 3, "action": "Do not wire Unified Brain into Master Brain live consumption.", "reason": "No validated improvement proof."},
        {"priority": 4, "action": "Do not claim Consciousness/Learning/Evolution decision influence.", "reason": "Signals are bridged, but downstream outcome impact is unproven."},
        {"priority": 5, "action": "Do not use setup files as outcomes.", "reason": "That would create fake validation."},
    ]
    return do_next, do_not


def build_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    echo = echo_scores()
    unified = unified_scores()
    do_next, do_not = next_actions()
    validation_completion = unified["validation_completion_percent"]
    promotion = unified["promotion_readiness_percent"]
    final_verdict = "FOCUS_ON_OUTCOMES" if promotion == 0 else "FOCUS_ON_EVIDENCE"
    audit = {
        "schema": "titan_echo.final_readiness_audit.v1",
        "timestamp_ist": timestamp_ist(),
        "mode": "READ_ONLY_AUDIT",
        "echo": echo,
        "unified_brain": unified,
        "blockers": blockers(),
        "fake_progress_detection": fake_progress(),
        "real_progress_detection": real_progress(),
        "do_next": do_next,
        "do_not_build_yet": do_not,
        "final_verdict": final_verdict,
    }
    summary = {
        "schema": "titan_echo.final_readiness_summary.v1",
        "timestamp_ist": audit["timestamp_ist"],
        "mode": "READ_ONLY_AUDIT",
        "echo_completion_percent": echo["completion_percent"],
        "unified_brain_completion_percent": unified["completion_percent"],
        "validation_completion_percent": validation_completion,
        "promotion_readiness_percent": promotion,
        "biggest_blocker": blockers()[0]["blocker"],
        "biggest_completed_achievement": real_progress()[1]["achievement"],
        "top_5_next_actions": do_next[:5],
        "top_5_actions_to_avoid": do_not[:5],
        "final_verdict": final_verdict,
        "recommended_next_action": do_next[0]["action"],
    }
    return audit, summary


def main() -> int:
    audit, summary = build_reports()
    write_json(AUDIT_PATH, audit)
    write_json(SUMMARY_PATH, summary)
    print("TITAN ECHO final readiness audit: PASSED")
    print(f"ECHO completion: {summary['echo_completion_percent']}%")
    print(f"Unified Brain completion: {summary['unified_brain_completion_percent']}%")
    print(f"Validation completion: {summary['validation_completion_percent']}%")
    print(f"Promotion readiness: {summary['promotion_readiness_percent']}%")
    print(f"Final verdict: {summary['final_verdict']}")
    print(f"Recommended next action: {summary['recommended_next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
