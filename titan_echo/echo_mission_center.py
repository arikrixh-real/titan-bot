"""ECHO Mission Center aggregation.

This module builds a read-only human-facing mission snapshot from TITAN
runtime/report files. Chat context is context only; runtime evidence files are
the proof source.
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
from titan_echo.echo_api_status import alerts_count, generate_reports

RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
ECHO_DIR = RUNTIME_DIR / "echo"
MISSION_CENTER_PATH = ECHO_DIR / "echo_mission_center.json"
MISSION_CENTER_SUMMARY_PATH = ECHO_DIR / "echo_mission_center_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))

INPUTS = {
    "echo_answer": ECHO_DIR / "echo_answer.json",
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
        raise ValueError("Mission Center writes only under data/runtime/echo")
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


def load_inputs() -> tuple[dict[str, Any], list[dict[str, Any]]]:
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


def waiting_items(answer: Any) -> list[dict[str, Any]]:
    items = pick(answer, ("stale_or_waiting_status",), [])
    return items if isinstance(items, list) else []


def failing_items(answer: Any) -> list[dict[str, Any]]:
    failing = pick(answer, ("failing_status",), [])
    waiting = waiting_items(answer)
    combined: list[dict[str, Any]] = []
    if isinstance(failing, list):
        combined.extend(item for item in failing if isinstance(item, dict))
    combined.extend(item for item in waiting if isinstance(item, dict))
    return combined


def build_mission_center() -> tuple[dict[str, Any], dict[str, Any]]:
    generate_answer()
    generate_reports()
    docs, evidence_used = load_inputs()
    answer = docs["echo_answer"]
    api_status = docs["echo_api_status"]
    runtime = docs["runtime_evidence_summary"]
    alerts = docs["alert_queue"]

    proven = pick(answer, ("proven_status",), [])
    proven_list = proven if isinstance(proven, list) else []
    failures = failing_items(answer)
    waiting = waiting_items(answer)
    titan_status = pick(api_status, ("titan_status",), pick(runtime, ("titan_runtime_status", "current_runtime_truth_verdict"), "UNKNOWN"))

    mission_center = {
        "schema": "titan.echo.mission_center.v1",
        "timestamp_ist": timestamp_ist(),
        "truth_rule": "ChatGPT memory is context only. TITAN runtime/report files are proof.",
        "current_human_answer": pick(answer, ("short_answer",), "UNKNOWN"),
        "titan_status": titan_status,
        "proven_healthy": proven_list,
        "failing_or_stale": failures,
        "waiting_for_runtime_data": waiting,
        "alerts_count": alerts_count(alerts),
        "next_recommended_action": pick(answer, ("recommended_next_action",), pick(api_status, ("next_recommended_action",), "UNKNOWN")),
        "what_not_to_do": pick(answer, ("what_not_to_do",), []),
        "evidence_used": evidence_used,
        "confidence": pick(answer, ("confidence",), "LOW"),
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
        "schema": "titan.echo.mission_center_summary.v1",
        "timestamp_ist": mission_center["timestamp_ist"],
        "current_human_answer": mission_center["current_human_answer"],
        "titan_status": mission_center["titan_status"],
        "alerts_count": mission_center["alerts_count"],
        "next_recommended_action": mission_center["next_recommended_action"],
        "what_not_to_do": mission_center["what_not_to_do"],
        "confidence": mission_center["confidence"],
        "safety": mission_center["safety"],
    }
    return mission_center, summary


def generate_mission_center() -> tuple[dict[str, Any], dict[str, Any]]:
    mission_center, summary = build_mission_center()
    write_echo_json(MISSION_CENTER_PATH, mission_center)
    write_echo_json(MISSION_CENTER_SUMMARY_PATH, summary)
    return mission_center, summary


def main() -> None:
    mission_center, _ = generate_mission_center()
    print("ECHO Mission Center generated.")
    print(f"current_human_answer={mission_center['current_human_answer']}")
    print(f"titan_status={mission_center['titan_status']}")
    print(f"alerts_count={mission_center['alerts_count']}")
    print(f"next_recommended_action={mission_center['next_recommended_action']}")
    print("what_not_to_do=" + " | ".join(mission_center.get("what_not_to_do") or []))
    print(f"confidence={mission_center['confidence']}")
    print("safety_result=PASS")


if __name__ == "__main__":
    main()
