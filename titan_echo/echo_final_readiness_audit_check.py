"""Validate the ECHO + Unified Brain final readiness audit outputs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "titan_echo" / "echo_final_readiness_audit.py"
CHECK = ROOT / "titan_echo" / "echo_final_readiness_audit_check.py"
AUDIT = ROOT / "data" / "runtime" / "echo" / "final_readiness_audit.json"
SUMMARY = ROOT / "data" / "runtime" / "echo" / "final_readiness_summary.json"
VALID_VERDICTS = {"READY_FOR_NEXT_BUILD", "FOCUS_ON_EVIDENCE", "FOCUS_ON_OUTCOMES", "NOT_READY", "UNKNOWN"}


def load(path: Path, errors: list[str]) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"invalid json {path}: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{path.name} must contain a JSON object")
        return {}
    return data


def main() -> int:
    errors: list[str] = []
    for path in (SCRIPT, CHECK):
        if not path.exists():
            errors.append(f"missing script: {path}")
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode:
        errors.append(f"audit script failed: {result.returncode}")
    if result.stderr:
        errors.append("audit script wrote stderr")
    for path in (AUDIT, SUMMARY):
        if not path.exists():
            errors.append(f"missing output: {path}")
    audit = load(AUDIT, errors) if AUDIT.exists() else {}
    summary = load(SUMMARY, errors) if SUMMARY.exists() else {}
    for key in ("echo", "unified_brain", "blockers", "fake_progress_detection", "real_progress_detection", "do_next", "do_not_build_yet", "final_verdict"):
        if key not in audit:
            errors.append(f"audit missing {key}")
    for key in (
        "echo_completion_percent",
        "unified_brain_completion_percent",
        "validation_completion_percent",
        "promotion_readiness_percent",
        "biggest_blocker",
        "biggest_completed_achievement",
        "top_5_next_actions",
        "top_5_actions_to_avoid",
        "final_verdict",
        "recommended_next_action",
    ):
        if key not in summary:
            errors.append(f"summary missing {key}")
    if summary.get("final_verdict") not in VALID_VERDICTS:
        errors.append("invalid final verdict")
    if float(summary.get("promotion_readiness_percent") or 0) > 0 and float(summary.get("validation_completion_percent") or 0) == 0:
        errors.append("promotion readiness cannot be positive when validation completion is zero")
    avoid = json.dumps(summary.get("top_5_actions_to_avoid", []), sort_keys=True)
    if "LOW_VALUE_NEXT_STEP" not in avoid:
        errors.append("LOW_VALUE_NEXT_STEP not identified in actions to avoid")
    if errors:
        print("TITAN ECHO final readiness audit check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("TITAN ECHO final readiness audit check: PASSED")
    print(f"ECHO completion: {summary.get('echo_completion_percent')}%")
    print(f"Unified Brain completion: {summary.get('unified_brain_completion_percent')}%")
    print(f"Validation completion: {summary.get('validation_completion_percent')}%")
    print(f"Promotion readiness: {summary.get('promotion_readiness_percent')}%")
    print(f"Biggest blocker: {summary.get('biggest_blocker')}")
    print(f"Final verdict: {summary.get('final_verdict')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
