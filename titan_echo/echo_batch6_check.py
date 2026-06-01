"""Checker for ECHO Batch 6 failure split and conversation style outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
FILES = [
    REPO_ROOT / "titan_echo" / "echo_failure_split_audit.py",
    REPO_ROOT / "titan_echo" / "echo_conversation_style.py",
    REPO_ROOT / "titan_echo" / "echo_batch6_check.py",
]
REPORTS = [
    REPO_ROOT / "data" / "runtime" / "echo" / "failure_split_audit.json",
    REPO_ROOT / "data" / "runtime" / "echo" / "echo_conversation_style.json",
    REPO_ROOT / "data" / "runtime" / "echo" / "batch6_summary.json",
]
DANGEROUS_TOKENS = ("subprocess", "os.system", "shlex", "pexpect")


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def build_check() -> dict[str, Any]:
    failure = read_json(REPORTS[0])
    style = read_json(REPORTS[1])
    summary = read_json(REPORTS[2])
    source = "\n".join(read_text(path) for path in FILES[:2])
    dangerous_found = [token for token in DANGEROUS_TOKENS if token in source]
    failures: list[str] = []
    if not all(path.exists() for path in FILES):
        failures.append("Batch 6 scripts missing")
    if not all(path.exists() for path in REPORTS):
        failures.append("Batch 6 reports missing")
    if not failure or not style or not summary:
        failures.append("Batch 6 JSON invalid")
    if dangerous_found:
        failures.append("dangerous command execution token found")
    if style.get("echo_tone_mode") != "HUMAN_REASONING_TRUTH_GROUNDED":
        failures.append("conversation mode missing")
    if not failure.get("highest_priority_failure"):
        failures.append("highest priority failure missing")
    safety = failure.get("safety", {})
    if safety.get("runtime_repair_executed") is not False or safety.get("shell_execution") is not False:
        failures.append("read-only safety not confirmed")
    return {
        "schema": "titan.echo.batch6_check.v1",
        "status": "PASS" if not failures else "FAIL",
        "files_exist": all(path.exists() for path in FILES),
        "reports_exist": all(path.exists() for path in REPORTS),
        "json_valid": bool(failure and style and summary),
        "dangerous_tokens_found": dangerous_found,
        "conversation_mode": style.get("echo_tone_mode"),
        "highest_priority_failure": (failure.get("highest_priority_failure") or {}).get("category"),
        "next_repair_mission": failure.get("next_repair_mission"),
        "safety_result": "PASS" if not failures else "FAIL",
        "failures": failures,
    }


def main() -> None:
    report = build_check()
    print("ECHO Batch 6 check complete.")
    print(f"status={report['status']}")
    print(f"files_exist={report['files_exist']}")
    print(f"reports_exist={report['reports_exist']}")
    print(f"json_valid={report['json_valid']}")
    print(f"dangerous_tokens_found={report['dangerous_tokens_found']}")
    print(f"conversation_mode={report['conversation_mode']}")
    print(f"highest_priority_failure={report['highest_priority_failure']}")
    print(f"next_repair_mission={report['next_repair_mission']}")
    print(f"safety_result={report['safety_result']}")
    if report["failures"]:
        print("failures=" + "; ".join(report["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
