"""Read-only failure split audit for ECHO Batch 6."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
REPORT_PATH = ECHO_DIR / "failure_split_audit.json"
SUMMARY_PATH = ECHO_DIR / "batch6_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))

INPUTS = {
    "runtime_evidence": ECHO_DIR / "runtime_evidence_report.json",
    "runtime_evidence_summary": ECHO_DIR / "runtime_evidence_summary.json",
    "runtime_failure_summary": ECHO_DIR / "runtime_failure_summary.json",
    "post_repair_summary": ECHO_DIR / "post_repair_runtime_summary.json",
    "scanner_repair": ECHO_DIR / "scanner_breakout_integrity_repair_report.json",
    "scanner_investigation": ECHO_DIR / "scanner_breakout_integrity_investigation.json",
}


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None


def write_echo_json(path: Path, payload: Any) -> None:
    resolved_echo = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_echo not in (resolved_path, *resolved_path.parents):
        raise ValueError("Batch 6 writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def subsystem(runtime: dict[str, Any], name: str) -> dict[str, Any]:
    subsystems = runtime.get("subsystems") if isinstance(runtime.get("subsystems"), dict) else {}
    item = subsystems.get(name)
    return item if isinstance(item, dict) else {}


def build_failure_split() -> tuple[dict[str, Any], dict[str, Any]]:
    runtime = read_json(INPUTS["runtime_evidence"]) or {}
    runtime_summary = read_json(INPUTS["runtime_evidence_summary"]) or {}
    failure_summary = read_json(INPUTS["runtime_failure_summary"]) or {}
    post_repair = read_json(INPUTS["post_repair_summary"]) or {}
    scanner_repair = read_json(INPUTS["scanner_repair"]) or {}
    scanner_investigation = read_json(INPUTS["scanner_investigation"]) or {}

    scanner_waiting = "Scanner" in (post_repair.get("waiting_for_runtime_regeneration") or [])
    split = {
        "scanner-caused": {
            "root_cause": (
                "Scanner breakout contract mismatch was patched, but current runtime files still show legacy scanner output."
                if scanner_waiting
                else scanner_investigation.get("classification", {}).get("reason", "Scanner cause not proven from current evidence.")
            ),
            "evidence": {
                "repair_status": scanner_repair.get("status"),
                "repair_verdict": scanner_repair.get("verdict"),
                "post_repair_scanner_status": post_repair.get("scanner_repair_status"),
                "runtime_scanner_status": runtime_summary.get("scanner_runtime_status"),
                "violating_symbols": scanner_investigation.get("violating_symbols"),
            },
            "confidence": "HIGH" if scanner_repair.get("status") == "PASS" else "MEDIUM",
            "fix_priority": 4 if scanner_waiting else 1,
            "recommended_next_action": (
                "Wait for natural runtime regeneration, then rerun runtime evidence. Do not rewrite legacy scanner rows."
                if scanner_waiting
                else "Repair scanner integrity first."
            ),
        },
        "truth-gate-caused": {
            "root_cause": subsystem(runtime, "Truth Gate").get("reason")
            or "Truth Gate evidence shows failure, separate from scanner repair.",
            "evidence": {
                "runtime_status": subsystem(runtime, "Truth Gate").get("status"),
                "status_values_seen": subsystem(runtime, "Truth Gate").get("status_values_seen"),
                "failure_summary": (failure_summary.get("severity_table") or {}).get("Truth Gate"),
            },
            "confidence": "HIGH",
            "fix_priority": 1,
            "recommended_next_action": "Investigate Truth Gate failure reasons and determine which are market-closed, trade-validation, or configuration related.",
        },
        "filter-engine-caused": {
            "root_cause": subsystem(runtime, "Filter Engine").get("reason")
            or "Filter Engine diagnostics include failure tokens.",
            "evidence": {
                "runtime_status": subsystem(runtime, "Filter Engine").get("status"),
                "status_values_seen": subsystem(runtime, "Filter Engine").get("status_values_seen"),
                "failure_summary": (failure_summary.get("severity_table") or {}).get("Filter Engine"),
            },
            "confidence": "HIGH",
            "fix_priority": 2,
            "recommended_next_action": "Audit filter diagnostics by engine and symbol without changing formulas.",
        },
        "worker-caused": {
            "root_cause": failure_summary.get("worker_root_cause")
            or subsystem(runtime, "Runtime Workers").get("reason")
            or "Worker failure is not proven beyond runtime evidence.",
            "evidence": {
                "runtime_status": runtime_summary.get("worker_runtime_status"),
                "worker_evidence": subsystem(runtime, "Runtime Workers").get("status_values_seen"),
                "post_repair_unrelated": "Workers" in (post_repair.get("unrelated_failures") or []),
            },
            "confidence": "HIGH",
            "fix_priority": 3,
            "recommended_next_action": "Inspect worker health, runtime ownership, lock files, and scheduler evidence before restart or repair.",
        },
        "stale-evidence-only": {
            "root_cause": "Master Brain, Unified Brain, and Selector are stale/not freshly proven, not proven failed.",
            "evidence": {
                "master_brain_runtime_status": runtime_summary.get("master_brain_runtime_status"),
                "unified_brain_runtime_status": runtime_summary.get("unified_brain_runtime_status"),
                "failure_summary_master": failure_summary.get("master_brain_root_cause"),
                "failure_summary_unified": failure_summary.get("unified_brain_root_cause"),
            },
            "confidence": "MEDIUM",
            "fix_priority": 5,
            "recommended_next_action": "Observe natural fresh status writes before claiming these systems are running or broken.",
        },
        "external/config issue": {
            "root_cause": "Truth Gate and worker evidence include market/trade-validation, mode, owner, or lock-style signals that may be external/configuration related.",
            "evidence": {
                "truth_gate_values": subsystem(runtime, "Truth Gate").get("status_values_seen"),
                "worker_missing_evidence": subsystem(runtime, "Runtime Workers").get("missing_evidence"),
                "post_repair_unrelated_failures": post_repair.get("unrelated_failures"),
            },
            "confidence": "MEDIUM",
            "fix_priority": 6,
            "recommended_next_action": "Separate market-closed/config/owner/lock evidence from code defects before choosing repair.",
        },
    }
    highest = min(split.items(), key=lambda item: item[1]["fix_priority"])
    report = {
        "schema": "titan.echo.failure_split_audit.v1",
        "timestamp_ist": timestamp_ist(),
        "audit_mode": "READ_ONLY_FAILURE_SPLIT",
        "input_files": [{"path": rel(path), "exists": path.exists()} for path in INPUTS.values()],
        "failure_split": split,
        "highest_priority_failure": {
            "category": highest[0],
            **highest[1],
        },
        "next_repair_mission": highest[1]["recommended_next_action"],
        "safety": {
            "read_only": True,
            "runtime_repair_executed": False,
            "scanner_modified": False,
            "master_brain_modified": False,
            "unified_brain_modified": False,
            "broker_risk_modified": False,
            "deploy_or_restart": False,
            "push_executed": False,
            "shell_execution": False,
            "writes_outside_echo_runtime": False,
        },
    }
    summary = {
        "schema": "titan.echo.batch6_summary.v1",
        "timestamp_ist": report["timestamp_ist"],
        "highest_priority_failure": report["highest_priority_failure"],
        "failure_split_summary": {
            key: {
                "root_cause": value["root_cause"],
                "confidence": value["confidence"],
                "fix_priority": value["fix_priority"],
            }
            for key, value in split.items()
        },
        "next_repair_mission": report["next_repair_mission"],
        "echo_tone_mode": "HUMAN_REASONING_TRUTH_GROUNDED",
        "readiness_for_chatgpt_style_interaction": "READY_WITH_EVIDENCE_LIMITS",
        "safety": report["safety"],
    }
    return report, summary


def generate_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    report, summary = build_failure_split()
    write_echo_json(REPORT_PATH, report)
    write_echo_json(SUMMARY_PATH, summary)
    return report, summary


def main() -> None:
    _, summary = generate_reports()
    highest = summary["highest_priority_failure"]
    print("ECHO failure split audit generated.")
    print(f"highest_priority_failure={highest['category']}")
    print(f"next_repair_mission={summary['next_repair_mission']}")
    print(f"echo_tone_mode={summary['echo_tone_mode']}")
    print(f"readiness_for_chatgpt_style_interaction={summary['readiness_for_chatgpt_style_interaction']}")


if __name__ == "__main__":
    main()
