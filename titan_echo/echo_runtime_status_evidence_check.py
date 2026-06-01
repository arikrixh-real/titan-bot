"""Checker for the ECHO runtime_status compatibility evidence writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_STATUS_SOURCE = REPO_ROOT / "runtime_status.py"
CHECK_SOURCE = REPO_ROOT / "titan_echo" / "echo_runtime_status_evidence_check.py"
RUNTIME_STATUS_PATH = REPO_ROOT / "data" / "runtime" / "runtime_status.json"
REPAIR_REPORT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "runtime_status_evidence_repair_report.json"

REQUIRED_RUNTIME_KEYS = {
    "timestamp_ist",
    "status_source",
    "titan_runtime_status",
    "scanner_status_summary",
    "worker_health_summary",
    "master_brain_status_summary",
    "unified_brain_status_summary",
    "truth_gate_summary",
    "evidence_files_read",
    "missing_evidence",
    "runtime_behavior_changed",
}
FORBIDDEN_SOURCE_TOKENS = {
    "subprocess",
    "os.system",
    "Popen",
    "start_continuous_workers(",
    "preview_dispatch(",
    "run_scanner(",
    "titan_daemon.main(",
    "acquire_lock(",
    "release_lock(",
    "threading.Thread",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def source_window(text: str) -> str:
    marker = "def build_echo_runtime_status_evidence"
    start = text.find(marker)
    if start == -1:
        return text
    end_marker = "def write_runtime_status"
    end = text.find(end_marker, start)
    if end == -1:
        return text[start:]
    return text[start:end]


def build_check() -> dict[str, Any]:
    runtime_status = read_json(RUNTIME_STATUS_PATH)
    repair_report = read_json(REPAIR_REPORT_PATH)
    runtime_source = read_text(RUNTIME_STATUS_SOURCE)
    evidence_writer_source = source_window(runtime_source)
    forbidden_tokens_found = sorted(token for token in FORBIDDEN_SOURCE_TOKENS if token in evidence_writer_source)

    failures: list[str] = []
    if not RUNTIME_STATUS_PATH.exists():
        failures.append("runtime_status.json missing")
    if not runtime_status:
        failures.append("runtime_status.json invalid or empty")
    missing_keys = sorted(REQUIRED_RUNTIME_KEYS - set(runtime_status))
    if missing_keys:
        failures.append("runtime_status.json missing keys: " + ", ".join(missing_keys))
    if not runtime_status.get("timestamp_ist"):
        failures.append("timestamp_ist missing")
    if runtime_status.get("runtime_behavior_changed") is not False:
        failures.append("runtime_behavior_changed must be false")
    if not isinstance(runtime_status.get("evidence_files_read"), list):
        failures.append("evidence_files_read must be a list")
    if not isinstance(runtime_status.get("missing_evidence"), list):
        failures.append("missing_evidence must be a list")
    if not repair_report:
        failures.append("repair report missing or invalid")
    safety = repair_report.get("safety") if isinstance(repair_report.get("safety"), dict) else {}
    expected_false = {
        "daemon_restart_start_stop",
        "worker_scheduling_changed",
        "duplicate_runner_logic_added",
        "scanner_logic_changed",
        "broker_risk_changed",
        "master_brain_behavior_changed",
        "unified_brain_behavior_changed",
    }
    for key in sorted(expected_false):
        if safety.get(key) is not False:
            failures.append(f"safety.{key} must be false")
    if safety.get("metadata_status_evidence_only") is not True:
        failures.append("safety.metadata_status_evidence_only must be true")
    if forbidden_tokens_found:
        failures.append("forbidden daemon/runtime-control token found in evidence writer")

    return {
        "schema": "titan.echo.runtime_status_evidence_check.v1",
        "status": "PASS" if not failures else "FAIL",
        "runtime_status_exists": RUNTIME_STATUS_PATH.exists(),
        "runtime_status_json_valid": bool(runtime_status),
        "timestamp_present": bool(runtime_status.get("timestamp_ist")),
        "runtime_behavior_changed": runtime_status.get("runtime_behavior_changed"),
        "repair_report_exists": REPAIR_REPORT_PATH.exists(),
        "no_daemon_restart_start_stop_logic_added": "daemon_restart_start_stop" not in failures and not forbidden_tokens_found,
        "no_protected_behavior_changed": not any("behavior_changed" in failure or "scanner_logic" in failure for failure in failures),
        "no_duplicate_runner_logic_added": safety.get("duplicate_runner_logic_added") is False and "threading.Thread" not in forbidden_tokens_found,
        "forbidden_tokens_found": forbidden_tokens_found,
        "failures": failures,
        "runtime_status_summary": {
            "timestamp_ist": runtime_status.get("timestamp_ist"),
            "status_source": runtime_status.get("status_source"),
            "titan_runtime_status": runtime_status.get("titan_runtime_status"),
            "worker_health_summary": runtime_status.get("worker_health_summary"),
            "missing_evidence": runtime_status.get("missing_evidence"),
        },
    }


def main() -> None:
    result = build_check()
    summary = result["runtime_status_summary"]
    worker = summary.get("worker_health_summary") or {}
    titan = summary.get("titan_runtime_status") or {}
    print("ECHO runtime status evidence check complete.")
    print(f"status={result['status']}")
    print(f"runtime_status_exists={result['runtime_status_exists']}")
    print(f"runtime_status_json_valid={result['runtime_status_json_valid']}")
    print(f"timestamp_present={result['timestamp_present']}")
    print(f"runtime_behavior_changed={result['runtime_behavior_changed']}")
    print(f"titan_runtime_status={titan.get('status')}")
    print(f"worker_health_status={worker.get('status')}")
    print(f"worker_count={worker.get('worker_count')}")
    print("remaining_missing_evidence=" + ", ".join(summary.get("missing_evidence") or []))
    print(f"no_daemon_restart_start_stop_logic_added={result['no_daemon_restart_start_stop_logic_added']}")
    print(f"no_protected_behavior_changed={result['no_protected_behavior_changed']}")
    print(f"no_duplicate_runner_logic_added={result['no_duplicate_runner_logic_added']}")
    print(f"forbidden_tokens_found={result['forbidden_tokens_found']}")
    if result["failures"]:
        print("failures=" + "; ".join(result["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
