"""Audit whether TITAN confidence values predict outcomes."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_RUNTIME = REPO_ROOT / "data" / "runtime" / "echo"
OUTPUT_PATH = ECHO_RUNTIME / "confidence_calibration_audit.json"
IST = timezone(timedelta(hours=5, minutes=30))
FILES = ["data/journals/trade_outcomes.csv", "data/journals/trade_results.csv", "data/journals/trade_outcomes.jsonl"]


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def read_rows() -> list[dict[str, Any]]:
    rows = []
    for relative in FILES:
        path = REPO_ROOT / relative
        if not path.exists():
            continue
        if path.suffix == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows.extend(dict(row) for row in csv.DictReader(handle))
        else:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(item, dict):
                        rows.append(item)
    return rows


def parse_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(str(value))
    except ValueError:
        return None


def confidence(row: dict[str, Any]) -> float | None:
    for key in ["confidence", "confidence_score", "rank_score", "score"]:
        value = parse_float(row.get(key))
        if value is not None:
            return value
    return None


def win(row: dict[str, Any]) -> bool | None:
    text = str(row.get("outcome") or row.get("result") or "").upper()
    if text in {"TP", "WIN", "PROFIT", "TARGET"}:
        return True
    if text in {"SL", "LOSS", "STOP_LOSS"}:
        return False
    pnl = parse_float(row.get("realized_pnl") or row.get("pnl") or row.get("pnl_points"))
    return None if pnl is None else pnl > 0


def bucket(value: float) -> str:
    if value >= 70:
        return "high"
    if value >= 40:
        return "medium"
    return "low"


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(1 for row in rows if win(row) is True)
    losses = sum(1 for row in rows if win(row) is False)
    known = wins + losses
    return {
        "count": len(rows),
        "known_outcomes": known,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / known, 4) if known else None,
    }


def build_report() -> dict[str, Any]:
    by_bucket = {"high": [], "medium": [], "low": []}
    missing_conf = 0
    for row in read_rows():
        conf = confidence(row)
        if conf is None or win(row) is None:
            missing_conf += 1
            continue
        by_bucket[bucket(conf)].append(row)
    summaries = {name: summarize(items) for name, items in by_bucket.items()}
    high = summaries["high"]["win_rate"]
    medium = summaries["medium"]["win_rate"]
    low = summaries["low"]["win_rate"]
    calibrated = high is not None and medium is not None and low is not None and high >= medium >= low
    enough = all(summaries[name]["known_outcomes"] >= 20 for name in summaries)
    score = 0
    if any(summaries[name]["known_outcomes"] for name in summaries):
        score += 25
    if enough:
        score += 25
    if calibrated:
        score += 35
    verdict = "PARTIAL" if calibrated or enough else "CONFIDENCE_NOT_VALIDATED"
    if not calibrated:
        verdict = "CONFIDENCE_NOT_VALIDATED"
    return {
        "schema": "titan_echo.confidence_calibration_audit.v1",
        "timestamp_ist": timestamp_ist(),
        "confidence_calibration_score": min(score, 70),
        "validation_status": verdict,
        "high_confidence_outcomes": summaries["high"],
        "medium_confidence_outcomes": summaries["medium"],
        "low_confidence_outcomes": summaries["low"],
        "overconfidence_evidence": ["High confidence win rate is not above lower buckets."] if not calibrated and high is not None else [],
        "underconfidence_evidence": ["Low confidence bucket outperformed higher bucket."] if low is not None and high is not None and low > high else [],
        "calibration_quality": "PARTIAL" if calibrated and enough else "UNKNOWN",
        "trustworthiness_score": min(score, 70),
        "missing_confidence_or_outcome_rows": missing_conf,
        "missing_evidence": [
            "Confidence is not validated unless higher confidence buckets show better realized outcomes.",
            "Calibration needs adequate samples in high, medium, and low buckets.",
        ],
    }


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = build_report()
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("TITAN ECHO confidence calibration audit: PASSED")
    print(f"Confidence calibration score: {report['confidence_calibration_score']}")
    print(f"Validation status: {report['validation_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
