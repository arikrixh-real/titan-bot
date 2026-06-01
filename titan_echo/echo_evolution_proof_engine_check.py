"""Validate the TITAN ECHO evolution proof engine."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = REPO_ROOT / "titan_echo" / "echo_evolution_proof_engine.py"
OUTPUT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "evolution_proof_report.json"

REQUIRED_CATEGORIES = {
    "memory_growth",
    "learning_activity",
    "outcome_feedback_loop",
    "evolution_parameter_changes",
    "performance_improvement_evidence",
    "confidence_calibration",
    "strategy_adaptation",
    "decision_influence",
    "self_reflection_usage",
    "historical_experience_usage",
}


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def run_engine() -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(ENGINE_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def validate_stdout(stdout: str) -> list[str]:
    allowed = (
        "TITAN ECHO evolution proof engine:",
        "Overall evolution score:",
        "Evolution verdict:",
        "Categories evaluated:",
        "Runtime files inspected:",
    )
    errors = []
    for line in stdout.splitlines():
        if not line.startswith(allowed):
            errors.append("Evolution proof engine printed unexpected output.")
            break
    return errors


def load_report() -> tuple[dict[str, Any] | None, str | None]:
    try:
        with OUTPUT_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None, f"Missing report: {relative(OUTPUT_PATH)}"
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {relative(OUTPUT_PATH)} line {exc.lineno}"
    if not isinstance(data, dict):
        return None, "Report root must be object."
    return data, None


def validate_report(report: dict[str, Any]) -> list[str]:
    errors = []
    for field in [
        "overall_evolution_score",
        "evolution_verdict",
        "strongest_evolution_evidence",
        "weakest_evolution_evidence",
        "top_missing_evolution_proofs",
        "recommended_next_missions",
    ]:
        if field not in report:
            errors.append(f"Missing {field}.")
    categories = report.get("categories")
    if not isinstance(categories, list):
        errors.append("categories must be a list.")
    else:
        represented = {str(item.get("category")) for item in categories if isinstance(item, dict)}
        missing = REQUIRED_CATEGORIES - represented
        if missing:
            errors.append(f"Missing categories: {sorted(missing)}")
        for item in categories:
            if not isinstance(item, dict):
                continue
            for field in ["status", "score", "evidence", "missing_evidence", "recommended_next_step"]:
                if field not in item:
                    errors.append(f"Category {item.get('category')} missing {field}.")
    return errors


def main() -> int:
    errors: list[str] = []

    if not ENGINE_PATH.is_file():
        errors.append(f"Missing evolution proof engine: {relative(ENGINE_PATH)}")
    else:
        returncode, stdout, stderr = run_engine()
        if returncode != 0:
            errors.append(f"Evolution proof engine failed with exit code {returncode}.")
        if stderr:
            errors.append("Evolution proof engine wrote to stderr.")
        if stdout:
            errors.extend(validate_stdout(stdout))

    report, error = load_report()
    if error:
        errors.append(error)
    elif report is not None:
        errors.extend(validate_report(report))

    if errors:
        print("TITAN ECHO evolution proof engine check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("TITAN ECHO evolution proof engine check: PASSED")
    print(f"Overall evolution score: {report.get('overall_evolution_score') if report else 0}")
    print(f"Evolution verdict: {report.get('evolution_verdict') if report else 'UNKNOWN'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
