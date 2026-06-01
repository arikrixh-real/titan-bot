"""Validate the ECHO confidence calibration audit."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "titan_echo" / "echo_confidence_calibration_audit.py"
OUTPUT = ROOT / "data" / "runtime" / "echo" / "confidence_calibration_audit.json"
REQUIRED = [
    "confidence_calibration_score",
    "high_confidence_outcomes",
    "medium_confidence_outcomes",
    "low_confidence_outcomes",
    "overconfidence_evidence",
    "underconfidence_evidence",
    "calibration_quality",
    "trustworthiness_score",
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
        print("TITAN ECHO confidence calibration audit check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("TITAN ECHO confidence calibration audit check: PASSED")
    print(f"Confidence calibration score: {data.get('confidence_calibration_score')}")
    print(f"Validation status: {data.get('validation_status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
