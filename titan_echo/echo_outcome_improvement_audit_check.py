"""Validate the TITAN ECHO outcome improvement audit."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = REPO_ROOT / "titan_echo" / "echo_outcome_improvement_audit.py"
OUTPUT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "outcome_improvement_audit.json"

REQUIRED_CATEGORIES = {
    "closed_outcome_count",
    "win_loss_evidence",
    "before_after_performance_evidence",
    "learning_change_evidence",
    "evolution_change_evidence",
    "strategy_weight_change_evidence",
    "confidence_change_evidence",
    "outcome_feedback_usage",
    "measurable_improvement",
    "sample_size_quality",
}

REQUIRED_REPORT_FIELDS = [
    "outcome_improvement_score",
    "verdict",
    "closed_outcome_count",
    "strongest_evidence",
    "weakest_evidence",
    "missing_proofs",
    "sample_size_warning",
    "recommended_next_missions",
]

REQUIRED_CATEGORY_FIELDS = [
    "status",
    "score",
    "evidence_found",
    "evidence_missing",
    "limitation",
    "recommended_next_step",
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
        "TITAN ECHO outcome improvement audit:",
        "Outcome improvement score:",
        "Verdict:",
        "Closed outcome count:",
        "Sample size warning:",
    )
    errors = []
    for line in stdout.splitlines():
        if not line.startswith(allowed):
            errors.append("Outcome improvement audit printed unexpected output.")
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

    for item in categories:
        if not isinstance(item, dict):
            errors.append("Category item must be an object.")
            continue
        for field in REQUIRED_CATEGORY_FIELDS:
            if field not in item:
                errors.append(f"Category {item.get('category')} missing {field}.")

    if report.get("verdict") not in {
        "IMPROVEMENT_PROVEN",
        "PARTIAL_IMPROVEMENT",
        "ACTIVITY_ONLY",
        "NOT_PROVEN",
        "UNKNOWN",
    }:
        errors.append("Invalid verdict.")
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
            errors.append(f"Outcome improvement audit failed with exit code {returncode}.")
        if stderr:
            errors.append("Outcome improvement audit wrote to stderr.")
        if stdout:
            errors.extend(validate_stdout(stdout))

    report, error = load_report()
    if error:
        errors.append(error)
    elif report is not None:
        errors.extend(validate_report(report))

    if errors:
        print("TITAN ECHO outcome improvement audit check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("TITAN ECHO outcome improvement audit check: PASSED")
    print(f"Outcome improvement score: {report.get('outcome_improvement_score') if report else 0}")
    print(f"Verdict: {report.get('verdict') if report else 'UNKNOWN'}")
    print(f"Closed outcome count: {report.get('closed_outcome_count') if report else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
