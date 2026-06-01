"""Validate the TITAN ECHO evolution evidence audit."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = REPO_ROOT / "titan_echo" / "echo_evolution_evidence_audit.py"
OUTPUT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "evolution_evidence_audit.json"

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

REQUIRED_REPORT_FIELDS = [
    "original_evolution_score",
    "adjusted_evolution_score",
    "original_verdict",
    "adjusted_verdict",
    "over_scored_categories",
    "strongest_verified_evidence",
    "weakest_verified_evidence",
    "missing_proofs",
    "recommended_next_missions",
]

REQUIRED_CATEGORY_FIELDS = [
    "original_status",
    "original_score",
    "audited_strength",
    "adjusted_score",
    "evidence_found",
    "evidence_missing",
    "whether_state_change_is_proven",
    "whether_decision_influence_is_proven",
    "whether_outcome_improvement_is_proven",
    "audit_notes",
]


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def run_audit() -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(AUDIT_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def validate_stdout(stdout: str) -> list[str]:
    allowed = (
        "TITAN ECHO evolution evidence audit:",
        "Original evolution score:",
        "Adjusted evolution score:",
        "Original verdict:",
        "Adjusted verdict:",
        "Over-scored categories:",
    )
    errors = []
    for line in stdout.splitlines():
        if not line.startswith(allowed):
            errors.append("Evolution evidence audit printed unexpected output.")
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
        return None, "Report root must be a JSON object."
    return data, None


def validate_report(report: dict[str, Any]) -> list[str]:
    errors = []
    for field in REQUIRED_REPORT_FIELDS:
        if field not in report:
            errors.append(f"Missing report field: {field}")

    categories = report.get("categories")
    if not isinstance(categories, list):
        errors.append("categories must be a list.")
        return errors

    represented = {str(item.get("category")) for item in categories if isinstance(item, dict)}
    missing_categories = REQUIRED_CATEGORIES - represented
    if missing_categories:
        errors.append(f"Missing categories: {sorted(missing_categories)}")

    allowed_strengths = {"STRONG", "MODERATE", "WEAK", "ACTIVITY_ONLY", "MISSING"}
    for item in categories:
        if not isinstance(item, dict):
            errors.append("Category item must be an object.")
            continue
        for field in REQUIRED_CATEGORY_FIELDS:
            if field not in item:
                errors.append(f"Category {item.get('category')} missing {field}.")
        if item.get("audited_strength") not in allowed_strengths:
            errors.append(f"Category {item.get('category')} has invalid audited_strength.")

    if not isinstance(report.get("recommended_next_missions"), list):
        errors.append("recommended_next_missions must be a list.")
    return errors


def main() -> int:
    errors: list[str] = []

    if not AUDIT_PATH.is_file():
        errors.append(f"Missing audit script: {relative(AUDIT_PATH)}")
    else:
        returncode, stdout, stderr = run_audit()
        if returncode != 0:
            errors.append(f"Evolution evidence audit failed with exit code {returncode}.")
        if stderr:
            errors.append("Evolution evidence audit wrote to stderr.")
        if stdout:
            errors.extend(validate_stdout(stdout))

    report, error = load_report()
    if error:
        errors.append(error)
    elif report is not None:
        errors.extend(validate_report(report))

    if errors:
        print("TITAN ECHO evolution evidence audit check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("TITAN ECHO evolution evidence audit check: PASSED")
    print(f"Original evolution score: {report.get('original_evolution_score') if report else 0}")
    print(f"Adjusted evolution score: {report.get('adjusted_evolution_score') if report else 0}")
    print(f"Adjusted verdict: {report.get('adjusted_verdict') if report else 'UNKNOWN'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
