"""Validate the Unified Brain gap analysis report."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "titan_echo" / "echo_unified_brain_gap_analysis.py"
OUTPUT = ROOT / "data" / "runtime" / "echo" / "unified_brain_gap_report.json"
REQUIRED = [
    "unified_brain_exists_status",
    "running_status",
    "connection_status",
    "influence_status",
    "missing_components",
    "required_interfaces",
    "recommended_build_steps",
    "risk_level",
    "unified_brain_gap_score",
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
    if not isinstance(data.get("unified_brain_gap_score"), int):
        errors.append("unified_brain_gap_score must be int")
    if errors:
        print("TITAN ECHO Unified Brain gap analysis check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("TITAN ECHO Unified Brain gap analysis check: PASSED")
    print(f"Unified Brain gap score: {data.get('unified_brain_gap_score')}")
    print(f"Unified Brain status: {data.get('unified_brain_exists_status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
