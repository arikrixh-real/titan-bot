from pathlib import Path

from consciousness_core.experience_utils import (
    is_loss,
    is_win,
    load_json,
    load_standard_reports,
    load_trade_rows,
    recent_rows,
    symbol_from_row,
)
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = Path("data") / "consciousness_core" / "daily_review.json"
REAL_MEMORY_PATH = Path("data") / "consciousness_core" / "real_experience_memory.json"


def _belief_reviews(beliefs, rows):
    confirmed = []
    contradicted = []
    losses = sum(1 for row in rows if is_loss(row))
    wins = sum(1 for row in rows if is_win(row))
    for belief in beliefs.values() if isinstance(beliefs, dict) else []:
        statement = str(belief.get("statement", "")).lower()
        item = {
            "belief_id": belief.get("belief_id"),
            "statement": belief.get("statement"),
            "confidence": belief.get("confidence"),
        }
        if "confidence" in statement and losses:
            confirmed.append(item)
        elif "choppy" in statement or "regime" in statement:
            confirmed.append(item)
        elif wins > losses and "avoid" in statement:
            contradicted.append(item)
    return confirmed[:10], contradicted[:10]


def run_daily_review_engine(output_path=OUTPUT_PATH, **_kwargs):
    rows = recent_rows(load_trade_rows(), days=7)
    reports = load_standard_reports()
    memory = load_json(REAL_MEMORY_PATH, {})
    wins = [row for row in rows if is_win(row)]
    losses = [row for row in rows if is_loss(row)]
    confirmed, contradicted = _belief_reviews(reports.get("beliefs", {}), rows)
    weak_engines = [
        item for item in memory.get("engine_reliability_memory", [])
        if item.get("reliability") == "WEAK"
    ]
    backtesting = reports.get("backtesting", {})
    confidence = reports.get("confidence", {})
    no_trade = reports.get("no_trade", {})
    news = reports.get("news", {})

    review = {
        "generated_at": now_ist(),
        "review_window": "recent_7_days_from_latest_trade",
        "trade_count": len(rows),
        "what_worked": [
            {
                "symbol": symbol_from_row(row),
                "outcome": row.get("outcome"),
                "reason": row.get("result_reason") or row.get("reason"),
            }
            for row in wins[:10]
        ],
        "what_failed": [
            {
                "symbol": symbol_from_row(row),
                "outcome": row.get("outcome"),
                "reason": row.get("result_reason") or row.get("reason"),
            }
            for row in losses[:10]
        ],
        "what_was_missing": [],
        "which_beliefs_were_confirmed": confirmed,
        "which_beliefs_were_contradicted": contradicted,
        "which_engines_were_weak": weak_engines,
        "what_to_study_next": [],
        "what_should_be_avoided_tomorrow": [],
        "what_needs_paper_testing": [],
        "source_reports": {
            "consciousness_report_seen": bool(reports.get("consciousness_report")),
            "worker_health_seen": bool(reports.get("worker_health")),
            "no_trade_warning": no_trade.get("no_trade_warning"),
            "confidence_warning": confidence.get("calibration_warning"),
            "news_warning": news.get("news_warning"),
        },
    }

    if not reports.get("worker_health"):
        review["what_was_missing"].append("worker health report is unavailable")
    if "NO_DATA" in str(backtesting) or "NO_TEST_DATA" in str(backtesting):
        review["what_was_missing"].append("backtesting validation has insufficient samples")
        review["what_to_study_next"].append("increase backtesting coverage before strategy promotion")
        review["what_needs_paper_testing"].append("strategies with no historical or out-of-sample validation")
    if confidence.get("predicted_vs_actual", {}).get("sample_size", 0) < 20:
        review["what_was_missing"].append("real confidence calibration sample size")
        review["what_to_study_next"].append("confidence reliability by score bucket")
    if no_trade.get("no_trade_warning") not in (None, "NONE"):
        review["what_should_be_avoided_tomorrow"].append("trading through no-trade warnings")
    if losses:
        review["what_should_be_avoided_tomorrow"].append("repeat of recent losing setup without fresh validation")
    if news.get("news_warning") == "REVIEW":
        review["what_to_study_next"].append("news reaction memory with real headline/outcome links")

    atomic_write_json(output_path, review)
    return review


if __name__ == "__main__":
    run_daily_review_engine()
