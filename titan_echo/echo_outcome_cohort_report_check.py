"""Validate the ECHO outcome cohort report."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "titan_echo" / "echo_outcome_cohort_report.py"
OUTPUT = ROOT / "data" / "runtime" / "echo" / "outcome_cohort_report.json"
REQUIRED = [
    "cohort_comparison_score",
    "improvement_confidence_score",
    "strongest_cohort_evidence",
    "weakest_cohort_evidence",
    "cohort_separation_status",
    "cohorts",
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
    for cohort in ["live", "paper", "synthetic", "unknown"]:
        if cohort not in data.get("cohorts", {}):
            errors.append(f"missing cohort {cohort}")
    if errors:
        print("TITAN ECHO outcome cohort report check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("TITAN ECHO outcome cohort report check: PASSED")
    print(f"Improvement confidence score: {data.get('improvement_confidence_score')}")
    print(f"Cohort separation status: {data.get('cohort_separation_status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
