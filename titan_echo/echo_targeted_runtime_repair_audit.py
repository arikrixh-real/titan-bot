"""Targeted ECHO audit for remaining runtime FAIL classifications."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
RUNTIME_REPORT_PATH = ECHO_DIR / "runtime_evidence_report.json"
REPAIR_SUMMARY_PATH = ECHO_DIR / "runtime_repair_priority_summary.json"
FINAL_READINESS_PATH = ECHO_DIR / "final_readiness_summary.json"
ANSWER_PATH = ECHO_DIR / "echo_answer.json"
AUDIT_PATH = ECHO_DIR / "targeted_runtime_repair_audit.json"
SUMMARY_PATH = ECHO_DIR / "targeted_runtime_repair_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:
        return {"_read_error": f"{type(exc).__name__}: {exc}"}


def write_echo_json(path: Path, payload: dict[str, Any]) -> None:
    resolved_echo = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_echo not in (resolved_path, *resolved_path.parents):
        raise ValueError("targeted runtime audit writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def classify_failure(name: str, item: dict[str, Any]) -> tuple[str, bool, str]:
    reason = str(item.get("reason") or "")
    values = [str(value).upper() for value in item.get("status_values_seen", [])]
    context = item.get("classification_context") if isinstance(item.get("classification_context"), dict) else {}
    if name == "Truth Gate" and "MARKET_CLOSED_NOT_LIVE_SAFE" in reason:
        return "EXPECTED_OFF_HOURS_STANDBY", False, "Truth Gate is blocked by market-closed/trade-not-open safety, not a live runtime defect."
    if name == "Truth Gate" and context.get("expected_off_hours_standby") and any("FAIL" in value for value in values):
        return "FALSE_POSITIVE_CLASSIFICATION", True, "Truth Gate FAIL tokens need market-closed context before classifying runtime failure."
    if name == "Filter Engine" and "FILTER_DIAGNOSTICS_CANDIDATE_REJECTIONS_NOT_RUNTIME_FAILURE" in reason:
        return "STALE_EVIDENCE", False, "Filter diagnostics contain candidate rejection FAILs; stale evidence should not be treated as engine failure."
    if name == "Filter Engine" and any("FAIL" in value for value in values):
        return "FALSE_POSITIVE_CLASSIFICATION", True, "Filter candidate rejection FAIL tokens need separation from engine/runtime failures."
    if item.get("missing_evidence"):
        return "MISSING_EVIDENCE_WAITING_FOR_DATA", False, "Subsystem has missing evidence and should wait for data."
    return "REAL_FAILURE", False, "Evidence still reports failure after ECHO classification context."


def build_audit() -> tuple[dict[str, Any], dict[str, Any]]:
    runtime_report = read_json(RUNTIME_REPORT_PATH) or {}
    repair_summary = read_json(REPAIR_SUMMARY_PATH) or {}
    final_readiness = read_json(FINAL_READINESS_PATH) or {}
    answer = read_json(ANSWER_PATH) or {}
    subsystems = runtime_report.get("subsystems") if isinstance(runtime_report, dict) else {}
    if not isinstance(subsystems, dict):
        subsystems = {}

    fail_sources = []
    resolved_classification_sources = []
    classification_counts: dict[str, int] = {}
    code_change_needed = False
    for name, item in sorted(subsystems.items()):
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        reason = str(item.get("reason") or "")
        if status != "FAIL":
            if name == "Truth Gate" and "MARKET_CLOSED_NOT_LIVE_SAFE" in reason:
                resolved_classification_sources.append(
                    {
                        "subsystem": name,
                        "status": status,
                        "classification": "EXPECTED_OFF_HOURS_STANDBY",
                        "reason": item.get("reason"),
                        "rationale": "Previously hard FAIL evidence is now classified as market-closed/trade-not-open standby.",
                    }
                )
            elif name == "Filter Engine" and "FILTER_DIAGNOSTICS_CANDIDATE_REJECTIONS_NOT_RUNTIME_FAILURE" in reason:
                resolved_classification_sources.append(
                    {
                        "subsystem": name,
                        "status": status,
                        "classification": "FALSE_POSITIVE_CLASSIFICATION",
                        "reason": item.get("reason"),
                        "rationale": "Filter candidate rejection FAIL tokens are not runtime engine failure.",
                    }
                )
            continue
        classification, needs_code, rationale = classify_failure(name, item)
        classification_counts[classification] = classification_counts.get(classification, 0) + 1
        code_change_needed = code_change_needed or needs_code
        fail_sources.append(
            {
                "subsystem": name,
                "status": item.get("status"),
                "classification": classification,
                "code_change_needed": needs_code,
                "reason": item.get("reason"),
                "status_values_seen": item.get("status_values_seen", [])[:20],
                "evidence_files": item.get("evidence_files", []),
                "rationale": rationale,
            }
        )

    safest_next_action = (
        "No protected subsystem repair. Re-run ECHO runtime evidence after classification repair and inspect any remaining REAL_FAILURE."
        if code_change_needed
        else "No repair. Continue evidence refresh and avoid protected subsystem changes."
    )
    audit = {
        "schema": "titan.echo.targeted_runtime_repair_audit.v1",
        "timestamp_ist": timestamp_ist(),
        "inputs": {
            "runtime_evidence_report": str(RUNTIME_REPORT_PATH).replace("\\", "/"),
            "runtime_repair_priority_summary": str(REPAIR_SUMMARY_PATH).replace("\\", "/"),
            "final_readiness_summary": str(FINAL_READINESS_PATH).replace("\\", "/"),
            "echo_answer": str(ANSWER_PATH).replace("\\", "/"),
        },
        "fail_count": len(fail_sources),
        "fail_sources": fail_sources,
        "resolved_classification_sources": resolved_classification_sources,
        "classification_counts": classification_counts,
        "code_change_needed": code_change_needed,
        "safest_next_action": safest_next_action,
        "supporting_context": {
            "repair_summary_recommended_next_repair": repair_summary.get("recommended_next_repair"),
            "final_readiness_verdict": final_readiness.get("final_verdict"),
            "answer_recommended_next_action": answer.get("recommended_next_action"),
        },
        "safety": {
            "read_only_audit": True,
            "scanner_changed": False,
            "broker_changed": False,
            "risk_changed": False,
            "execution_changed": False,
            "master_brain_behavior_changed": False,
            "unified_brain_behavior_changed": False,
            "runtime_workers_changed": False,
            "deploy_or_restart": False,
            "push": False,
        },
        "risk_level": "LOW",
    }
    summary = {
        "schema": "titan.echo.targeted_runtime_repair_summary.v1",
        "timestamp_ist": audit["timestamp_ist"],
        "fail_count": audit["fail_count"],
        "current_fail_source": [item["subsystem"] for item in fail_sources],
        "exact_fail_source": [item["subsystem"] for item in fail_sources] or [
            item["subsystem"] for item in resolved_classification_sources
        ],
        "resolved_classification_sources": resolved_classification_sources,
        "classification_counts": classification_counts,
        "code_change_needed": code_change_needed,
        "safest_next_action": safest_next_action,
        "risk_level": audit["risk_level"],
        "safety": audit["safety"],
    }
    return audit, summary


def main() -> None:
    audit, summary = build_audit()
    write_echo_json(AUDIT_PATH, audit)
    write_echo_json(SUMMARY_PATH, summary)
    print("ECHO targeted runtime repair audit generated.")
    print("exact_fail_source=" + ", ".join(summary["exact_fail_source"]))
    print(f"fail_count={summary['fail_count']}")
    print(f"classification_counts={summary['classification_counts']}")
    print(f"code_change_needed={summary['code_change_needed']}")
    print(f"risk_level={summary['risk_level']}")


if __name__ == "__main__":
    main()
