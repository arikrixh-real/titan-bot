"""Evidence-based runtime status layer for ECHO.

This module reads runtime/status evidence files and writes only Echo runtime
evidence reports under data/runtime/echo. It does not execute commands or
inspect process tables.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
ECHO_DIR = RUNTIME_DIR / "echo"
REPORT_PATH = ECHO_DIR / "runtime_evidence_report.json"
SUMMARY_PATH = ECHO_DIR / "runtime_evidence_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))
FRESH_SECONDS = 900

SUBSYSTEMS = {
    "Scanner": [
        RUNTIME_DIR / "scanner_status.json",
    ],
    "Master Brain": [
        RUNTIME_DIR / "master_brain_status.json",
        RUNTIME_DIR / "brain_state.json",
    ],
    "Unified Brain": [
        RUNTIME_DIR / "unified_brain_status.json",
        RUNTIME_DIR / "unified_brain" / "unified_brain_final_status.json",
    ],
    "Runtime Workers": [
        RUNTIME_DIR / "runtime_status.json",
        RUNTIME_DIR / "worker_health.json",
        RUNTIME_DIR / "daemon_owner.json",
        RUNTIME_DIR / "runtime_owner.json",
        RUNTIME_DIR / "titan_runtime_status.json",
    ],
    "Truth Gate": [
        RUNTIME_DIR / "truth_gate_status.json",
    ],
    "Filter Engine": [
        RUNTIME_DIR / "filter_engine_diagnostics.json",
    ],
    "Selector": [
        RUNTIME_DIR / "runtime_selector_status.json",
    ],
    "Outcome Tracker": [
        RUNTIME_DIR / "outcome_tracker_status.json",
        ECHO_DIR / "outcome_id_adoption_report.json",
    ],
    "Learning": [
        ECHO_DIR / "learning_event_id_adoption_report.json",
        REPO_ROOT / "data" / "learning" / "reinforcement_learning_reports.jsonl",
    ],
    "Evolution": [
        ECHO_DIR / "evolution_event_id_adoption_report.json",
        REPO_ROOT / "data" / "memory" / "evolution_state.json",
        RUNTIME_DIR / "evolution_engine_status.json",
    ],
    "Alerts": [
        ECHO_DIR / "alert_queue.json",
    ],
    "ECHO API": [
        ECHO_DIR / "echo_api_status.json",
        ECHO_DIR / "echo_api_contract.json",
    ],
}

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
)
FAIL_TOKENS = ("FAIL", "FAILED", "ERROR", "BROKEN", "BLOCKED", "CRITICAL")
DEGRADED_TOKENS = ("DEGRADED", "WARNING", "PARTIAL")
RUNNING_TOKENS = ("RUNNING", "ACTIVE", "ALIVE")
HEALTHY_TOKENS = ("HEALTHY", "PASS", "OK", "READY", "COMPLETE", "OPERATIONAL")
STOPPED_TOKENS = ("STOPPED", "HALTED", "OFFLINE", "DOWN", "EXITED")


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
    except Exception:
        return None


def read_jsonl_latest(path: Path) -> Any:
    if not path.exists():
        return None
    latest: Any = None
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                latest = item
    except Exception:
        return None
    return latest


def write_echo_json(path: Path, payload: Any) -> None:
    resolved_echo = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_echo not in (resolved_path, *resolved_path.parents):
        raise ValueError("runtime evidence writes only under data/runtime/echo")
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


def latest_timestamp(payloads: list[Any], paths: list[Path]) -> datetime | None:
    candidates: list[datetime] = []
    for payload in payloads:
        for item in iter_dicts(payload):
            for key in TIMESTAMP_KEYS:
                parsed = parse_time(item.get(key))
                if parsed:
                    candidates.append(parsed)
    for path in paths:
        if path.exists():
            candidates.append(datetime.fromtimestamp(path.stat().st_mtime, IST))
    return max(candidates) if candidates else None


def status_tokens(payloads: list[Any]) -> list[str]:
    values: list[str] = []
    for payload in payloads:
        for item in iter_dicts(payload):
            for key in STATUS_KEYS:
                value = item.get(key)
                if value not in (None, ""):
                    values.append(str(value).upper())
    return values


def contains_any(values: list[str], tokens: tuple[str, ...]) -> bool:
    return any(token in value for value in values for token in tokens)


def pid_lock_paths() -> list[Path]:
    paths = list(RUNTIME_DIR.glob("*.pid"))
    paths.extend(RUNTIME_DIR.glob("*.lock"))
    locks_dir = RUNTIME_DIR / "locks"
    if locks_dir.exists():
        paths.extend(path for path in locks_dir.iterdir() if path.is_file())
    return paths


def load_payload(path: Path) -> Any:
    if path.suffix.lower() == ".jsonl":
        return read_jsonl_latest(path)
    return read_json(path)


def evaluate_subsystem(name: str, configured_paths: list[Path]) -> dict[str, Any]:
    paths = configured_paths[:]
    if name == "Runtime Workers":
        paths.extend(pid_lock_paths())
    present_paths = [path for path in paths if path.exists()]
    payloads = [load_payload(path) for path in present_paths]
    payloads = [payload for payload in payloads if payload is not None]
    latest = latest_timestamp(payloads, present_paths)
    now = datetime.now(IST)
    freshness_seconds = int((now - latest).total_seconds()) if latest else None
    values = status_tokens(payloads)
    evidence_found = bool(present_paths)
    missing = [relative(path) for path in configured_paths if not path.exists()]

    if not evidence_found:
        status = "UNKNOWN"
        confidence = "LOW"
        reason = "No configured evidence files found."
    elif contains_any(values, FAIL_TOKENS):
        status = "FAIL"
        confidence = "HIGH"
        reason = "A current evidence status/verdict field contains a failure token."
    elif contains_any(values, STOPPED_TOKENS):
        status = "STOPPED"
        confidence = "HIGH" if latest else "MEDIUM"
        reason = "Evidence status/verdict indicates stopped/offline."
    elif latest is None:
        status = "UNKNOWN"
        confidence = "LOW"
        reason = "Evidence files exist, but no timestamp or file mtime could prove recency."
    elif freshness_seconds is not None and freshness_seconds > FRESH_SECONDS:
        status = "STALE"
        confidence = "MEDIUM"
        reason = f"Latest evidence is older than {FRESH_SECONDS} seconds."
    elif contains_any(values, RUNNING_TOKENS):
        status = "RUNNING"
        confidence = "HIGH"
        reason = "Fresh evidence contains a running/active status token."
    elif contains_any(values, HEALTHY_TOKENS):
        status = "HEALTHY"
        confidence = "HIGH"
        reason = "Fresh evidence contains a healthy/pass/ready status token."
    elif contains_any(values, DEGRADED_TOKENS):
        status = "DEGRADED"
        confidence = "MEDIUM"
        reason = "Fresh evidence contains degraded/warning/partial token."
    else:
        status = "NOT_PROVEN"
        confidence = "LOW"
        reason = "Evidence exists, but status fields do not prove running or health."

    return {
        "subsystem": name,
        "evidence_found": evidence_found,
        "latest_timestamp": latest.isoformat() if latest else None,
        "freshness_seconds": freshness_seconds,
        "status": status,
        "confidence": confidence,
        "evidence_files": [
            {"path": relative(path), "exists": path.exists()}
            for path in paths
        ],
        "missing_evidence": missing,
        "status_values_seen": values[:20],
        "reason": reason,
    }


def verdict_for(summary_counts: dict[str, int], subsystems: dict[str, dict[str, Any]]) -> str:
    core = [
        subsystems["Scanner"]["status"],
        subsystems["Master Brain"]["status"],
        subsystems["Runtime Workers"]["status"],
        subsystems["Unified Brain"]["status"],
    ]
    if all(status in ("RUNNING", "HEALTHY") for status in core):
        return "RUNTIME_PROVEN"
    if summary_counts["fail_count"] > 0:
        return "PARTIAL_RUNTIME_EVIDENCE"
    if summary_counts["stale_count"] > 0:
        return "STALE_RUNTIME_EVIDENCE"
    if any(status not in ("UNKNOWN", "NOT_PROVEN") for status in core):
        return "PARTIAL_RUNTIME_EVIDENCE"
    return "RUNTIME_NOT_PROVEN"


def build_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    subsystem_list = [evaluate_subsystem(name, paths) for name, paths in SUBSYSTEMS.items()]
    subsystems = {item["subsystem"]: item for item in subsystem_list}
    status_counts = {
        "stale_count": sum(1 for item in subsystem_list if item["status"] == "STALE"),
        "unknown_count": sum(1 for item in subsystem_list if item["status"] in ("UNKNOWN", "NOT_PROVEN")),
        "fail_count": sum(1 for item in subsystem_list if item["status"] == "FAIL"),
        "healthy_count": sum(1 for item in subsystem_list if item["status"] in ("RUNNING", "HEALTHY")),
    }
    report = {
        "schema": "titan.echo.runtime_evidence_report.v1",
        "timestamp_ist": timestamp_ist(),
        "freshness_rule_seconds": FRESH_SECONDS,
        "truth_rule": "RUNNING/HEALTHY requires fresh timestamp plus supportive status evidence.",
        "safety": {
            "read_only_evidence_layer": True,
            "reads_env": False,
            "shell_execution": False,
            "codex_execution": False,
            "writes_outside_echo_runtime": False,
            "broker_risk_scanner_changes": False,
            "deploy_or_restart": False,
        },
        "subsystems": subsystems,
    }
    summary = {
        "schema": "titan.echo.runtime_evidence_summary.v1",
        "timestamp_ist": report["timestamp_ist"],
        "titan_runtime_status": subsystems["Runtime Workers"]["status"],
        "scanner_runtime_status": subsystems["Scanner"]["status"],
        "master_brain_runtime_status": subsystems["Master Brain"]["status"],
        "worker_runtime_status": subsystems["Runtime Workers"]["status"],
        "unified_brain_runtime_status": subsystems["Unified Brain"]["status"],
        **status_counts,
        "current_runtime_truth_verdict": verdict_for(status_counts, subsystems),
        "still_unknown_systems": [
            item["subsystem"]
            for item in subsystem_list
            if item["status"] in ("UNKNOWN", "NOT_PROVEN")
        ],
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
    print("ECHO runtime evidence generated.")
    print(f"titan_runtime_status={summary['titan_runtime_status']}")
    print(f"scanner_runtime_status={summary['scanner_runtime_status']}")
    print(f"master_brain_runtime_status={summary['master_brain_runtime_status']}")
    print(f"worker_runtime_status={summary['worker_runtime_status']}")
    print(f"unified_brain_runtime_status={summary['unified_brain_runtime_status']}")
    print(f"stale_count={summary['stale_count']}")
    print(f"unknown_count={summary['unknown_count']}")
    print(f"fail_count={summary['fail_count']}")
    print(f"healthy_count={summary['healthy_count']}")
    print(f"current_runtime_truth_verdict={summary['current_runtime_truth_verdict']}")
    print("still_unknown_systems=" + ", ".join(summary["still_unknown_systems"]))


if __name__ == "__main__":
    main()
