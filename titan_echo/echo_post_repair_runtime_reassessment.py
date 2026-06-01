"""Read-only post-repair runtime reassessment.

This report checks whether current runtime evidence changed after the scanner
breakout integrity repair. It does not execute scanner/runtime code.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
ECHO_DIR = RUNTIME_DIR / "echo"
REPORT_PATH = ECHO_DIR / "post_repair_runtime_reassessment.json"
SUMMARY_PATH = ECHO_DIR / "post_repair_runtime_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))

FILES = {
    "repair": ECHO_DIR / "scanner_breakout_integrity_repair_report.json",
    "runtime_evidence": ECHO_DIR / "runtime_evidence_summary.json",
    "failure_summary": ECHO_DIR / "runtime_failure_summary.json",
    "scanner": RUNTIME_DIR / "scanner_status.json",
    "truth_gate": RUNTIME_DIR / "truth_gate_status.json",
    "filter": RUNTIME_DIR / "filter_engine_diagnostics.json",
    "worker": RUNTIME_DIR / "worker_health.json",
    "runtime": RUNTIME_DIR / "runtime_status.json",
    "master": RUNTIME_DIR / "master_brain_status.json",
    "unified": RUNTIME_DIR / "unified_brain_status.json",
    "final_setups": RUNTIME_DIR / "final_validated_setups.json",
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
        raise ValueError("post-repair reassessment writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def nested_get(data: Any, key: str, default: Any = None) -> Any:
    current = data
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def final_setup_legacy_count(final_setups: Any) -> int:
    rows = final_setups.get("setups") if isinstance(final_setups, dict) else []
    if not isinstance(rows, list):
        return 0
    required = {
        "raw_breakout_ready",
        "qualified_breakout_ready",
        "breakout_ready",
        "momentum_passed",
        "structure_passed",
        "trend_passed",
        "breakout_reason",
        "gate_source",
    }
    return sum(1 for item in rows if isinstance(item, dict) and not required.issubset(item))


def evidence_file_entries(keys: list[str]) -> list[dict[str, Any]]:
    return [{"path": rel(FILES[key]), "exists": FILES[key].exists()} for key in keys]


def build_subsystems() -> tuple[dict[str, Any], dict[str, Any]]:
    repair = read_json(FILES["repair"]) or {}
    runtime_evidence = read_json(FILES["runtime_evidence"]) or {}
    failure_summary = read_json(FILES["failure_summary"]) or {}
    scanner = read_json(FILES["scanner"]) or {}
    truth_gate = read_json(FILES["truth_gate"]) or {}
    filter_diag = read_json(FILES["filter"]) or {}
    worker = read_json(FILES["worker"]) or {}
    master = read_json(FILES["master"]) or {}
    unified = read_json(FILES["unified"]) or {}
    final_setups = read_json(FILES["final_setups"]) or {}

    repair_pass = repair.get("status") == "PASS"
    legacy_rows = final_setup_legacy_count(final_setups)
    scanner_still_old_error = scanner.get("status") == "BREAKOUT_PIPELINE_INTEGRITY_ERROR"
    scanner_current_status = runtime_evidence.get("scanner_runtime_status") or scanner.get("status") or "UNKNOWN"

    subsystems: dict[str, Any] = {}
    subsystems["Scanner"] = {
        "before_status": "FAIL",
        "current_status": scanner_current_status,
        "repair_related": True,
        "repair_impact": (
            "WAITING_FOR_RUNTIME_REGENERATION"
            if repair_pass and scanner_still_old_error and legacy_rows > 0
            else "REPAIRED"
            if repair_pass and not scanner_still_old_error
            else "NOT_REPAIRED"
        ),
        "evidence": {
            "repair_report_status": repair.get("status"),
            "repair_verdict": repair.get("verdict"),
            "pnb_bpcl_pattern_blocked": repair.get("pnb_bpcl_pattern_blocked"),
            "scanner_status": scanner.get("status"),
            "scanner_integrity_errors": nested_get(scanner, "breakout_pipeline_integrity.integrity_errors", []),
            "legacy_final_setup_rows_without_new_gate_fields": legacy_rows,
        },
        "missing_evidence": [] if FILES["scanner"].exists() and FILES["repair"].exists() else ["scanner_status.json or repair report"],
        "next_required_action": "Let scanner run naturally to regenerate final_validated_setups with repaired gate fields; do not rewrite legacy rows.",
    }

    truth_reason = truth_gate.get("blocked_reason") or truth_gate.get("recommended_next_action")
    subsystems["Truth Gate"] = {
        "before_status": "FAIL",
        "current_status": truth_gate.get("overall_status") or "UNKNOWN",
        "repair_related": False,
        "repair_impact": "NOT_RELATED",
        "evidence": {
            "overall_status": truth_gate.get("overall_status"),
            "blocked_reason": truth_reason,
            "trade_validation_status": truth_gate.get("trade_validation_status"),
            "market_data_status": truth_gate.get("market_data_status"),
        },
        "missing_evidence": [] if FILES["truth_gate"].exists() else ["truth_gate_status.json"],
        "next_required_action": "Investigate Truth Gate reasons separately; current evidence points to market/trade validation, not scanner repair.",
    }

    filter_status = "FAIL" if "FAIL" in json.dumps(filter_diag).upper() else "UNKNOWN"
    subsystems["Filter Engine"] = {
        "before_status": "FAIL",
        "current_status": filter_status,
        "repair_related": False,
        "repair_impact": "NOT_RELATED",
        "evidence": {
            "engine_counts": filter_diag.get("engine_counts"),
            "rejection_reasons": filter_diag.get("rejection_reasons"),
            "timestamp_ist": filter_diag.get("timestamp_ist"),
        },
        "missing_evidence": [] if FILES["filter"].exists() else ["filter_engine_diagnostics.json"],
        "next_required_action": "Inspect filter diagnostics separately; scanner contract repair does not change filter formulas.",
    }

    worker_text = json.dumps(worker).upper()
    worker_status = "FAIL" if any(token in worker_text for token in ("FAIL", "DEGRADED", "ERROR")) else runtime_evidence.get("worker_runtime_status", "UNKNOWN")
    subsystems["Workers"] = {
        "before_status": "FAIL",
        "current_status": worker_status,
        "repair_related": False,
        "repair_impact": "NOT_RELATED",
        "evidence": {
            "runtime_evidence_worker_status": runtime_evidence.get("worker_runtime_status"),
            "worker_health_file_exists": FILES["worker"].exists(),
            "runtime_status_file_exists": FILES["runtime"].exists(),
        },
        "missing_evidence": [rel(FILES["runtime"])] if not FILES["runtime"].exists() else [],
        "next_required_action": "Investigate worker health/runtime owner/lock evidence separately; do not blame scanner repair.",
    }

    subsystems["Master Brain"] = {
        "before_status": "STALE",
        "current_status": runtime_evidence.get("master_brain_runtime_status") or "STALE",
        "repair_related": False,
        "repair_impact": "NOT_RELATED",
        "evidence": {
            "runtime_evidence_master_status": runtime_evidence.get("master_brain_runtime_status"),
            "master_brain_status": master.get("status"),
            "timestamp_ist": master.get("timestamp_ist") or master.get("timestamp"),
        },
        "missing_evidence": [] if FILES["master"].exists() else ["master_brain_status.json"],
        "next_required_action": "Observe or refresh Master Brain status naturally; stale evidence is not scanner-repair related.",
    }

    subsystems["Unified Brain"] = {
        "before_status": "STALE",
        "current_status": runtime_evidence.get("unified_brain_runtime_status") or "STALE",
        "repair_related": False,
        "repair_impact": "NOT_RELATED",
        "evidence": {
            "runtime_evidence_unified_status": runtime_evidence.get("unified_brain_runtime_status"),
            "unified_brain_status_file_exists": FILES["unified"].exists(),
            "status": unified.get("status"),
            "timestamp_ist": unified.get("timestamp_ist") or unified.get("timestamp"),
        },
        "missing_evidence": [rel(FILES["unified"])] if not FILES["unified"].exists() else [],
        "next_required_action": "Observe or refresh Unified Brain status naturally; stale/missing evidence is not scanner-repair related.",
    }
    context = {
        "repair_pass": repair_pass,
        "legacy_rows": legacy_rows,
        "scanner_still_old_error": scanner_still_old_error,
        "failure_summary_final_verdict": failure_summary.get("final_verdict"),
    }
    return subsystems, context


def build_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    subsystems, context = build_subsystems()
    remaining_failures = [
        name for name, item in subsystems.items()
        if item["current_status"] in ("FAIL", "BREAKOUT_PIPELINE_INTEGRITY_ERROR")
    ]
    unrelated_failures = [
        name for name in remaining_failures
        if not subsystems[name]["repair_related"]
    ]
    waiting = [
        name for name, item in subsystems.items()
        if item["repair_impact"] == "WAITING_FOR_RUNTIME_REGENERATION"
    ]
    if context["repair_pass"] and waiting:
        overall = "WAITING_FOR_RUNTIME_REGENERATION"
        final_verdict = "WAITING_FOR_RUNTIME_DATA"
    elif context["repair_pass"] and unrelated_failures:
        overall = "PARTIALLY_REPAIRED"
        final_verdict = "PARTIALLY_REPAIRED"
    elif context["repair_pass"] and not remaining_failures:
        overall = "REPAIRED"
        final_verdict = "REPAIRED"
    else:
        overall = "NOT_REPAIRED"
        final_verdict = "STILL_FAILING"

    report = {
        "schema": "titan.echo.post_repair_runtime_reassessment.v1",
        "timestamp_ist": timestamp_ist(),
        "audit_mode": "READ_ONLY_REASSESSMENT",
        "input_files": evidence_file_entries(list(FILES)),
        "subsystems": subsystems,
        "overall_repair_impact": overall,
        "scanner_repair_status": subsystems["Scanner"]["repair_impact"],
        "remaining_failures": remaining_failures,
        "unrelated_failures": unrelated_failures,
        "waiting_for_runtime_regeneration": waiting,
        "recommended_next_action": (
            "Wait for a natural scanner/runtime cycle to regenerate scanner_status and final_validated_setups; "
            "then rerun runtime evidence and this reassessment. Do not rewrite legacy rows."
        )
        if waiting
        else "Investigate unrelated remaining failures separately.",
        "final_verdict": final_verdict,
        "safety": {
            "read_only_reassessment": True,
            "scanner_runtime_executed": False,
            "scanner_modified": False,
            "workers_modified": False,
            "master_brain_modified": False,
            "unified_brain_modified": False,
            "broker_risk_modified": False,
            "restart_executed": False,
            "deploy_executed": False,
            "push_executed": False,
            "shell_execution": False,
            "writes_outside_echo_runtime": False,
        },
    }
    summary = {
        "schema": "titan.echo.post_repair_runtime_summary.v1",
        "timestamp_ist": report["timestamp_ist"],
        "overall_repair_impact": overall,
        "scanner_repair_status": report["scanner_repair_status"],
        "remaining_failures": remaining_failures,
        "unrelated_failures": unrelated_failures,
        "waiting_for_runtime_regeneration": waiting,
        "recommended_next_action": report["recommended_next_action"],
        "final_verdict": final_verdict,
        "safety": report["safety"],
    }
    return report, summary


def generate_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    report, summary = build_reports()
    write_echo_json(REPORT_PATH, report)
    write_echo_json(SUMMARY_PATH, summary)
    return report, summary


def main() -> None:
    _, summary = generate_reports()
    print("ECHO post-repair runtime reassessment complete.")
    print(f"overall_repair_impact={summary['overall_repair_impact']}")
    print(f"scanner_repair_status={summary['scanner_repair_status']}")
    print("remaining_failures=" + ", ".join(summary["remaining_failures"]))
    print("unrelated_failures=" + ", ".join(summary["unrelated_failures"]))
    print("waiting_for_runtime_regeneration=" + ", ".join(summary["waiting_for_runtime_regeneration"]))
    print(f"recommended_next_action={summary['recommended_next_action']}")
    print(f"final_verdict={summary['final_verdict']}")


if __name__ == "__main__":
    main()
