"""Checker for the final lineage truth audit reports."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


AUDIT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "final_lineage_truth_audit.json"
SUMMARY_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "final_lineage_truth_summary.json"
REQUIRED_STAGES = [
    "setup",
    "decision",
    "trace",
    "trade",
    "outcome",
    "learning",
    "evolution",
]
REQUIRED_SCORES = [
    "lineage_completeness_score",
    "traceability_score",
    "learning_linkage_score",
    "evolution_linkage_score",
    "future_adoption_score",
]
REQUIRED_STATUS_KEYS = [
    "contract_complete",
    "writer_adoption_complete",
    "future_lineage_ready",
    "current_runtime_proven",
    "legacy_data_limitation",
]


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def score_ok(value: Any) -> bool:
    return isinstance(value, (int, float)) and 0.0 <= float(value) <= 1.0


def build_check() -> dict[str, Any]:
    audit = read_json(AUDIT_PATH)
    summary = read_json(SUMMARY_PATH)
    failures: list[str] = []

    if not audit:
        failures.append("final audit report missing or unreadable")
    if not summary:
        failures.append("final summary report missing or unreadable")

    coverage = audit.get("coverage", {}) if isinstance(audit.get("coverage"), dict) else {}
    missing_stages = [stage for stage in REQUIRED_STAGES if stage not in coverage]
    if missing_stages:
        failures.append(f"missing stage coverage: {', '.join(missing_stages)}")

    scores = audit.get("scores", {}) if isinstance(audit.get("scores"), dict) else {}
    bad_scores = [key for key in REQUIRED_SCORES if not score_ok(scores.get(key))]
    if bad_scores:
        failures.append(f"missing or invalid scores: {', '.join(bad_scores)}")

    status = audit.get("LINEAGE_TRUTH_STATUS", {})
    if not isinstance(status, dict):
        failures.append("LINEAGE_TRUTH_STATUS missing")
        status = {}
    missing_status = [key for key in REQUIRED_STATUS_KEYS if key not in status]
    if missing_status:
        failures.append(f"missing LINEAGE_TRUTH_STATUS keys: {', '.join(missing_status)}")

    orphans = audit.get("orphans_and_duplicates", {})
    if not isinstance(orphans, dict):
        failures.append("orphans_and_duplicates missing")
        orphans = {}
    for key in ("legacy_orphans", "current_orphans", "orphan_count", "duplicate_count", "ambiguous_link_count"):
        if not isinstance(orphans.get(key), int) or orphans.get(key, 0) < 0:
            failures.append(f"invalid orphan/duplicate metric: {key}")

    if audit.get("final_verdict") not in ("BROKEN", "PARTIAL", "READY", "FUTURE_READY"):
        failures.append("invalid final verdict")
    recommendations = audit.get("recommendations", {})
    if not isinstance(recommendations, dict):
        failures.append("recommendations missing")
        recommendations = {}
    if recommendations.get("outcome_tracking_truth_upgrade_status") not in ("COMPLETE", "NOT_COMPLETE"):
        failures.append("invalid Outcome Tracking Truth Upgrade status")
    if not recommendations.get("next_recommended_titan_project"):
        failures.append("missing next recommended TITAN project")

    if summary.get("final_verdict") != audit.get("final_verdict"):
        failures.append("summary final verdict does not match audit")
    if summary.get("LINEAGE_TRUTH_STATUS") != audit.get("LINEAGE_TRUTH_STATUS"):
        failures.append("summary lineage truth status does not match audit")
    if audit.get("runtime_behavior_modified") is not False:
        failures.append("audit claims runtime behavior was modified")
    if audit.get("protected_systems_modified") not in ([], None):
        failures.append("protected system modification recorded")

    return {
        "status": "PASS" if not failures else "FAIL",
        "audit_report_exists": AUDIT_PATH.exists(),
        "summary_report_exists": SUMMARY_PATH.exists(),
        "coverage_stages_present": not missing_stages,
        "scores_present": not bad_scores,
        "lineage_truth_status_present": not missing_status,
        "runtime_behavior_modified": audit.get("runtime_behavior_modified"),
        "protected_systems_modified": audit.get("protected_systems_modified"),
        "final_verdict": audit.get("final_verdict"),
        "outcome_tracking_truth_upgrade_status": recommendations.get("outcome_tracking_truth_upgrade_status"),
        "failures": failures,
    }


def main() -> None:
    report = build_check()
    print("Final lineage truth audit check complete.")
    print(f"status={report['status']}")
    print(f"audit_report_exists={report['audit_report_exists']}")
    print(f"summary_report_exists={report['summary_report_exists']}")
    print(f"coverage_stages_present={report['coverage_stages_present']}")
    print(f"scores_present={report['scores_present']}")
    print(f"lineage_truth_status_present={report['lineage_truth_status_present']}")
    print(f"runtime_behavior_modified={report['runtime_behavior_modified']}")
    print(f"protected_systems_modified={report['protected_systems_modified']}")
    print(f"final_verdict={report['final_verdict']}")
    print(f"outcome_tracking_truth_upgrade_status={report['outcome_tracking_truth_upgrade_status']}")
    if report["failures"]:
        print("failures=" + "; ".join(report["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
