"""Focused read-only audit for remaining worker/scanner runtime FAIL evidence."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
ECHO_DIR = RUNTIME_DIR / "echo"
REPORT_PATH = ECHO_DIR / "worker_scanner_failure_focus.json"
SUMMARY_PATH = ECHO_DIR / "worker_scanner_failure_focus_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))
STALE_SECONDS = 24 * 60 * 60

INPUTS = {
    "runtime_status": RUNTIME_DIR / "runtime_status.json",
    "worker_health": RUNTIME_DIR / "worker_health.json",
    "scanner_status": RUNTIME_DIR / "scanner_status.json",
    "truth_gate_status": RUNTIME_DIR / "truth_gate_status.json",
    "filter_engine_diagnostics": RUNTIME_DIR / "filter_engine_diagnostics.json",
    "post_repair_runtime_summary": ECHO_DIR / "post_repair_runtime_summary.json",
    "scanner_breakout_integrity_repair_report": ECHO_DIR / "scanner_breakout_integrity_repair_report.json",
    "runtime_evidence_summary": ECHO_DIR / "runtime_evidence_summary.json",
}


def now_ist() -> datetime:
    return datetime.now(IST)


def timestamp_ist() -> str:
    return now_ist().isoformat()


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


def parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def file_timestamp(path: Path) -> datetime | None:
    try:
        if path.exists():
            return datetime.fromtimestamp(path.stat().st_mtime, IST)
    except OSError:
        return None
    return None


def latest_timestamp(payload: Any, path: Path) -> datetime | None:
    candidates: list[datetime] = []
    if isinstance(payload, dict):
        for key in (
            "timestamp_ist",
            "scanner_timestamp",
            "scan_finished_at_ist",
            "timestamp",
            "generated_at_ist",
        ):
            parsed = parse_time(payload.get(key))
            if parsed:
                candidates.append(parsed)
    mtime = file_timestamp(path)
    if mtime:
        candidates.append(mtime)
    return max(candidates) if candidates else None


def age_seconds_at(path: Path, payload: Any, generated_at: datetime) -> int | None:
    latest = latest_timestamp(payload, path)
    if not latest:
        return None
    return int((generated_at - latest).total_seconds())


def evidence_file_summary(docs: dict[str, Any], generated_at: datetime) -> list[dict[str, Any]]:
    summary = []
    for name, path in INPUTS.items():
        latest = latest_timestamp(docs.get(name), path)
        summary.append(
            {
                "name": name,
                "path": relative(path),
                "exists": path.exists(),
                "latest_timestamp_ist": latest.isoformat() if latest else None,
                "age_seconds": int((generated_at - latest).total_seconds()) if latest else None,
            }
        )
    return summary


def worker_status_counts(worker: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not isinstance(worker, dict):
        return counts
    for item in worker.values():
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or item.get("last_status") or "UNKNOWN").upper()
        counts[status] = counts.get(status, 0) + 1
    return counts


def degraded_worker_examples(worker: Any) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    if not isinstance(worker, dict):
        return examples
    for task, item in worker.items():
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or item.get("last_status") or "UNKNOWN").upper()
        if status not in {"DEGRADED", "ERROR", "FAIL"}:
            continue
        examples.append(
            {
                "task": task,
                "status": status,
                "last_error": item.get("last_error"),
                "last_finished_at": item.get("last_finished_at"),
                "recovery_action": item.get("recovery_action"),
            }
        )
    return examples[:10]


def classify_scanner(docs: dict[str, Any], generated_at: datetime) -> str:
    scanner = docs["scanner_status"] if isinstance(docs.get("scanner_status"), dict) else {}
    post = docs["post_repair_runtime_summary"] if isinstance(docs.get("post_repair_runtime_summary"), dict) else {}
    repair = (
        docs["scanner_breakout_integrity_repair_report"]
        if isinstance(docs.get("scanner_breakout_integrity_repair_report"), dict)
        else {}
    )
    age = age_seconds_at(INPUTS["scanner_status"], scanner, generated_at)
    waiting = "Scanner" in (post.get("waiting_for_runtime_regeneration") or [])
    legacy_rows = int(repair.get("current_legacy_rows_without_new_gate_fields_count") or 0)
    repair_ready = repair.get("status") == "PASS" and repair.get("current_canonical_violations") == []
    if waiting and repair_ready and legacy_rows:
        return "LEGACY_WAITING_REGENERATION"
    if age is not None and age > STALE_SECONDS:
        return "STALE"
    if str(scanner.get("status") or "").upper() in {"FAIL", "ERROR", "BROKEN", "BREAKOUT_PIPELINE_INTEGRITY_ERROR"}:
        return "ACTIVE_FAILURE"
    if scanner:
        return "UNKNOWN"
    return "UNKNOWN"


def classify_worker(docs: dict[str, Any], generated_at: datetime) -> str:
    worker = docs["worker_health"]
    if not isinstance(worker, dict) or not worker:
        return "MISSING_EVIDENCE"
    age = age_seconds_at(INPUTS["worker_health"], worker, generated_at)
    counts = worker_status_counts(worker)
    if age is not None and age > STALE_SECONDS:
        return "STALE"
    if any(status in counts for status in ("DEGRADED", "ERROR", "FAIL")):
        return "DEGRADED_WORKERS"
    runtime_summary = docs["runtime_evidence_summary"] if isinstance(docs.get("runtime_evidence_summary"), dict) else {}
    if runtime_summary.get("worker_runtime_status") == "FAIL":
        return "ACTIVE_FAILURE"
    return "UNKNOWN"


def classify_truth_gate(docs: dict[str, Any]) -> str:
    truth = docs["truth_gate_status"] if isinstance(docs.get("truth_gate_status"), dict) else {}
    text = json.dumps(truth, sort_keys=True).upper()
    scanner_path = truth.get("scanner_path_status") if isinstance(truth.get("scanner_path_status"), dict) else {}
    if scanner_path.get("status") == "FAIL":
        return "SCANNER_DEPENDENT"
    if "SUPABASE" in text:
        return "SUPABASE"
    if "TRADE_NOT_OPEN" in text or "OUTCOME" in text or "ACTIVE_TRADES" in text:
        return "OUTCOME_SAMPLE"
    if "MARKET_CLOSED" in text or "OHLC_NOT_PROVIDED" in text:
        return "EXTERNAL_CONFIG"
    return "UNKNOWN"


def classify_filter_engine(docs: dict[str, Any], generated_at: datetime) -> str:
    diagnostics = (
        docs["filter_engine_diagnostics"]
        if isinstance(docs.get("filter_engine_diagnostics"), dict)
        else {}
    )
    scanner = docs["scanner_status"] if isinstance(docs.get("scanner_status"), dict) else {}
    age = age_seconds_at(INPUTS["filter_engine_diagnostics"], diagnostics, generated_at)
    if diagnostics.get("exceptions"):
        return "TRUE_FILTER_FAILURE"
    if diagnostics.get("scanner_cycle_id") and diagnostics.get("scanner_cycle_id") == scanner.get("scanner_cycle_id"):
        if age is not None and age > STALE_SECONDS:
            return "LEGACY_DIAGNOSTIC"
        return "SCANNER_DEPENDENT"
    if age is not None and age > STALE_SECONDS:
        return "LEGACY_DIAGNOSTIC"
    return "UNKNOWN"


def exact_blocker(scanner_type: str, worker_type: str, truth_relation: str, filter_relation: str, docs: dict[str, Any]) -> str:
    worker = docs["worker_health"] if isinstance(docs.get("worker_health"), dict) else {}
    counts = worker_status_counts(worker)
    degraded_count = sum(counts.get(status, 0) for status in ("DEGRADED", "ERROR", "FAIL"))
    if scanner_type == "LEGACY_WAITING_REGENERATION" and worker_type == "STALE":
        return (
            "Runtime FAIL is blocked by stale worker_health evidence plus scanner artifacts that still reflect "
            "pre-repair legacy final_validated_setups rows awaiting a natural scanner/runtime regeneration cycle."
        )
    if worker_type == "DEGRADED_WORKERS":
        return f"Worker health has {degraded_count} degraded/error/fail task statuses."
    if scanner_type == "ACTIVE_FAILURE":
        scanner = docs["scanner_status"] if isinstance(docs.get("scanner_status"), dict) else {}
        return f"Scanner status is active failure: {scanner.get('status')}"
    if truth_relation == "OUTCOME_SAMPLE":
        return "Truth Gate is failing on an outcome/trade sample condition rather than scanner path evidence."
    if filter_relation == "TRUE_FILTER_FAILURE":
        return "Filter diagnostics contain exceptions indicating a true filter engine failure."
    return "Remaining blocker is unresolved or stale runtime evidence, not enough to justify code repair."


def recommended_action(scanner_type: str, worker_type: str, truth_relation: str, filter_relation: str) -> str:
    if scanner_type == "LEGACY_WAITING_REGENERATION" and worker_type == "STALE":
        return (
            "Do not repair scanner or workers yet. Wait for an approved natural runtime/scanner regeneration cycle, "
            "then rerun runtime_status.py, echo_runtime_evidence.py, and this focus audit."
        )
    if worker_type == "DEGRADED_WORKERS":
        return "Open a separate read-only worker-health audit focused on degraded task errors; do not change scheduling."
    if scanner_type == "ACTIVE_FAILURE":
        return "Open a scanner evidence audit only; do not modify scanner logic until fresh post-repair evidence confirms the failure."
    if truth_relation == "OUTCOME_SAMPLE":
        return "Inspect the Truth Gate sample inputs and active trade evidence; do not alter scanner or broker/risk behavior."
    if filter_relation == "TRUE_FILTER_FAILURE":
        return "Inspect filter diagnostics exceptions in a separate read-only mission before any repair."
    return "Regenerate runtime evidence in an approved non-restart workflow and rerun this focus audit."


def build_report() -> tuple[dict[str, Any], dict[str, Any]]:
    generated_at = now_ist()
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    scanner_type = classify_scanner(docs, generated_at)
    worker_type = classify_worker(docs, generated_at)
    truth_relation = classify_truth_gate(docs)
    filter_relation = classify_filter_engine(docs, generated_at)
    blocker = exact_blocker(scanner_type, worker_type, truth_relation, filter_relation, docs)
    action = recommended_action(scanner_type, worker_type, truth_relation, filter_relation)
    worker = docs["worker_health"] if isinstance(docs.get("worker_health"), dict) else {}
    scanner = docs["scanner_status"] if isinstance(docs.get("scanner_status"), dict) else {}
    truth = docs["truth_gate_status"] if isinstance(docs.get("truth_gate_status"), dict) else {}
    filter_diag = docs["filter_engine_diagnostics"] if isinstance(docs.get("filter_engine_diagnostics"), dict) else {}
    report = {
        "schema": "titan.echo.worker_scanner_failure_focus.v1",
        "timestamp_ist": generated_at.isoformat(),
        "scanner_fail_type": scanner_type,
        "worker_fail_type": worker_type,
        "truth_gate_relation": truth_relation,
        "filter_engine_relation": filter_relation,
        "exact_remaining_blocker": blocker,
        "recommended_next_action": action,
        "evidence_files": evidence_file_summary(docs, generated_at),
        "scanner_evidence": {
            "status": scanner.get("status"),
            "scanner_cycle_id": scanner.get("scanner_cycle_id"),
            "timestamp_ist": scanner.get("timestamp_ist") or scanner.get("scanner_timestamp"),
            "breakout_pipeline_integrity": scanner.get("breakout_pipeline_integrity"),
        },
        "worker_evidence": {
            "status_counts": worker_status_counts(worker),
            "degraded_examples": degraded_worker_examples(worker),
        },
        "truth_gate_evidence": {
            "overall_status": truth.get("overall_status"),
            "blocked_reason": truth.get("blocked_reason"),
            "scanner_path_status": truth.get("scanner_path_status"),
            "outcome_validation_status": truth.get("outcome_validation_status"),
        },
        "filter_engine_evidence": {
            "timestamp_ist": filter_diag.get("timestamp_ist"),
            "scanner_cycle_id": filter_diag.get("scanner_cycle_id"),
            "exceptions": filter_diag.get("exceptions") or [],
            "engine_counts": filter_diag.get("engine_counts"),
            "final_setup_count": filter_diag.get("final_setup_count"),
        },
        "safety": {
            "read_only_investigation": True,
            "restart_executed": False,
            "deploy_executed": False,
            "push_executed": False,
            "scanner_modified": False,
            "workers_modified": False,
            "broker_risk_modified": False,
            "master_brain_modified": False,
            "unified_brain_modified": False,
            "runtime_scheduling_modified": False,
            "writes_only_echo_reports": True,
        },
    }
    summary = {
        "schema": "titan.echo.worker_scanner_failure_focus_summary.v1",
        "timestamp_ist": report["timestamp_ist"],
        "scanner_fail_type": scanner_type,
        "worker_fail_type": worker_type,
        "truth_gate_relation": truth_relation,
        "filter_engine_relation": filter_relation,
        "exact_remaining_blocker": blocker,
        "recommended_next_action": action,
        "safety": report["safety"],
    }
    return report, summary


def generate_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    report, summary = build_report()
    ECHO_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return report, summary


def main() -> None:
    _, summary = generate_reports()
    print("ECHO worker/scanner failure focus generated.")
    print(f"scanner_fail_type={summary['scanner_fail_type']}")
    print(f"worker_fail_type={summary['worker_fail_type']}")
    print(f"truth_gate_relation={summary['truth_gate_relation']}")
    print(f"filter_engine_relation={summary['filter_engine_relation']}")
    print(f"exact_remaining_blocker={summary['exact_remaining_blocker']}")
    print(f"recommended_next_action={summary['recommended_next_action']}")


if __name__ == "__main__":
    main()
