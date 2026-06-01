"""Checker for the ECHO worker/scanner failure focus audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from titan_echo.echo_worker_scanner_failure_focus import REPORT_PATH, SUMMARY_PATH, generate_reports


SCRIPT_PATH = REPO_ROOT / "titan_echo" / "echo_worker_scanner_failure_focus.py"
VALID_SCANNER_TYPES = {"LEGACY_WAITING_REGENERATION", "ACTIVE_FAILURE", "STALE", "UNKNOWN"}
VALID_WORKER_TYPES = {"MISSING_EVIDENCE", "DEGRADED_WORKERS", "STALE", "ACTIVE_FAILURE", "UNKNOWN"}
VALID_TRUTH_RELATIONS = {"SCANNER_DEPENDENT", "EXTERNAL_CONFIG", "OUTCOME_SAMPLE", "SUPABASE", "UNKNOWN"}
VALID_FILTER_RELATIONS = {"SCANNER_DEPENDENT", "TRUE_FILTER_FAILURE", "LEGACY_DIAGNOSTIC", "UNKNOWN"}
REQUIRED_KEYS = {
    "scanner_fail_type",
    "worker_fail_type",
    "truth_gate_relation",
    "filter_engine_relation",
    "exact_remaining_blocker",
    "recommended_next_action",
    "safety",
}
FORBIDDEN_TOKENS = {
    "subprocess",
    "os.system",
    "Popen",
    "threading.Thread",
    "start_continuous_workers(",
    "run_scanner(",
    "preview_dispatch(",
    "from engines.risk_engine",
    "import engines.risk_engine",
    "place_order",
    "execute_order",
    "evaluate_setups(",
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


def build_check() -> dict[str, Any]:
    generate_reports()
    report = read_json(REPORT_PATH)
    summary = read_json(SUMMARY_PATH)
    source = read_text(SCRIPT_PATH)
    forbidden_found = sorted(token for token in FORBIDDEN_TOKENS if token in source)
    failures: list[str] = []

    if not REPORT_PATH.exists():
        failures.append("focus report missing")
    if not SUMMARY_PATH.exists():
        failures.append("focus summary missing")
    if not report:
        failures.append("focus report invalid")
    if not summary:
        failures.append("focus summary invalid")

    missing = sorted(REQUIRED_KEYS - set(summary))
    if missing:
        failures.append("summary missing keys: " + ", ".join(missing))
    if summary.get("scanner_fail_type") not in VALID_SCANNER_TYPES:
        failures.append("invalid scanner_fail_type")
    if summary.get("worker_fail_type") not in VALID_WORKER_TYPES:
        failures.append("invalid worker_fail_type")
    if summary.get("truth_gate_relation") not in VALID_TRUTH_RELATIONS:
        failures.append("invalid truth_gate_relation")
    if summary.get("filter_engine_relation") not in VALID_FILTER_RELATIONS:
        failures.append("invalid filter_engine_relation")
    if not summary.get("exact_remaining_blocker"):
        failures.append("exact_remaining_blocker missing")
    if not summary.get("recommended_next_action"):
        failures.append("recommended_next_action missing")

    safety = summary.get("safety") if isinstance(summary.get("safety"), dict) else {}
    expected_false = {
        "restart_executed",
        "deploy_executed",
        "push_executed",
        "scanner_modified",
        "workers_modified",
        "broker_risk_modified",
        "master_brain_modified",
        "unified_brain_modified",
        "runtime_scheduling_modified",
    }
    for key in sorted(expected_false):
        if safety.get(key) is not False:
            failures.append(f"safety.{key} must be false")
    if safety.get("read_only_investigation") is not True:
        failures.append("safety.read_only_investigation must be true")
    if safety.get("writes_only_echo_reports") is not True:
        failures.append("safety.writes_only_echo_reports must be true")
    if forbidden_found:
        failures.append("forbidden runtime-control/protected token found")

    return {
        "schema": "titan.echo.worker_scanner_failure_focus_check.v1",
        "status": "PASS" if not failures else "FAIL",
        "report_exists": REPORT_PATH.exists(),
        "summary_exists": SUMMARY_PATH.exists(),
        "json_valid": bool(report) and bool(summary),
        "scanner_fail_type": summary.get("scanner_fail_type"),
        "worker_fail_type": summary.get("worker_fail_type"),
        "truth_gate_relation": summary.get("truth_gate_relation"),
        "filter_engine_relation": summary.get("filter_engine_relation"),
        "exact_remaining_blocker": summary.get("exact_remaining_blocker"),
        "recommended_next_action": summary.get("recommended_next_action"),
        "forbidden_tokens_found": forbidden_found,
        "failures": failures,
    }


def main() -> None:
    result = build_check()
    print("ECHO worker/scanner failure focus check complete.")
    print(f"status={result['status']}")
    print(f"report_exists={result['report_exists']}")
    print(f"summary_exists={result['summary_exists']}")
    print(f"json_valid={result['json_valid']}")
    print(f"scanner_fail_type={result['scanner_fail_type']}")
    print(f"worker_fail_type={result['worker_fail_type']}")
    print(f"truth_gate_relation={result['truth_gate_relation']}")
    print(f"filter_engine_relation={result['filter_engine_relation']}")
    print(f"exact_remaining_blocker={result['exact_remaining_blocker']}")
    print(f"recommended_next_action={result['recommended_next_action']}")
    print(f"forbidden_tokens_found={result['forbidden_tokens_found']}")
    if result["failures"]:
        print("failures=" + "; ".join(result["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
