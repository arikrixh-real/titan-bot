"""Validate the ECHO Batch B summary."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "titan_echo" / "echo_batch_b_summary.py"
OUTPUT = ROOT / "data" / "runtime" / "echo" / "batch_b_summary.json"
PREREQS = [
    ROOT / "titan_echo" / "echo_unified_brain_gap_analysis.py",
    ROOT / "titan_echo" / "echo_consciousness_influence_audit.py",
    ROOT / "titan_echo" / "echo_master_brain_influence_audit.py",
    ROOT / "titan_echo" / "echo_system_influence_map.py",
]
REQUIRED = [
    "current_real_top_authority",
    "unified_brain_gap_score",
    "consciousness_influence_score",
    "master_brain_influence_score",
    "system_influence_score",
    "strongest_real_influence_paths",
    "weakest_or_missing_influence_paths",
    "actual_control_hierarchy",
    "expected_final_hierarchy",
    "gap_between_current_and_target",
    "recommended_next_missions",
    "verdict",
]


def run_script(path: Path, errors: list[str]) -> None:
    result = subprocess.run([sys.executable, str(path)], cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode:
        errors.append(f"{path.name} failed: {result.returncode}")
    if result.stderr:
        errors.append(f"{path.name} wrote stderr")


def main() -> int:
    errors: list[str] = []
    for prereq in PREREQS:
        run_script(prereq, errors)
    run_script(SCRIPT, errors)
    try:
        data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except Exception as exc:
        data = {}
        errors.append(f"invalid output json: {exc}")
    for field in REQUIRED:
        if field not in data:
            errors.append(f"missing {field}")
    if not isinstance(data.get("verdict"), list):
        errors.append("verdict must be a list")
    if errors:
        print("TITAN ECHO Batch B summary check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("TITAN ECHO Batch B summary check: PASSED")
    print(f"Current real top authority: {data.get('current_real_top_authority')}")
    print(f"Unified Brain gap score: {data.get('unified_brain_gap_score')}")
    print(f"Consciousness influence score: {data.get('consciousness_influence_score')}")
    print(f"Master Brain influence score: {data.get('master_brain_influence_score')}")
    print(f"System influence score: {data.get('system_influence_score')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
