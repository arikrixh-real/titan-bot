"""Validate the ECHO decision trace audit."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "titan_echo" / "echo_decision_trace_audit.py"
OUTPUT = ROOT / "data" / "runtime" / "echo" / "decision_trace_audit.json"
REQUIRED = [
    "decision_trace_score",
    "traceable_decisions",
    "partially_traceable_decisions",
    "untraceable_decisions",
    "feedback_loop_completeness",
    "broken_links",
    "missing_links",
    "orphan_outcomes",
]


def main() -> int:
    errors = []
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode:
        errors.append(f"script failed: {result.returncode}")
    if result.stderr:
        errors.append("script wrote stderr")
    try:
        data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except Exception as exc:
        data = {}
        errors.append(f"invalid output json: {exc}")
    for field in REQUIRED:
        if field not in data:
            errors.append(f"missing {field}")
    if errors:
        print("TITAN ECHO decision trace audit check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("TITAN ECHO decision trace audit check: PASSED")
    print(f"Decision trace score: {data.get('decision_trace_score')}")
    print(f"Causality status: {data.get('causality_status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
