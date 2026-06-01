"""Checker for ECHO brain status evidence compatibility files."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from titan_echo.echo_brain_status_evidence_writer import (
    BRAIN_STATE_PATH,
    REPAIR_REPORT_PATH,
    UNIFIED_BRAIN_STATUS_PATH,
    generate_brain_status_evidence,
)


WRITER_PATH = REPO_ROOT / "titan_echo" / "echo_brain_status_evidence_writer.py"
CHECKER_PATH = REPO_ROOT / "titan_echo" / "echo_brain_status_evidence_check.py"
REQUIRED_BRAIN_KEYS = {
    "timestamp_ist",
    "status_source",
    "master_brain_status",
    "evidence_files_read",
    "missing_evidence",
    "brain_behavior_changed",
}
REQUIRED_UNIFIED_KEYS = {
    "timestamp_ist",
    "status_source",
    "unified_brain_status",
    "promotion_state",
    "architecture_state",
    "validation_state",
    "live_decision_allowed",
    "evidence_files_read",
    "missing_evidence",
    "unified_brain_behavior_changed",
}
FORBIDDEN_TOKENS = {
    "subprocess",
    "os.system",
    "Popen",
    "threading.Thread",
    "from runtime_master_brain",
    "import runtime_master_brain",
    "from titan_master_brain",
    "import titan_master_brain",
    "from unified_brain",
    "import unified_brain",
    "from engines.risk_engine",
    "import engines.risk_engine",
    "start_continuous_workers(",
    "preview_dispatch(",
    "run_scanner(",
    "run_master_brain(",
    "evaluate_setups(",
    "calculate_trade_levels(",
    "calculate_rr(",
    "place_order",
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


def validate() -> dict[str, Any]:
    generate_brain_status_evidence()
    brain_state = read_json(BRAIN_STATE_PATH)
    unified_status = read_json(UNIFIED_BRAIN_STATUS_PATH)
    repair_report = read_json(REPAIR_REPORT_PATH)
    source = read_text(WRITER_PATH)
    forbidden_found = sorted(token for token in FORBIDDEN_TOKENS if token in source)

    failures: list[str] = []
    if not BRAIN_STATE_PATH.exists():
        failures.append("brain_state.json missing")
    if not UNIFIED_BRAIN_STATUS_PATH.exists():
        failures.append("unified_brain_status.json missing")
    if not brain_state:
        failures.append("brain_state.json invalid")
    if not unified_status:
        failures.append("unified_brain_status.json invalid")

    missing_brain_keys = sorted(REQUIRED_BRAIN_KEYS - set(brain_state))
    if missing_brain_keys:
        failures.append("brain_state.json missing keys: " + ", ".join(missing_brain_keys))
    missing_unified_keys = sorted(REQUIRED_UNIFIED_KEYS - set(unified_status))
    if missing_unified_keys:
        failures.append("unified_brain_status.json missing keys: " + ", ".join(missing_unified_keys))

    if brain_state.get("brain_behavior_changed") is not False:
        failures.append("brain_behavior_changed must be false")
    if unified_status.get("unified_brain_behavior_changed") is not False:
        failures.append("unified_brain_behavior_changed must be false")
    if unified_status.get("live_decision_allowed") is not False:
        failures.append("live_decision_allowed must be false")

    safety = repair_report.get("safety") if isinstance(repair_report.get("safety"), dict) else {}
    expected_false = {
        "master_brain_decision_logic_changed",
        "unified_brain_reasoning_logic_changed",
        "scanner_filter_risk_broker_changed",
        "daemon_restart_start_stop",
        "duplicate_runner_logic_added",
        "runtime_scheduling_changed",
        "live_decision_allowed",
    }
    for key in sorted(expected_false):
        if safety.get(key) is not False:
            failures.append(f"safety.{key} must be false")
    if safety.get("metadata_status_evidence_only") is not True:
        failures.append("safety.metadata_status_evidence_only must be true")
    if forbidden_found:
        failures.append("forbidden logic/control token found in evidence writer/checker")

    return {
        "schema": "titan.echo.brain_status_evidence_check.v1",
        "status": "PASS" if not failures else "FAIL",
        "brain_state_exists": BRAIN_STATE_PATH.exists(),
        "unified_brain_status_exists": UNIFIED_BRAIN_STATUS_PATH.exists(),
        "brain_state_json_valid": bool(brain_state),
        "unified_brain_status_json_valid": bool(unified_status),
        "brain_behavior_changed": brain_state.get("brain_behavior_changed"),
        "unified_brain_behavior_changed": unified_status.get("unified_brain_behavior_changed"),
        "live_decision_allowed": unified_status.get("live_decision_allowed"),
        "no_master_unified_logic_changed": not forbidden_found,
        "no_daemon_restart_start_stop_logic_added": safety.get("daemon_restart_start_stop") is False,
        "no_broker_risk_scanner_logic_changed": safety.get("scanner_filter_risk_broker_changed") is False,
        "no_duplicate_runner_logic_added": safety.get("duplicate_runner_logic_added") is False,
        "forbidden_tokens_found": forbidden_found,
        "failures": failures,
        "brain_state_summary": {
            "timestamp_ist": brain_state.get("timestamp_ist"),
            "status_source": brain_state.get("status_source"),
            "master_brain_status": brain_state.get("master_brain_status"),
            "missing_evidence": brain_state.get("missing_evidence"),
        },
        "unified_brain_status_summary": {
            "timestamp_ist": unified_status.get("timestamp_ist"),
            "status_source": unified_status.get("status_source"),
            "unified_brain_status": unified_status.get("unified_brain_status"),
            "promotion_state": unified_status.get("promotion_state"),
            "architecture_state": unified_status.get("architecture_state"),
            "validation_state": unified_status.get("validation_state"),
            "live_decision_allowed": unified_status.get("live_decision_allowed"),
            "missing_evidence": unified_status.get("missing_evidence"),
        },
        "remaining_missing_evidence": repair_report.get("remaining_missing_evidence") or [],
    }


def main() -> None:
    result = validate()
    brain = result["brain_state_summary"]
    unified = result["unified_brain_status_summary"]
    master = brain.get("master_brain_status") or {}
    print("ECHO brain status evidence check complete.")
    print(f"status={result['status']}")
    print(f"brain_state_exists={result['brain_state_exists']}")
    print(f"unified_brain_status_exists={result['unified_brain_status_exists']}")
    print(f"brain_behavior_changed={result['brain_behavior_changed']}")
    print(f"unified_brain_behavior_changed={result['unified_brain_behavior_changed']}")
    print(f"master_brain_status={master.get('status')}")
    print(f"unified_brain_status={unified.get('unified_brain_status')}")
    print(f"promotion_state={unified.get('promotion_state')}")
    print(f"architecture_state={unified.get('architecture_state')}")
    print(f"validation_state={unified.get('validation_state')}")
    print(f"live_decision_allowed={result['live_decision_allowed']}")
    print("remaining_missing_evidence=" + ", ".join(result["remaining_missing_evidence"]))
    print(f"no_master_unified_logic_changed={result['no_master_unified_logic_changed']}")
    print(f"no_daemon_restart_start_stop_logic_added={result['no_daemon_restart_start_stop_logic_added']}")
    print(f"no_broker_risk_scanner_logic_changed={result['no_broker_risk_scanner_logic_changed']}")
    print(f"no_duplicate_runner_logic_added={result['no_duplicate_runner_logic_added']}")
    print(f"forbidden_tokens_found={result['forbidden_tokens_found']}")
    if result["failures"]:
        print("failures=" + "; ".join(result["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
