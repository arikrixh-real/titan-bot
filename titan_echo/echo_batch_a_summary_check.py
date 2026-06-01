"""Validate the ECHO Batch A summary."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "titan_echo" / "echo_batch_a_summary.py"
OUTPUT = ROOT / "data" / "runtime" / "echo" / "batch_a_summary.json"
REQUIRED = [
    "improvement_confidence_score",
    "decision_trace_score",
    "confidence_calibration_score",
    "strongest_proofs",
    "weakest_proofs",
    "missing_evidence",
    "causality_confidence",
    "verdict",
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
    if data.get("verdict") not in {"PROVEN", "PARTIAL", "NOT_PROVEN", "UNKNOWN"}:
        errors.append("invalid verdict")
    if errors:
        print("TITAN ECHO Batch A summary check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("TITAN ECHO Batch A summary check: PASSED")
    print(f"Improvement confidence score: {data.get('improvement_confidence_score')}")
    print(f"Decision trace score: {data.get('decision_trace_score')}")
    print(f"Confidence calibration score: {data.get('confidence_calibration_score')}")
    print(f"Batch A verdict: {data.get('verdict')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
