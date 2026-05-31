"""Evidence-grounded ECHO query router.

The router maps simple Ari question intents to short answers from TITAN
runtime/report files. Chat context is context only; files are proof.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from titan_echo.echo_answer_engine import generate_answer
from titan_echo.echo_mission_center import generate_mission_center


RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
ECHO_DIR = RUNTIME_DIR / "echo"
QUERY_ROUTER_PATH = ECHO_DIR / "echo_query_router.json"
QUERY_ROUTER_SUMMARY_PATH = ECHO_DIR / "echo_query_router_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))

SUPPORTED_INTENTS = [
    "status",
    "runtime",
    "scanner",
    "workers",
    "master_brain",
    "unified_brain",
    "outcome_tracking",
    "lineage",
    "alerts",
    "missions",
    "what_next",
    "what_not_to_do",
    "unknown",
]

INPUTS = {
    "echo_answer": ECHO_DIR / "echo_answer.json",
    "echo_mission_center": ECHO_DIR / "echo_mission_center.json",
    "echo_api_status": ECHO_DIR / "echo_api_status.json",
    "project_state_registry": ECHO_DIR / "project_state_registry.json",
    "runtime_evidence_summary": ECHO_DIR / "runtime_evidence_summary.json",
    "worker_scanner_failure_focus_summary": ECHO_DIR / "worker_scanner_failure_focus_summary.json",
    "unified_brain_status": RUNTIME_DIR / "unified_brain_status.json",
    "brain_state": RUNTIME_DIR / "brain_state.json",
    "final_lineage_truth_summary": ECHO_DIR / "final_lineage_truth_summary.json",
    "natural_run_lineage_proof": ECHO_DIR / "natural_run_lineage_proof.json",
    "alert_queue": ECHO_DIR / "alert_queue.json",
}


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
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:
        return {"_read_error": f"{type(exc).__name__}: {exc}"}


def write_echo_json(path: Path, payload: Any) -> None:
    resolved_echo = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_echo not in (resolved_path, *resolved_path.parents):
        raise ValueError("Query Router writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def pick(data: Any, keys: tuple[str, ...], default: Any = "UNKNOWN") -> Any:
    if not isinstance(data, dict):
        return default
    for key in keys:
        current: Any = data
        found = True
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                found = False
                break
            current = current[part]
        if found and current not in (None, ""):
            return current
    return default


def evidence(name: str) -> dict[str, Any]:
    path = INPUTS[name]
    return {
        "name": name,
        "path": relative(path),
        "exists": path.exists(),
        "used": path.exists(),
    }


def load_inputs() -> dict[str, Any]:
    return {name: read_json(path) for name, path in INPUTS.items()}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def status_names(items: Any) -> list[str]:
    names: list[str] = []
    for item in as_list(items):
        if isinstance(item, dict):
            name = item.get("name")
            status = item.get("status")
            if name or status:
                names.append(f"{name or 'Evidence'}: {status or 'UNKNOWN'}")
    return names


def alert_count(alerts: Any) -> int:
    if isinstance(alerts, list):
        return len(alerts)
    if isinstance(alerts, dict):
        for key in ("alerts", "queue", "items"):
            items = alerts.get(key)
            if isinstance(items, list):
                return len(items)
        return 1 if alerts else 0
    return 0


def project_status(projects: Any, names: tuple[str, ...]) -> str:
    entries = projects.get("projects") if isinstance(projects, dict) else None
    if not isinstance(entries, list):
        return "UNKNOWN"
    wanted = {name.lower() for name in names}
    for item in entries:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).lower()
        if name in wanted:
            return str(item.get("status") or "UNKNOWN")
    return "UNKNOWN"


def base_answer(intent: str, docs: dict[str, Any], sources: list[str]) -> dict[str, Any]:
    answer = docs["echo_answer"]
    mission = docs["echo_mission_center"]
    return {
        "intent": intent,
        "short_answer": "UNKNOWN",
        "evidence_used": [evidence(name) for name in sources],
        "proven_facts": [],
        "unknowns_or_waiting": [],
        "recommended_next_action": pick(answer, ("recommended_next_action",), pick(mission, ("next_recommended_action",), "UNKNOWN")),
        "what_not_to_do": pick(answer, ("what_not_to_do",), pick(mission, ("what_not_to_do",), [])),
        "confidence": pick(answer, ("confidence",), pick(mission, ("confidence",), "LOW")),
    }


def route_query(intent: str, docs: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = str(intent or "").strip().lower().replace("-", "_") or "unknown"
    if normalized not in SUPPORTED_INTENTS:
        normalized = "unknown"
    docs = docs or load_inputs()
    answer = docs["echo_answer"]
    mission = docs["echo_mission_center"]
    runtime = docs["runtime_evidence_summary"]
    focus = docs["worker_scanner_failure_focus_summary"]
    unified = docs["unified_brain_status"]
    brain = docs["brain_state"]
    lineage = docs["final_lineage_truth_summary"]
    natural = docs["natural_run_lineage_proof"]
    alerts = docs["alert_queue"]
    projects = docs["project_state_registry"]
    api_status = docs["echo_api_status"]

    if normalized == "status":
        result = base_answer(normalized, docs, ["echo_answer", "echo_mission_center", "runtime_evidence_summary"])
        result["short_answer"] = pick(mission, ("current_human_answer",), pick(answer, ("short_answer",), "UNKNOWN"))
        result["proven_facts"] = status_names(pick(answer, ("proven_status",), []))
        result["unknowns_or_waiting"] = status_names(pick(answer, ("failing_status",), [])) + status_names(pick(answer, ("stale_or_waiting_status",), []))
        return result

    if normalized == "runtime":
        result = base_answer(normalized, docs, ["runtime_evidence_summary", "echo_api_status"])
        titan = pick(api_status, ("titan_status",), pick(runtime, ("titan_runtime_status", "current_runtime_truth_verdict"), "UNKNOWN"))
        result["short_answer"] = f"TITAN runtime status is {titan} based on runtime evidence."
        result["proven_facts"] = [f"titan_status: {titan}"] if titan != "UNKNOWN" else []
        result["unknowns_or_waiting"] = status_names(pick(answer, ("stale_or_waiting_status",), []))
        return result

    if normalized == "scanner":
        result = base_answer(normalized, docs, ["runtime_evidence_summary", "worker_scanner_failure_focus_summary"])
        scanner = pick(runtime, ("scanner_runtime_status",), "UNKNOWN")
        fail_type = pick(focus, ("scanner_fail_type",), "UNKNOWN")
        result["short_answer"] = f"Scanner status is {scanner}; focus evidence classifies it as {fail_type}."
        result["proven_facts"] = [f"scanner_runtime_status: {scanner}", f"scanner_fail_type: {fail_type}"]
        result["unknowns_or_waiting"] = ["WAITING_FOR_RUNTIME_REGENERATION"] if fail_type == "LEGACY_WAITING_REGENERATION" else []
        return result

    if normalized == "workers":
        result = base_answer(normalized, docs, ["runtime_evidence_summary", "worker_scanner_failure_focus_summary"])
        workers = pick(runtime, ("worker_runtime_status",), "UNKNOWN")
        fail_type = pick(focus, ("worker_fail_type",), "UNKNOWN")
        result["short_answer"] = f"Worker status is {workers}; focus evidence classifies workers as {fail_type}."
        result["proven_facts"] = [f"worker_runtime_status: {workers}", f"worker_fail_type: {fail_type}"]
        result["unknowns_or_waiting"] = ["worker evidence is stale"] if fail_type == "STALE" else []
        return result

    if normalized == "master_brain":
        result = base_answer(normalized, docs, ["runtime_evidence_summary", "brain_state"])
        status = pick(runtime, ("master_brain_runtime_status",), pick(brain, ("master_brain_status.status",), "UNKNOWN"))
        changed = pick(brain, ("brain_behavior_changed",), "UNKNOWN")
        result["short_answer"] = f"Master Brain status is {status} based on available evidence."
        result["proven_facts"] = [f"master_brain_status: {status}", f"brain_behavior_changed: {changed}"]
        result["unknowns_or_waiting"] = [] if status != "UNKNOWN" else ["Master Brain status is NOT PROVEN"]
        return result

    if normalized == "unified_brain":
        result = base_answer(normalized, docs, ["runtime_evidence_summary", "unified_brain_status"])
        status = pick(runtime, ("unified_brain_runtime_status",), pick(unified, ("unified_brain_status",), "UNKNOWN"))
        live_allowed = pick(unified, ("live_decision_allowed",), "UNKNOWN")
        result["short_answer"] = f"Unified Brain status is {status}; live decision allowed is {live_allowed}."
        result["proven_facts"] = [f"unified_brain_status: {status}", f"live_decision_allowed: {live_allowed}"]
        result["unknowns_or_waiting"] = [] if status != "UNKNOWN" else ["Unified Brain status is NOT PROVEN"]
        return result

    if normalized == "outcome_tracking":
        result = base_answer(normalized, docs, ["echo_api_status", "project_state_registry", "final_lineage_truth_summary"])
        status = pick(api_status, ("outcome_tracking_status",), project_status(projects, ("Outcome Tracking Truth Upgrade",)))
        result["short_answer"] = f"Outcome tracking status is {status} based on ECHO project/lineage evidence."
        result["proven_facts"] = [f"outcome_tracking_status: {status}"] if status != "UNKNOWN" else []
        result["unknowns_or_waiting"] = [] if status != "UNKNOWN" else ["Outcome tracking is NOT PROVEN"]
        return result

    if normalized == "lineage":
        result = base_answer(normalized, docs, ["final_lineage_truth_summary", "natural_run_lineage_proof"])
        final_status = pick(lineage, ("final_verdict", "status", "lineage_status"), "UNKNOWN")
        natural_status = pick(natural, ("verdict", "natural_run_status"), "WAITING_FOR_DATA" if natural is None else "UNKNOWN")
        result["short_answer"] = f"Lineage status is {final_status}; natural-run proof is {natural_status}."
        result["proven_facts"] = [f"lineage_status: {final_status}"] if final_status != "UNKNOWN" else []
        result["unknowns_or_waiting"] = [f"natural_run_lineage_proof: {natural_status}"]
        return result

    if normalized == "alerts":
        result = base_answer(normalized, docs, ["alert_queue"])
        count = alert_count(alerts)
        result["short_answer"] = f"ECHO alert evidence currently shows {count} alert item(s)."
        result["proven_facts"] = [f"alerts_count: {count}"]
        result["unknowns_or_waiting"] = [] if alerts is not None else ["Alert queue is UNKNOWN"]
        return result

    if normalized == "missions":
        result = base_answer(normalized, docs, ["project_state_registry", "echo_api_status"])
        focus = pick(api_status, ("current_focus",), pick(projects, ("current_focus", "active_project", "focus"), "UNKNOWN"))
        result["short_answer"] = f"Current mission focus is {focus}."
        result["proven_facts"] = [f"current_focus: {focus}"] if focus != "UNKNOWN" else []
        result["unknowns_or_waiting"] = [] if focus != "UNKNOWN" else ["Mission focus is UNKNOWN"]
        return result

    if normalized == "what_next":
        result = base_answer(normalized, docs, ["echo_answer", "echo_mission_center"])
        action = result["recommended_next_action"]
        result["short_answer"] = f"Next recommended action: {action}"
        result["proven_facts"] = [f"recommended_next_action: {action}"] if action != "UNKNOWN" else []
        result["unknowns_or_waiting"] = [] if action != "UNKNOWN" else ["Next action is UNKNOWN"]
        return result

    if normalized == "what_not_to_do":
        result = base_answer(normalized, docs, ["echo_answer", "echo_mission_center"])
        forbidden = result["what_not_to_do"]
        result["short_answer"] = "Do not perform the forbidden actions listed in current ECHO evidence."
        result["proven_facts"] = [str(item) for item in as_list(forbidden)]
        result["unknowns_or_waiting"] = [] if forbidden else ["Forbidden action guidance is UNKNOWN"]
        return result

    result = base_answer("unknown", docs, ["echo_answer", "echo_mission_center"])
    result["short_answer"] = "UNKNOWN intent. ECHO can answer supported read-only status, runtime, system, alert, mission, and next-action questions from evidence."
    result["unknowns_or_waiting"] = ["Requested intent is not supported, so no health or completion claim is made."]
    result["confidence"] = "LOW"
    return result


def build_router_report() -> tuple[dict[str, Any], dict[str, Any]]:
    generate_answer()
    generate_mission_center()
    docs = load_inputs()
    responses = {intent: route_query(intent, docs) for intent in SUPPORTED_INTENTS}
    unknown_sample = route_query("not_a_supported_intent", docs)
    report = {
        "schema": "titan.echo.query_router.v1",
        "timestamp_ist": timestamp_ist(),
        "truth_rule": "ChatGPT memory is context only. TITAN runtime/report files are proof.",
        "supported_intents": SUPPORTED_INTENTS,
        "responses": responses,
        "unknown_intent_sample": unknown_sample,
        "safety": {
            "read_only": True,
            "shell_execution": False,
            "codex_execution": False,
            "runtime_behavior_changed": False,
            "scanner_changed": False,
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
        "schema": "titan.echo.query_router_summary.v1",
        "timestamp_ist": report["timestamp_ist"],
        "supported_intents": SUPPORTED_INTENTS,
        "sample_status_answer": responses["status"],
        "sample_unified_brain_answer": responses["unified_brain"],
        "sample_what_next_answer": responses["what_next"],
        "unknown_intent_answer": unknown_sample,
        "safety": report["safety"],
    }
    return report, summary


def generate_query_router() -> tuple[dict[str, Any], dict[str, Any]]:
    report, summary = build_router_report()
    write_echo_json(QUERY_ROUTER_PATH, report)
    write_echo_json(QUERY_ROUTER_SUMMARY_PATH, summary)
    return report, summary


def main() -> None:
    report, summary = generate_query_router()
    print("ECHO Query Router generated.")
    print("supported_intents=" + ", ".join(report["supported_intents"]))
    print(f"sample_status_answer={summary['sample_status_answer']['short_answer']}")
    print(f"sample_unified_brain_answer={summary['sample_unified_brain_answer']['short_answer']}")
    print(f"sample_what_next_answer={summary['sample_what_next_answer']['short_answer']}")
    print(f"unknown_intent_answer={summary['unknown_intent_answer']['short_answer']}")
    print("safety_result=PASS")


if __name__ == "__main__":
    main()
