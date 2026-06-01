"""Read-only investigation of runtime failures surfaced by ECHO evidence.

This script only reads runtime/status evidence and writes Echo investigation
reports under data/runtime/echo.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
ECHO_DIR = RUNTIME_DIR / "echo"
REPORT_PATH = ECHO_DIR / "runtime_failure_investigation.json"
SUMMARY_PATH = ECHO_DIR / "runtime_failure_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))

INVESTIGATION_TARGETS = {
    "Scanner": [
        RUNTIME_DIR / "scanner_status.json",
        RUNTIME_DIR / "filter_engine_diagnostics.json",
        RUNTIME_DIR / "truth_gate_status.json",
        RUNTIME_DIR / "runtime_selector_status.json",
    ],
    "Workers": [
        RUNTIME_DIR / "runtime_status.json",
        RUNTIME_DIR / "worker_health.json",
        RUNTIME_DIR / "titan_runtime_status.json",
        RUNTIME_DIR / "daemon_owner.json",
        RUNTIME_DIR / "runtime_owner.json",
    ],
    "Master Brain": [
        RUNTIME_DIR / "master_brain_status.json",
        RUNTIME_DIR / "brain_state.json",
    ],
    "Unified Brain": [
        RUNTIME_DIR / "unified_brain_status.json",
        RUNTIME_DIR / "unified_brain" / "unified_brain_final_status.json",
        RUNTIME_DIR / "unified_brain" / "unified_brain_final_summary.json",
    ],
    "Truth Gate": [
        RUNTIME_DIR / "truth_gate_status.json",
    ],
    "Selector": [
        RUNTIME_DIR / "runtime_selector_status.json",
    ],
    "Filter Engine": [
        RUNTIME_DIR / "filter_engine_diagnostics.json",
    ],
}

SUPPORTING_FILES = [
    ECHO_DIR / "runtime_evidence_report.json",
    ECHO_DIR / "runtime_evidence_summary.json",
    ECHO_DIR / "project_state_registry.json",
]

TIMESTAMP_KEYS = (
    "timestamp_ist",
    "timestamp",
    "updated_at",
    "last_updated",
    "last_update",
    "generated_at",
    "created_at",
    "heartbeat_at",
    "last_heartbeat",
    "last_seen",
    "last_finished_at",
    "last_started_at",
)
STATUS_KEYS = (
    "status",
    "verdict",
    "health",
    "state",
    "runtime_status",
    "scanner_status",
    "master_brain_status",
    "unified_brain_status",
    "worker_status",
    "last_status",
    "pipeline_status",
)
FAIL_TOKENS = ("FAIL", "FAILED", "ERROR", "BROKEN", "BLOCKED", "CRITICAL", "INTEGRITY_ERROR")
DEGRADED_TOKENS = ("DEGRADED", "WARNING", "CAUTION", "PARTIAL", "MANUAL_RECONCILIATION_REQUIRED")
STALE_SECONDS = 900


def now_ist() -> datetime:
    return datetime.now(IST)


def timestamp_ist() -> str:
    return now_ist().isoformat()


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
        raise ValueError("runtime failure investigation writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def iter_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        for child in value.values():
            found.extend(iter_dicts(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(iter_dicts(child))
    return found


def parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def evidence_timestamp(item: dict[str, Any], path: Path) -> datetime | None:
    for key in TIMESTAMP_KEYS:
        parsed = parse_time(item.get(key))
        if parsed:
            return parsed
    if path.exists():
        return datetime.fromtimestamp(path.stat().st_mtime, IST)
    return None


def collect_signals(paths: list[Path]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for path in paths:
        payload = read_json(path)
        if payload is None:
            continue
        for item in iter_dicts(payload):
            seen_any = False
            for key in STATUS_KEYS:
                value = item.get(key)
                if value in (None, ""):
                    continue
                text = str(value)
                upper = text.upper()
                if any(token in upper for token in FAIL_TOKENS):
                    signal_type = "failure"
                elif any(token in upper for token in DEGRADED_TOKENS):
                    signal_type = "degraded"
                else:
                    signal_type = "status"
                signals.append({
                    "file": rel(path),
                    "field": key,
                    "value": text[:500],
                    "signal_type": signal_type,
                    "timestamp": (evidence_timestamp(item, path) or datetime.fromtimestamp(path.stat().st_mtime, IST)).isoformat(),
                })
                seen_any = True
            if not seen_any:
                continue
    signals.sort(key=lambda item: item.get("timestamp") or "")
    return signals


def evidence_files(paths: list[Path]) -> list[dict[str, Any]]:
    return [{"path": rel(path), "exists": path.exists()} for path in paths]


def latest_file_timestamp(paths: list[Path]) -> datetime | None:
    times = [datetime.fromtimestamp(path.stat().st_mtime, IST) for path in paths if path.exists()]
    return max(times) if times else None


def runtime_evidence_for(name: str) -> dict[str, Any]:
    report = read_json(ECHO_DIR / "runtime_evidence_report.json")
    if isinstance(report, dict):
        subsystems = report.get("subsystems")
        if isinstance(subsystems, dict):
            if name in subsystems and isinstance(subsystems[name], dict):
                return subsystems[name]
            if name == "Workers" and isinstance(subsystems.get("Runtime Workers"), dict):
                return subsystems["Runtime Workers"]
    return {}


def classify_root_cause(name: str, status: str, signals: list[dict[str, Any]], paths: list[Path]) -> tuple[str, str, str, str]:
    values = " ".join(signal.get("value", "").upper() for signal in signals)
    missing = [path for path in paths if not path.exists()]
    if "BREAKOUT_PIPELINE_INTEGRITY_ERROR" in values:
        return (
            "Scanner breakout pipeline integrity error is recorded in runtime evidence.",
            "integrity issue",
            "HIGH",
            "HIGH",
        )
    if name == "Workers" and any(token in values for token in ("DEGRADED", "ERROR_COUNT", "WAITING_FOR_MODE", "FAIL")):
        return (
            "Worker/runtime evidence contains degraded or failure signals; process liveness is not independently proven by this read-only audit.",
            "real runtime failure",
            "HIGH",
            "HIGH",
        )
    if status == "STALE":
        return (
            "Latest evidence is stale; current runtime state is not proven from fresh files.",
            "stale evidence",
            "MEDIUM",
            "MEDIUM",
        )
    if status == "FAIL":
        return (
            "Runtime/status evidence contains explicit failure tokens.",
            "real runtime failure",
            "HIGH",
            "HIGH",
        )
    if missing and not signals:
        return (
            "Configured evidence files are missing, so runtime state is not proven.",
            "missing evidence",
            "LOW",
            "MEDIUM",
        )
    if any(token in values for token in ("MODE", "OWNER", "LOCK")):
        return (
            "Evidence points to ownership/mode/lock state that needs configuration review.",
            "configuration issue",
            "MEDIUM",
            "MEDIUM",
        )
    return (
        "No explicit current failure root cause is proven by available files.",
        "historical artifact",
        "LOW",
        "LOW",
    )


def investigate_subsystem(name: str, paths: list[Path]) -> dict[str, Any]:
    if name == "Workers":
        locks_dir = RUNTIME_DIR / "locks"
        runtime_extra = list(RUNTIME_DIR.glob("*.pid")) + list(RUNTIME_DIR.glob("*.lock"))
        if locks_dir.exists():
            runtime_extra.extend(path for path in locks_dir.iterdir() if path.is_file())
        paths = paths + runtime_extra
    runtime = runtime_evidence_for(name)
    signals = collect_signals(paths)
    failure_signals = [signal for signal in signals if signal["signal_type"] in ("failure", "degraded")]
    status = str(runtime.get("status") or "UNKNOWN")
    if status == "UNKNOWN" and failure_signals:
        status = "FAIL" if any(signal["signal_type"] == "failure" for signal in failure_signals) else "DEGRADED"
    root_cause, cause_type, confidence, severity = classify_root_cause(name, status, failure_signals or signals, paths)
    latest_ts = runtime.get("latest_timestamp")
    if not latest_ts:
        latest = latest_file_timestamp(paths)
        latest_ts = latest.isoformat() if latest else None
    return {
        "subsystem": name,
        "status": status,
        "root_cause": root_cause,
        "cause_type": cause_type,
        "evidence_files": evidence_files(paths),
        "first_failure_signal": failure_signals[0] if failure_signals else None,
        "latest_failure_signal": failure_signals[-1] if failure_signals else None,
        "latest_evidence_timestamp": latest_ts,
        "confidence": confidence,
        "severity": severity,
        "reason": runtime.get("reason") or root_cause,
    }


def fix_complexity(cause_type: str, subsystem: str) -> str:
    if cause_type in ("stale evidence", "missing evidence", "historical artifact"):
        return "LOW"
    if subsystem in ("Scanner", "Workers", "Filter Engine", "Truth Gate"):
        return "MEDIUM"
    return "LOW"


def recommended_action(item: dict[str, Any]) -> str:
    subsystem = item["subsystem"]
    cause_type = item["cause_type"]
    if subsystem == "Scanner" and cause_type == "integrity issue":
        return "Inspect scanner breakout pipeline integrity inputs and filter/truth-gate dependencies before any repair."
    if subsystem == "Workers":
        return "Inspect worker health/runtime owner/lock evidence and scheduler ownership before restarting or repairing."
    if cause_type == "stale evidence":
        return f"Refresh or observe {subsystem} naturally and verify a fresh timestamped status file."
    if cause_type == "missing evidence":
        return f"Identify the expected {subsystem} status writer; do not infer runtime state without its file."
    return f"Review {subsystem} evidence files and confirm whether the signal is current or historical."


def priority_score(item: dict[str, Any]) -> tuple[int, int]:
    severity_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    status_rank = {"FAIL": 0, "DEGRADED": 1, "STALE": 2, "UNKNOWN": 3, "NOT_PROVEN": 3}
    return (severity_rank.get(item["severity"], 3), status_rank.get(item["status"], 4))


def build_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    investigations = {
        name: investigate_subsystem(name, paths)
        for name, paths in INVESTIGATION_TARGETS.items()
    }
    priority_items = sorted(investigations.values(), key=priority_score)
    fix_priority = [
        {
            "priority_rank": index + 1,
            "subsystem": item["subsystem"],
            "severity": item["severity"],
            "estimated_fix_complexity": fix_complexity(item["cause_type"], item["subsystem"]),
            "recommended_next_action": recommended_action(item),
        }
        for index, item in enumerate(priority_items)
    ]
    statuses = [item["status"] for item in investigations.values()]
    if any(status == "FAIL" for status in statuses):
        final_verdict = "FAILING"
    elif any(status in ("DEGRADED", "STALE") for status in statuses):
        final_verdict = "DEGRADED"
    elif all(status in ("HEALTHY", "RUNNING") for status in statuses):
        final_verdict = "HEALTHY"
    else:
        final_verdict = "NOT_PROVEN"
    report = {
        "schema": "titan.echo.runtime_failure_investigation.v1",
        "timestamp_ist": timestamp_ist(),
        "audit_mode": "READ_ONLY_INVESTIGATION",
        "supporting_files": evidence_files(SUPPORTING_FILES),
        "safety": {
            "read_only_investigation": True,
            "repair_actions_executed": False,
            "restart_executed": False,
            "deploy_executed": False,
            "push_executed": False,
            "reads_env": False,
            "shell_execution": False,
            "codex_execution": False,
            "writes_outside_echo_runtime": False,
        },
        "subsystems": investigations,
        "scanner_root_cause": investigations["Scanner"]["root_cause"],
        "worker_root_cause": investigations["Workers"]["root_cause"],
        "master_brain_root_cause": investigations["Master Brain"]["root_cause"],
        "unified_brain_root_cause": investigations["Unified Brain"]["root_cause"],
        "FIX_PRIORITY_ORDER": fix_priority,
        "final_verdict": final_verdict,
        "recommended_first_fix": fix_priority[0]["recommended_next_action"] if fix_priority else "NOT_PROVEN",
    }
    summary = {
        "schema": "titan.echo.runtime_failure_summary.v1",
        "timestamp_ist": report["timestamp_ist"],
        "scanner_root_cause": report["scanner_root_cause"],
        "worker_root_cause": report["worker_root_cause"],
        "master_brain_root_cause": report["master_brain_root_cause"],
        "unified_brain_root_cause": report["unified_brain_root_cause"],
        "severity_table": {
            name: {
                "status": item["status"],
                "severity": item["severity"],
                "cause_type": item["cause_type"],
                "confidence": item["confidence"],
            }
            for name, item in investigations.items()
        },
        "FIX_PRIORITY_ORDER": fix_priority,
        "final_verdict": final_verdict,
        "recommended_first_fix": report["recommended_first_fix"],
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
    print("ECHO runtime failure investigation complete.")
    print(f"scanner_root_cause={summary['scanner_root_cause']}")
    print(f"worker_root_cause={summary['worker_root_cause']}")
    print(f"master_brain_root_cause={summary['master_brain_root_cause']}")
    print(f"unified_brain_root_cause={summary['unified_brain_root_cause']}")
    print(f"final_verdict={summary['final_verdict']}")
    print(f"recommended_first_fix={summary['recommended_first_fix']}")
    print("fix_priority_order=" + ", ".join(
        f"{item['priority_rank']}:{item['subsystem']}:{item['severity']}"
        for item in summary["FIX_PRIORITY_ORDER"]
    ))


if __name__ == "__main__":
    main()
