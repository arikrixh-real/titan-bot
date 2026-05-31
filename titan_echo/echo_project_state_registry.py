"""Evidence-based ECHO Project State Registry.

The registry is a read-only/status artifact. It reads current runtime/report
files and writes only data/runtime/echo/project_state_registry*.json.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
REGISTRY_PATH = ECHO_DIR / "project_state_registry.json"
SUMMARY_PATH = ECHO_DIR / "project_state_registry_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))

STATUS_VALUES = {"COMPLETE", "PARTIAL", "UNKNOWN", "WAITING_FOR_RUNTIME_DATA", "BLOCKED"}
STATE_VALUES = {"SHADOW_READY", "FUTURE_READY", "READ_ONLY_READY", "WAITING_FOR_RUNTIME_DATA", "UNKNOWN"}


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
        raise ValueError("project state registry writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def nested_get(data: Any, keys: tuple[str, ...], default: Any = None) -> Any:
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


def existing(paths: list[Path]) -> list[Path]:
    return [path for path in paths if path.exists()]


def newest_mtime(paths: list[Path]) -> str | None:
    present = existing(paths)
    if not present:
        return None
    newest = max(path.stat().st_mtime for path in present)
    return datetime.fromtimestamp(newest, IST).isoformat()


def alerts_count(data: Any) -> int:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("alerts", "queue", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return len(value)
        return 1 if data else 0
    return 0


def project(
    *,
    name: str,
    status: str,
    state: str,
    paths: list[Path],
    evidence_summary: str,
    missing_evidence: list[str],
    confidence: str,
    next_action: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status if status in STATUS_VALUES else "UNKNOWN",
        "state": state if state in STATE_VALUES else "UNKNOWN",
        "evidence_files": [
            {"path": rel(path), "exists": path.exists()}
            for path in paths
        ],
        "evidence_summary": evidence_summary,
        "missing_evidence": missing_evidence,
        "last_verified_from_file": newest_mtime(paths),
        "confidence": confidence,
        "next_action": next_action,
    }


def build_registry() -> dict[str, Any]:
    final_readiness_path = ECHO_DIR / "final_readiness_summary.json"
    brain_state_path = REPO_ROOT / "data" / "runtime" / "brain_state.json"
    unified_evidence_path = REPO_ROOT / "data" / "runtime" / "unified_brain_status.json"
    runtime_repair_priority_path = ECHO_DIR / "runtime_repair_priority_summary.json"
    unified_status_path = REPO_ROOT / "data" / "runtime" / "unified_brain" / "unified_brain_final_status.json"
    unified_summary_path = REPO_ROOT / "data" / "runtime" / "unified_brain" / "unified_brain_final_summary.json"
    lineage_path = ECHO_DIR / "final_lineage_truth_summary.json"
    natural_path = ECHO_DIR / "natural_run_lineage_proof.json"
    api_status_path = ECHO_DIR / "echo_api_status.json"
    api_contract_path = ECHO_DIR / "echo_api_contract.json"
    scanner_path = REPO_ROOT / "data" / "runtime" / "scanner_status.json"
    master_path = REPO_ROOT / "data" / "runtime" / "master_brain_status.json"
    learning_path = ECHO_DIR / "learning_event_id_adoption_report.json"
    evolution_path = ECHO_DIR / "evolution_event_id_adoption_report.json"
    runtime_paths = [
        REPO_ROOT / "data" / "runtime" / "titan_runtime_status.json",
        REPO_ROOT / "data" / "runtime" / "dashboard_sync_status.json",
        REPO_ROOT / "data" / "runtime" / "ohlc_refresh_status.json",
    ]
    alerts_path = ECHO_DIR / "alert_queue.json"
    mission_path = ECHO_DIR / "mission_plan.json"
    approval_path = ECHO_DIR / "approval_queue.json"

    final_readiness = read_json(final_readiness_path)
    brain_state = read_json(brain_state_path)
    unified_evidence = read_json(unified_evidence_path)
    runtime_repair_priority = read_json(runtime_repair_priority_path)
    unified_status = read_json(unified_status_path)
    unified_summary = read_json(unified_summary_path)
    lineage = read_json(lineage_path)
    natural = read_json(natural_path)
    api_status = read_json(api_status_path)
    api_contract = read_json(api_contract_path)
    scanner = read_json(scanner_path)
    master = read_json(master_path)
    learning = read_json(learning_path)
    evolution = read_json(evolution_path)
    alerts = read_json(alerts_path)
    mission = read_json(mission_path)
    approval = read_json(approval_path)

    projects: list[dict[str, Any]] = []

    echo_evidence = existing([final_readiness_path, api_status_path, api_contract_path, alerts_path, mission_path])
    echo_status = "PARTIAL" if echo_evidence else "UNKNOWN"
    echo_state = "READ_ONLY_READY" if api_status_path.exists() and api_contract_path.exists() else "UNKNOWN"
    projects.append(project(
        name="ECHO",
        status=echo_status,
        state=echo_state,
        paths=[final_readiness_path, api_status_path, api_contract_path, alerts_path, mission_path],
        evidence_summary="ECHO evidence files exist for API/status/alerts/missions." if echo_evidence else "No ECHO evidence files found.",
        missing_evidence=[] if echo_evidence else ["final_readiness_summary.json or ECHO status reports"],
        confidence="MEDIUM" if echo_evidence else "LOW",
        next_action="Keep answering TITAN status only from evidence files.",
    ))

    projects.append(project(
        name="Project State Registry",
        status="PARTIAL" if REGISTRY_PATH.exists() or SUMMARY_PATH.exists() else "UNKNOWN",
        state="READ_ONLY_READY" if REGISTRY_PATH.exists() or SUMMARY_PATH.exists() else "UNKNOWN",
        paths=[REGISTRY_PATH, SUMMARY_PATH],
        evidence_summary="Project registry evidence artifact exists." if REGISTRY_PATH.exists() or SUMMARY_PATH.exists() else "Project registry evidence is missing.",
        missing_evidence=[] if REGISTRY_PATH.exists() or SUMMARY_PATH.exists() else ["project_state_registry.json"],
        confidence="HIGH" if REGISTRY_PATH.exists() or SUMMARY_PATH.exists() else "LOW",
        next_action="Regenerate the ECHO project state registry from evidence before relying on project focus.",
    ))

    brain_status = nested_get(brain_state, ("master_brain_status.status", "status", "verdict"), None)
    projects.append(project(
        name="Brain State",
        status="PARTIAL" if brain_state_path.exists() else "UNKNOWN",
        state="READ_ONLY_READY" if brain_state_path.exists() else "UNKNOWN",
        paths=[brain_state_path],
        evidence_summary=f"Brain state evidence status: {brain_status or 'UNKNOWN_NOT_PROVEN'}.",
        missing_evidence=[] if brain_state_path.exists() else ["brain_state.json"],
        confidence="MEDIUM" if brain_state_path.exists() else "LOW",
        next_action="Use brain_state.json as read-only evidence only; do not infer Master Brain behavior from memory.",
    ))

    ub_verdict = (
        nested_get(unified_evidence, ("unified_brain_status", "evidence_status.status", "status", "verdict"), None)
        or nested_get(unified_status, ("verdict", "status"), None)
        or nested_get(unified_summary, ("verdict", "status"), None)
    )
    ub_promotion_state = nested_get(unified_evidence, ("promotion_state", "evidence_status.promotion_state"), None)
    ub_ready = any(str(value or "").upper().endswith(token) for value in (ub_verdict, ub_promotion_state) for token in ("READY", "COMPLETE", "PASS"))
    projects.append(project(
        name="Unified Brain",
        status="PARTIAL" if unified_evidence_path.exists() or unified_status_path.exists() or unified_summary_path.exists() else "UNKNOWN",
        state="SHADOW_READY" if ub_ready else "UNKNOWN",
        paths=[unified_evidence_path, unified_status_path, unified_summary_path],
        evidence_summary=f"Unified Brain evidence verdict/status: {ub_verdict or 'UNKNOWN'}.",
        missing_evidence=[] if ub_verdict else ["explicit Unified Brain final verdict/status"],
        confidence="MEDIUM" if unified_evidence_path.exists() or unified_status_path.exists() or unified_summary_path.exists() else "LOW",
        next_action="Use Unified Brain evidence files before claiming working/ready status.",
    ))

    repair_status = nested_get(runtime_repair_priority, ("safety_result.status", "status", "verdict"), None)
    projects.append(project(
        name="Runtime Repair Priority",
        status="PARTIAL" if runtime_repair_priority_path.exists() else "UNKNOWN",
        state="READ_ONLY_READY" if runtime_repair_priority_path.exists() else "UNKNOWN",
        paths=[runtime_repair_priority_path],
        evidence_summary=f"Runtime repair priority evidence status: {repair_status or 'UNKNOWN_NOT_PROVEN'}.",
        missing_evidence=[] if runtime_repair_priority_path.exists() else ["runtime_repair_priority_summary.json"],
        confidence="MEDIUM" if runtime_repair_priority_path.exists() else "LOW",
        next_action="Use runtime repair priority as planning evidence only; do not auto-repair protected systems.",
    ))

    outcome_status = nested_get(lineage, ("outcome_tracking_truth_upgrade_status",), None)
    projects.append(project(
        name="Outcome Tracking Truth Upgrade",
        status="COMPLETE" if outcome_status == "COMPLETE" else "UNKNOWN",
        state="FUTURE_READY" if nested_get(lineage, ("LINEAGE_TRUTH_STATUS.future_lineage_ready",), False) else "UNKNOWN",
        paths=[lineage_path],
        evidence_summary=f"Outcome tracking upgrade status from lineage summary: {outcome_status or 'UNKNOWN'}.",
        missing_evidence=[] if outcome_status else ["final_lineage_truth_summary.json with outcome status"],
        confidence="HIGH" if outcome_status == "COMPLETE" else "LOW",
        next_action="Wait for natural fresh records to prove runtime lineage end to end.",
    ))

    natural_verdict = nested_get(natural, ("verdict",), None)
    projects.append(project(
        name="Natural-Run Lineage Proof",
        status="WAITING_FOR_RUNTIME_DATA" if natural_verdict == "WAITING_FOR_RUNTIME_DATA" else ("COMPLETE" if natural_verdict == "PROVEN" else "PARTIAL" if natural_verdict else "UNKNOWN"),
        state="WAITING_FOR_RUNTIME_DATA" if natural_verdict == "WAITING_FOR_RUNTIME_DATA" else "UNKNOWN",
        paths=[natural_path],
        evidence_summary=f"Natural-run lineage proof verdict: {natural_verdict or 'UNKNOWN'}.",
        missing_evidence=[] if natural_verdict else ["natural_run_lineage_proof.json"],
        confidence="HIGH" if natural_verdict else "LOW",
        next_action="Let runtime naturally generate fresh post-adoption records.",
    ))

    api_safe = isinstance(api_status, dict) and isinstance(api_contract, dict) and api_status.get("api_mode") == "READ_ONLY"
    projects.append(project(
        name="ECHO API",
        status="PARTIAL" if api_safe else "UNKNOWN",
        state="READ_ONLY_READY" if api_safe else "UNKNOWN",
        paths=[api_status_path, api_contract_path],
        evidence_summary="Read-only API status and contract are present." if api_safe else "API status/contract evidence is missing or incomplete.",
        missing_evidence=[] if api_safe else ["echo_api_status.json and echo_api_contract.json"],
        confidence="HIGH" if api_safe else "LOW",
        next_action="Keep API read-only until runtime proof requirements are met.",
    ))

    scanner_status = nested_get(scanner, ("status", "scanner_status", "verdict"), None)
    projects.append(project(
        name="Scanner",
        status="PARTIAL" if scanner_path.exists() else "UNKNOWN",
        state="UNKNOWN",
        paths=[scanner_path],
        evidence_summary=f"Scanner status file value: {scanner_status or 'UNKNOWN'}.",
        missing_evidence=[] if scanner_status else ["explicit scanner health/status verdict"],
        confidence="MEDIUM" if scanner_path.exists() else "LOW",
        next_action="Read scanner status file before claiming scanner health.",
    ))

    master_status = nested_get(master, ("status", "master_brain_status", "verdict"), None)
    projects.append(project(
        name="Master Brain",
        status="PARTIAL" if master_path.exists() else "UNKNOWN",
        state="UNKNOWN",
        paths=[master_path],
        evidence_summary=f"Master Brain status file value: {master_status or 'UNKNOWN'}.",
        missing_evidence=[] if master_status else ["explicit Master Brain health/status verdict"],
        confidence="MEDIUM" if master_path.exists() else "LOW",
        next_action="Read Master Brain status evidence before claiming behavior or connectivity.",
    ))

    learning_verdict = nested_get(learning, ("verdict", "status"), None)
    projects.append(project(
        name="Learning",
        status="PARTIAL" if learning_path.exists() else "UNKNOWN",
        state="FUTURE_READY" if learning_verdict == "LEARNING_EVENT_ID_ADOPTION_READY" else "UNKNOWN",
        paths=[learning_path],
        evidence_summary=f"Learning lineage adoption evidence: {learning_verdict or 'UNKNOWN'}.",
        missing_evidence=[] if learning_verdict else ["learning_event_id_adoption_report.json"],
        confidence="HIGH" if learning_verdict else "LOW",
        next_action="Wait for fresh learning records to prove runtime linkage.",
    ))

    evolution_verdict = nested_get(evolution, ("verdict", "status"), None)
    projects.append(project(
        name="Evolution",
        status="PARTIAL" if evolution_path.exists() else "UNKNOWN",
        state="FUTURE_READY" if evolution_verdict == "EVOLUTION_EVENT_ID_ADOPTION_READY" else "UNKNOWN",
        paths=[evolution_path],
        evidence_summary=f"Evolution lineage adoption evidence: {evolution_verdict or 'UNKNOWN'}.",
        missing_evidence=[] if evolution_verdict else ["evolution_event_id_adoption_report.json"],
        confidence="HIGH" if evolution_verdict else "LOW",
        next_action="Wait for fresh evolution records to prove runtime linkage.",
    ))

    runtime_present = existing(runtime_paths)
    projects.append(project(
        name="Runtime Workers",
        status="PARTIAL" if runtime_present else "UNKNOWN",
        state="UNKNOWN",
        paths=runtime_paths,
        evidence_summary=f"Runtime worker/status files present: {len(runtime_present)}.",
        missing_evidence=[] if runtime_present else ["runtime worker/status files"],
        confidence="MEDIUM" if runtime_present else "LOW",
        next_action="Use worker/status files before claiming TITAN is running.",
    ))

    count = alerts_count(alerts)
    projects.append(project(
        name="Alerts",
        status="PARTIAL" if alerts_path.exists() else "UNKNOWN",
        state="READ_ONLY_READY" if alerts_path.exists() else "UNKNOWN",
        paths=[alerts_path],
        evidence_summary=f"Alert queue count from file: {count}." if alerts_path.exists() else "Alert queue evidence missing.",
        missing_evidence=[] if alerts_path.exists() else ["alert_queue.json"],
        confidence="HIGH" if alerts_path.exists() else "LOW",
        next_action="Review alert queue evidence; do not infer alert health from memory.",
    ))

    mission_present = existing([mission_path, approval_path])
    projects.append(project(
        name="Mission Planner",
        status="PARTIAL" if mission_present else "UNKNOWN",
        state="READ_ONLY_READY" if mission_present else "UNKNOWN",
        paths=[mission_path, approval_path],
        evidence_summary=f"Mission/approval evidence files present: {len(mission_present)}.",
        missing_evidence=[] if mission_present else ["mission_plan.json or approval_queue.json"],
        confidence="MEDIUM" if mission_present else "LOW",
        next_action="Use mission and approval queues as evidence for active focus.",
    ))

    still_unknown = [item["name"] for item in projects if item["status"] == "UNKNOWN"]
    unknown_state_systems = [item["name"] for item in projects if item["state"] == "UNKNOWN"]
    registry = {
        "schema": "titan.echo.project_state_registry.v1",
        "timestamp_ist": timestamp_ist(),
        "truth_rule": "Conversation memory is context only; status claims require current runtime/report evidence.",
        "safety": {
            "read_only_status_registry": True,
            "reads_env": False,
            "shell_execution": False,
            "codex_execution": False,
            "writes_outside_echo_runtime": False,
            "broker_risk_scanner_changes": False,
            "broker_changed": False,
            "risk_changed": False,
            "scanner_changed": False,
            "runtime_behavior_changed": False,
            "master_brain_behavior_changed": False,
            "unified_brain_behavior_changed": False,
            "deploy_or_restart": False,
        },
        "projects": projects,
        "still_unknown_systems": still_unknown,
        "unknown_state_systems": unknown_state_systems,
        "current_focus": nested_get(mission, ("current_focus", "active_mission", "title"), "UNKNOWN"),
    }
    return registry


def build_summary(registry: dict[str, Any]) -> dict[str, Any]:
    projects = registry["projects"]
    by_name = {item["name"]: item for item in projects}
    return {
        "schema": "titan.echo.project_state_registry_summary.v1",
        "timestamp_ist": registry["timestamp_ist"],
        "echo_status": by_name["ECHO"]["status"],
        "unified_brain_status": by_name["Unified Brain"]["status"],
        "outcome_tracking_status": by_name["Outcome Tracking Truth Upgrade"]["status"],
        "natural_run_status": by_name["Natural-Run Lineage Proof"]["status"],
        "api_status": by_name["ECHO API"]["status"],
        "still_unknown_systems": registry["still_unknown_systems"],
        "unknown_state_systems": registry["unknown_state_systems"],
        "current_focus": registry["current_focus"],
        "project_count": len(projects),
        "safety": registry["safety"],
    }


def generate_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    registry = build_registry()
    summary = build_summary(registry)
    write_echo_json(REGISTRY_PATH, registry)
    write_echo_json(SUMMARY_PATH, summary)
    return registry, summary


def main() -> None:
    registry, summary = generate_reports()
    print("ECHO project state registry generated.")
    print(f"echo_status={summary['echo_status']}")
    print(f"unified_brain_status={summary['unified_brain_status']}")
    print(f"outcome_tracking_status={summary['outcome_tracking_status']}")
    print(f"natural_run_status={summary['natural_run_status']}")
    print(f"api_status={summary['api_status']}")
    print("still_unknown_systems=" + ", ".join(summary["still_unknown_systems"]))
    print(f"project_count={summary['project_count']}")


if __name__ == "__main__":
    main()
