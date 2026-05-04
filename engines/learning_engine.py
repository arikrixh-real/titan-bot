"""
TITAN - Learning Engine
-----------------------
Analyzes trade journal + outcome results.

Input:
- data/journals/trade_journal.csv
- data/journals/trade_outcomes.csv

Output:
- data/learning/learning_report.json
- data/learning/learning_summary.txt

This file does NOT:
- Send Telegram alerts
- Change scan/filter logic
- Change daily alert cap

Purpose:
- Understand what works
- Track win/loss stats
- Prepare Titan for evolution engine
"""

import csv
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict


IST = ZoneInfo("Asia/Kolkata")

JOURNAL_FILE = Path("data/journals/trade_journal.csv")
OUTCOME_FILE = Path("data/journals/trade_outcomes.csv")

LEARNING_DIR = Path("data/learning")
REPORT_JSON = LEARNING_DIR / "learning_report.json"
SUMMARY_TXT = LEARNING_DIR / "learning_summary.txt"


def safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def read_csv(path):
    if not path.exists():
        return []

    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def make_key(row):
    return (
        str(row.get("scan_id", "")),
        str(row.get("symbol", "")),
        str(row.get("side", "")),
        str(row.get("entry", "")),
    )


def calculate_stats(rows):
    total = len(rows)

    target_hits = [r for r in rows if r.get("outcome") == "TARGET_HIT"]
    sl_hits = [r for r in rows if r.get("outcome") == "SL_HIT"]
    open_trades = [r for r in rows if r.get("outcome") == "OPEN"]

    closed = target_hits + sl_hits
    closed_count = len(closed)

    win_rate = 0.0
    if closed_count > 0:
        win_rate = round((len(target_hits) / closed_count) * 100, 2)

    avg_score = round(
        sum(safe_float(r.get("score")) for r in rows) / total,
        2,
    ) if total else 0.0

    avg_rr = round(
        sum(safe_float(r.get("rr")) for r in rows) / total,
        2,
    ) if total else 0.0

    avg_rank_score = round(
        sum(safe_float(r.get("rank_score")) for r in rows) / total,
        2,
    ) if total else 0.0

    return {
        "total_tracked": total,
        "closed_trades": closed_count,
        "target_hits": len(target_hits),
        "sl_hits": len(sl_hits),
        "open_trades": len(open_trades),
        "win_rate_closed_percent": win_rate,
        "avg_score": avg_score,
        "avg_rr": avg_rr,
        "avg_rank_score": avg_rank_score,
    }


def group_performance(rows, group_key):
    grouped = defaultdict(list)

    for row in rows:
        key = row.get(group_key, "UNKNOWN") or "UNKNOWN"
        grouped[key].append(row)

    result = {}

    for key, items in grouped.items():
        stats = calculate_stats(items)
        result[key] = stats

    return result


def top_symbols(rows, limit=10):
    grouped = group_performance(rows, "symbol")

    sortable = []

    for symbol, stats in grouped.items():
        sortable.append({
            "symbol": symbol,
            **stats,
        })

    sortable.sort(
        key=lambda x: (
            x["target_hits"],
            x["win_rate_closed_percent"],
            x["closed_trades"],
            x["total_tracked"],
        ),
        reverse=True,
    )

    return sortable[:limit]


def analyze_learning():
    LEARNING_DIR.mkdir(parents=True, exist_ok=True)

    journal_rows = read_csv(JOURNAL_FILE)
    outcome_rows = read_csv(OUTCOME_FILE)

    if not journal_rows:
        print("⚠️ No trade journal data found.")
        return None

    if not outcome_rows:
        print("⚠️ No outcome data found. Run outcome tracker first.")
        return None

    # Use latest outcome per trade key
    latest_by_key = {}

    for row in outcome_rows:
        latest_by_key[make_key(row)] = row

    latest_outcomes = list(latest_by_key.values())

    all_stats = calculate_stats(latest_outcomes)
    side_stats = group_performance(latest_outcomes, "side")
    alert_stats = group_performance(latest_outcomes, "alert_sent")
    symbol_leaders = top_symbols(latest_outcomes, limit=10)

    report = {
        "generated_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
        "summary": all_stats,
        "by_side": side_stats,
        "by_alert_sent": alert_stats,
        "top_symbols": symbol_leaders,
        "learning_notes": build_learning_notes(all_stats, side_stats, alert_stats),
    }

    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    write_summary(report)

    print("🧠 Learning Engine Updated")
    print(f"📊 Total tracked: {all_stats['total_tracked']}")
    print(f"✅ Target hits: {all_stats['target_hits']}")
    print(f"❌ SL hits: {all_stats['sl_hits']}")
    print(f"⏳ Open trades: {all_stats['open_trades']}")
    print(f"🏆 Win rate closed: {all_stats['win_rate_closed_percent']}%")
    print(f"📁 Report saved: {REPORT_JSON}")

    return report


def build_learning_notes(all_stats, side_stats, alert_stats):
    notes = []

    closed = all_stats.get("closed_trades", 0)

    if closed == 0:
        notes.append(
            "Not enough closed trades yet. Titan should keep collecting outcome data before changing strategy."
        )
    else:
        win_rate = all_stats.get("win_rate_closed_percent", 0)

        if win_rate >= 60:
            notes.append("Closed-trade win rate is strong. Current filters may be working well.")
        elif win_rate >= 45:
            notes.append("Closed-trade win rate is moderate. Continue collecting data before major changes.")
        else:
            notes.append("Closed-trade win rate is weak. Future evolution should tighten ranking/filter rules.")

    long_stats = side_stats.get("LONG", {})
    short_stats = side_stats.get("SHORT", {})

    if long_stats and short_stats:
        long_wr = long_stats.get("win_rate_closed_percent", 0)
        short_wr = short_stats.get("win_rate_closed_percent", 0)

        if long_wr > short_wr:
            notes.append("LONG setups are currently performing better than SHORT setups.")
        elif short_wr > long_wr:
            notes.append("SHORT setups are currently performing better than LONG setups.")
        else:
            notes.append("LONG and SHORT setups are performing similarly so far.")

    alerted_true = alert_stats.get("True", {})
    alerted_false = alert_stats.get("False", {})

    if alerted_true and alerted_false:
        alerted_wr = alerted_true.get("win_rate_closed_percent", 0)
        non_alerted_wr = alerted_false.get("win_rate_closed_percent", 0)

        if alerted_wr > non_alerted_wr:
            notes.append("Top 3 alerted setups are outperforming non-alerted setups.")
        elif non_alerted_wr > alerted_wr:
            notes.append("Non-alerted setups are outperforming alerted setups. Ranking may need improvement later.")
        else:
            notes.append("Alerted and non-alerted setups are performing similarly so far.")

    return notes


def write_summary(report):
    summary = report["summary"]
    notes = report["learning_notes"]

    lines = []
    lines.append("TITAN LEARNING SUMMARY")
    lines.append("=" * 30)
    lines.append(f"Generated At: {report['generated_at']}")
    lines.append("")
    lines.append(f"Total Tracked: {summary['total_tracked']}")
    lines.append(f"Closed Trades: {summary['closed_trades']}")
    lines.append(f"Target Hits: {summary['target_hits']}")
    lines.append(f"SL Hits: {summary['sl_hits']}")
    lines.append(f"Open Trades: {summary['open_trades']}")
    lines.append(f"Win Rate Closed: {summary['win_rate_closed_percent']}%")
    lines.append(f"Average Score: {summary['avg_score']}")
    lines.append(f"Average RR: {summary['avg_rr']}")
    lines.append(f"Average Rank Score: {summary['avg_rank_score']}")
    lines.append("")
    lines.append("Learning Notes:")
    for note in notes:
        lines.append(f"- {note}")

    lines.append("")
    lines.append("Top Symbols:")
    for item in report["top_symbols"]:
        lines.append(
            f"- {item['symbol']}: tracked={item['total_tracked']}, "
            f"closed={item['closed_trades']}, wins={item['target_hits']}, "
            f"losses={item['sl_hits']}, win_rate={item['win_rate_closed_percent']}%"
        )

    with open(SUMMARY_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    analyze_learning()