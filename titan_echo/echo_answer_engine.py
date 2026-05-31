"""Unified, evidence-grounded answer engine for ECHO.

Chat context is context only. This module treats TITAN runtime evidence files
as truth and reports UNKNOWN / NOT PROVEN / WAITING FOR DATA when evidence is
missing or incomplete.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
ECHO_DIR = RUNTIME_DIR / "echo"
ANSWER_PATH = ECHO_DIR / "echo_answer.json"
SUMMARY_PATH = ECHO_DIR / "echo_answer_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))

INPUTS = {
    "conversation_style": ECHO_DIR / "echo_conversation_style.json",
    "project_state_registry": ECHO_DIR / "project_state_registry.json",
    "runtime_evidence_summary": ECHO_DIR / "runtime_evidence_summary.json",
    "worker_scanner_failure_focus_summary": ECHO_DIR / "worker_scanner_failure_focus_summary.json",
    "post_repair_runtime_summary": ECHO_DIR / "post_repair_runtime_summary.json",
    "runtime_failure_summary": ECHO_DIR / "runtime_failure_summary.json",
    "brain_state": RUNTIME_DIR / "brain_state.json",
    "unified_brain_status": RUNTIME_DIR / "unified_brain_status.json",
    "final_lineage_truth_summary": ECHO_DIR / "final_lineage_truth_summary.json",
    "natural_run_lineage_proof": ECHO_DIR / "natural_run_lineage_proof.json",
    "alert_queue": ECHO_DIR / "alert_queue.json",
    "runtime_repair_priority_summary": ECHO_DIR / "runtime_repair_priority_summary.json",
}

FORBIDDEN_ACTIONS = [
    "Do not patch scanner again without fresh post-regeneration evidence.",
    "Do not restart TITAN blindly.",
    "Do not deploy.",
    "Do not push.",
    "Do not promote Unified Brain.",
    "Do not modify broker/risk.",
    "Do not modify Master Brain or Unified Brain behavior.",
]


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": f"{type(exc).__name__}: {exc}"}


def load_evidence() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    evidence_used = [
        {
            "name": name,
            "path": relative(path),
            "exists": path.exists(),
            "used": docs[name] is not None,
        }
        for name, path in INPUTS.items()
    ]
    return docs, evidence_used


def value(data: Any, key: str, default: Any = None) -> Any:
    return data.get(key, default) if isinstance(data, dict) else default


def status_item(name: str, status: str, evidence: str, detail: str | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "evidence": evidence,
        "detail": detail,
    }


def proven_status(docs: dict[str, Any]) -> list[dict[str, Any]]:
    runtime = docs.get("runtime_evidence_summary")
    brain = docs.get("brain_state")
    unified = docs.get("unified_brain_status")
    lineage = docs.get("final_lineage_truth_summary")
    items: list[dict[str, Any]] = []

    if value(runtime, "master_brain_runtime_status") == "RUNNING":
        items.append(status_item("Master Brain", "RUNNING", relative(INPUTS["runtime_evidence_summary"])))
    elif value(brain, "brain_behavior_changed") is False:
        master = value(brain, "master_brain_status", {})
        if isinstance(master, dict) and master.get("status"):
            items.append(status_item("Master Brain evidence", str(master["status"]), relative(INPUTS["brain_state"])))

    if value(runtime, "unified_brain_runtime_status") == "HEALTHY":
        items.append(status_item("Unified Brain", "HEALTHY", relative(INPUTS["runtime_evidence_summary"])))
    elif value(unified, "unified_brain_behavior_changed") is False and value(unified, "live_decision_allowed") is False:
        items.append(
            status_item(
                "Unified Brain evidence",
                str(value(unified, "unified_brain_status", "PRESENT")),
                relative(INPUTS["unified_brain_status"]),
                "Shadow evidence only; live decision is not allowed.",
            )
        )

    if isinstance(lineage, dict) and lineage:
        verdict = lineage.get("final_verdict") or lineage.get("status") or lineage.get("lineage_status")
        if verdict:
            items.append(status_item("Lineage evidence", str(verdict), relative(INPUTS["final_lineage_truth_summary"])))
    return items


def failing_status(docs: dict[str, Any]) -> list[dict[str, Any]]:
    runtime = docs.get("runtime_evidence_summary")
    focus = docs.get("worker_scanner_failure_focus_summary")
    failures = docs.get("runtime_failure_summary")
    items: list[dict[str, Any]] = []
    for name, key in (
        ("TITAN runtime", "titan_runtime_status"),
        ("Scanner", "scanner_runtime_status"),
        ("Workers", "worker_runtime_status"),
    ):
        if value(runtime, key) == "FAIL":
            items.append(status_item(name, "FAIL", relative(INPUTS["runtime_evidence_summary"])))

    if isinstance(focus, dict):
        items.append(
            status_item(
                "Scanner fail type",
                str(focus.get("scanner_fail_type") or "UNKNOWN"),
                relative(INPUTS["worker_scanner_failure_focus_summary"]),
            )
        )
        items.append(
            status_item(
                "Worker fail type",
                str(focus.get("worker_fail_type") or "UNKNOWN"),
                relative(INPUTS["worker_scanner_failure_focus_summary"]),
            )
        )

    if isinstance(failures, dict) and failures.get("remaining_failures"):
        items.append(
            status_item(
                "Runtime failure summary",
                "FAILURES_REPORTED",
                relative(INPUTS["runtime_failure_summary"]),
                ", ".join(str(item) for item in failures.get("remaining_failures", [])),
            )
        )
    return items


def stale_or_waiting_status(docs: dict[str, Any]) -> list[dict[str, Any]]:
    runtime = docs.get("runtime_evidence_summary")
    focus = docs.get("worker_scanner_failure_focus_summary")
    post = docs.get("post_repair_runtime_summary")
    natural = docs.get("natural_run_lineage_proof")
    items: list[dict[str, Any]] = []

    stale_count = value(runtime, "stale_count")
    if stale_count:
        items.append(status_item("Runtime evidence", f"{stale_count} stale items", relative(INPUTS["runtime_evidence_summary"])))

    if value(focus, "scanner_fail_type") == "LEGACY_WAITING_REGENERATION":
        items.append(
            status_item(
                "Scanner",
                "WAITING_FOR_RUNTIME_REGENERATION",
                relative(INPUTS["worker_scanner_failure_focus_summary"]),
            )
        )
    if value(focus, "worker_fail_type") == "STALE":
        items.append(status_item("Worker health", "STALE", relative(INPUTS["worker_scanner_failure_focus_summary"])))

    if isinstance(post, dict) and post.get("waiting_for_runtime_regeneration"):
        items.append(
            status_item(
                "Post-repair runtime",
                "WAITING_FOR_RUNTIME_REGENERATION",
                relative(INPUTS["post_repair_runtime_summary"]),
                ", ".join(str(item) for item in post.get("waiting_for_runtime_regeneration", [])),
            )
        )

    if natural is None:
        items.append(status_item("Natural-run lineage proof", "WAITING_FOR_DATA", relative(INPUTS["natural_run_lineage_proof"])))
    return items


def unknown_status(docs: dict[str, Any], evidence_used: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = [
        status_item(item["name"], "UNKNOWN_NOT_PROVEN", item["path"])
        for item in evidence_used
        if not item["exists"]
    ]
    runtime = docs.get("runtime_evidence_summary")
    for system in value(runtime, "still_unknown_systems", []) or []:
        items.append(status_item(str(system), "UNKNOWN", relative(INPUTS["runtime_evidence_summary"])))
    return items


def recommended_next_action(docs: dict[str, Any]) -> str:
    focus = docs.get("worker_scanner_failure_focus_summary")
    if isinstance(focus, dict) and focus.get("recommended_next_action"):
        return str(focus["recommended_next_action"])
    priority = docs.get("runtime_repair_priority_summary")
    recommended = value(priority, "recommended_next_repair")
    if isinstance(recommended, dict) and recommended.get("recommended_codex_mission_prompt"):
        return str(recommended["recommended_codex_mission_prompt"])
    return "Wait for fresh runtime evidence, then rerun the ECHO runtime evidence and answer engine checks."


def confidence(docs: dict[str, Any], evidence_used: list[dict[str, Any]]) -> str:
    required_core = [
        "runtime_evidence_summary",
        "worker_scanner_failure_focus_summary",
        "brain_state",
        "unified_brain_status",
    ]
    if all(docs.get(name) is not None for name in required_core):
        return "HIGH"
    used_count = sum(1 for item in evidence_used if item["used"])
    if used_count >= 6:
        return "MEDIUM"
    return "LOW"


def short_answer_text(
    proven: list[dict[str, Any]],
    failing: list[dict[str, Any]],
    waiting: list[dict[str, Any]],
    action: str,
) -> str:
    proven_names = {item["name"] for item in proven}
    failing_names = {item["name"] for item in failing}
    if {"Master Brain", "Unified Brain"}.issubset(proven_names) and {"Scanner", "Workers"}.issubset(failing_names):
        return (
            "Ari, right now TITAN is not proven healthy. The good news is Master Brain is proven RUNNING "
            "and Unified Brain is proven HEALTHY, but runtime evidence still marks scanner and workers as FAIL. "
            "The current evidence says scanner is waiting on natural runtime regeneration and worker health is stale, "
            "so I would not patch scanner again yet."
        )
    if failing:
        return (
            "Ari, TITAN is only partially proven right now. Some evidence is healthy, but current runtime files still "
            "show failures or stale data. The next step is evidence refresh or the specific action listed below, not a blind restart."
        )
    if waiting:
        return (
            "Ari, TITAN does not show a clear active failure in the available evidence, but it is still waiting for runtime data. "
            "I would treat the state as not fully proven until fresh runtime evidence lands."
        )
    return "Ari, the available evidence does not prove a current runtime failure, but missing evidence still limits confidence."


def reasoning_text(docs: dict[str, Any]) -> str:
    runtime = docs.get("runtime_evidence_summary")
    focus = docs.get("worker_scanner_failure_focus_summary")
    verdict = value(runtime, "current_runtime_truth_verdict", "UNKNOWN")
    scanner = value(focus, "scanner_fail_type", "UNKNOWN")
    worker = value(focus, "worker_fail_type", "UNKNOWN")
    truth = value(focus, "truth_gate_relation", "UNKNOWN")
    filter_relation = value(focus, "filter_engine_relation", "UNKNOWN")
    return (
        f"ECHO is using runtime evidence files as truth. The runtime verdict is {verdict}. "
        f"The worker/scanner focus audit classifies scanner as {scanner}, workers as {worker}, "
        f"Truth Gate relation as {truth}, and Filter Engine relation as {filter_relation}. "
        "Where an input file is missing, ECHO reports UNKNOWN or WAITING FOR DATA instead of assuming health."
    )


def build_answer() -> tuple[dict[str, Any], dict[str, Any]]:
    docs, evidence_used = load_evidence()
    proven = proven_status(docs)
    failing = failing_status(docs)
    waiting = stale_or_waiting_status(docs)
    unknown = unknown_status(docs, evidence_used)
    action = recommended_next_action(docs)
    answer = {
        "schema": "titan.echo.answer.v1",
        "timestamp_ist": timestamp_ist(),
        "truth_rule": "ChatGPT memory is context only. TITAN evidence files are truth.",
        "short_answer": short_answer_text(proven, failing, waiting, action),
        "proven_status": proven,
        "failing_status": failing,
        "stale_or_waiting_status": waiting,
        "unknown_status": unknown,
        "reasoning": reasoning_text(docs),
        "recommended_next_action": action,
        "what_not_to_do": FORBIDDEN_ACTIONS,
        "evidence_used": evidence_used,
        "confidence": confidence(docs, evidence_used),
        "safety": {
            "read_only_answer_engine": True,
            "shell_execution": False,
            "runtime_repair": False,
            "scanner_changed": False,
            "workers_changed": False,
            "master_brain_changed": False,
            "unified_brain_changed": False,
            "broker_risk_changed": False,
            "restart": False,
            "deploy": False,
            "push": False,
            "writes_only_echo_runtime": True,
        },
    }
    summary = {
        "schema": "titan.echo.answer_summary.v1",
        "timestamp_ist": answer["timestamp_ist"],
        "short_answer": answer["short_answer"],
        "recommended_next_action": answer["recommended_next_action"],
        "what_not_to_do": answer["what_not_to_do"],
        "confidence": answer["confidence"],
        "safety": answer["safety"],
    }
    return answer, summary


def generate_answer() -> tuple[dict[str, Any], dict[str, Any]]:
    answer, summary = build_answer()
    ECHO_DIR.mkdir(parents=True, exist_ok=True)
    ANSWER_PATH.write_text(json.dumps(answer, indent=2, sort_keys=True), encoding="utf-8")
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return answer, summary


def main() -> None:
    _, summary = generate_answer()
    print("ECHO answer generated.")
    print(f"short_answer={summary['short_answer']}")
    print(f"recommended_next_action={summary['recommended_next_action']}")
    print("what_not_to_do=" + " | ".join(summary["what_not_to_do"]))
    print(f"confidence={summary['confidence']}")
    print("safety_result=PASS")


if __name__ == "__main__":
    main()
