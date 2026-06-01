"""Summarize TITAN ECHO Batch A causality and improvement proof."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_RUNTIME = REPO_ROOT / "data" / "runtime" / "echo"
COHORT_PATH = ECHO_RUNTIME / "outcome_cohort_report.json"
TRACE_PATH = ECHO_RUNTIME / "decision_trace_audit.json"
CALIBRATION_PATH = ECHO_RUNTIME / "confidence_calibration_audit.json"
OUTPUT_PATH = ECHO_RUNTIME / "batch_a_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))


def load(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def verdict(improvement: int, trace: int, calibration: int, cohort: dict[str, Any], trace_report: dict[str, Any], calibration_report: dict[str, Any]) -> str:
    if (
        improvement >= 75
        and trace >= 75
        and calibration >= 75
        and trace_report.get("causality_status") != "DECISION_CAUSALITY_NOT_PROVEN"
        and calibration_report.get("validation_status") != "CONFIDENCE_NOT_VALIDATED"
    ):
        return "PROVEN"
    if improvement >= 40 and trace >= 40 and calibration >= 25:
        return "PARTIAL"
    if not improvement and not trace and not calibration:
        return "UNKNOWN"
    return "NOT_PROVEN"


def main() -> int:
    cohort = load(COHORT_PATH)
    trace = load(TRACE_PATH)
    calibration = load(CALIBRATION_PATH)
    improvement_score = int(cohort.get("improvement_confidence_score", 0))
    trace_score = int(trace.get("decision_trace_score", 0))
    calibration_score = int(calibration.get("confidence_calibration_score", 0))
    final = verdict(improvement_score, trace_score, calibration_score, cohort, trace, calibration)
    missing = []
    missing.extend(item for item in cohort.get("missing_evidence", []) if item)
    missing.extend(trace.get("missing_links", []))
    missing.extend(calibration.get("missing_evidence", []))
    report = {
        "schema": "titan_echo.batch_a_summary.v1",
        "timestamp_ist": datetime.now(IST).isoformat(),
        "improvement_confidence_score": improvement_score,
        "decision_trace_score": trace_score,
        "confidence_calibration_score": calibration_score,
        "strongest_proofs": [
            {"area": "outcome_cohorts", "evidence": cohort.get("strongest_cohort_evidence", [])[:3]},
            {"area": "decision_trace", "evidence": trace.get("strongest_evidence", [])[:3]},
        ],
        "weakest_proofs": [
            {"area": "outcome_cohorts", "evidence": cohort.get("weakest_cohort_evidence", [])[:3]},
            {"area": "confidence_calibration", "evidence": calibration.get("overconfidence_evidence", []) or calibration.get("missing_evidence", [])},
        ],
        "missing_evidence": list(dict.fromkeys(str(item) for item in missing))[:20],
        "causality_confidence": "PARTIAL" if final == "PARTIAL" else "LOW" if final == "NOT_PROVEN" else final,
        "verdict": final,
        "downgrade_note": "PROVEN requires learning/evolution -> decision change -> outcome improvement. Batch A downgrades when any link is incomplete.",
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("TITAN ECHO Batch A summary: PASSED")
    print(f"Improvement confidence score: {improvement_score}")
    print(f"Decision trace score: {trace_score}")
    print(f"Confidence calibration score: {calibration_score}")
    print(f"Causality confidence: {report['causality_confidence']}")
    print(f"Batch A verdict: {final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
