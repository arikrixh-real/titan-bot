"""Validate the system influence map report."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "titan_echo" / "echo_system_influence_map.py"
OUTPUT = ROOT / "data" / "runtime" / "echo" / "system_influence_map.json"
REQUIRED = [
    "subsystems",
    "top_influence_chains",
    "weak_influence_chains",
    "dead_paths",
    "passive_modules",
    "missing_influence_links",
    "current_control_hierarchy",
    "recommended_integration_upgrades",
    "system_influence_score",
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
    if len(data.get("subsystems", [])) < 16:
        errors.append("expected at least 16 subsystem entries")
    if errors:
        print("TITAN ECHO system influence map check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("TITAN ECHO system influence map check: PASSED")
    print(f"System influence score: {data.get('system_influence_score')}")
    print(f"Hierarchy: {' > '.join(data.get('current_control_hierarchy', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
