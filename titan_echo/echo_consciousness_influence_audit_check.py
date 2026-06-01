"""Validate the Consciousness influence audit report."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "titan_echo" / "echo_consciousness_influence_audit.py"
OUTPUT = ROOT / "data" / "runtime" / "echo" / "consciousness_influence_report.json"
REQUIRED = [
    "consciousness_exists_status",
    "output_generation_status",
    "downstream_consumption_status",
    "decision_influence_status",
    "passive_vs_active_verdict",
    "strongest_evidence",
    "missing_evidence",
    "recommended_next_steps",
    "consciousness_influence_score",
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
    if not isinstance(data.get("consciousness_influence_score"), int):
        errors.append("consciousness_influence_score must be int")
    if errors:
        print("TITAN ECHO Consciousness influence audit check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("TITAN ECHO Consciousness influence audit check: PASSED")
    print(f"Consciousness influence score: {data.get('consciousness_influence_score')}")
    print(f"Verdict: {data.get('verdict')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
