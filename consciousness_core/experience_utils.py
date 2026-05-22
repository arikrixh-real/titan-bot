import csv
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path


TRADE_PATHS = (
    Path("data") / "journals" / "trade_outcomes.csv",
    Path("data") / "journals" / "trade_journal.csv",
    Path("data") / "trade_journal.csv",
)


def load_json(path, default):
    try:
        with Path(path).open("r", encoding="utf-8") as payload_file:
            payload = json.load(payload_file)
        return payload if isinstance(payload, type(default)) else default
    except Exception:
        return default


def read_csv_rows(path, limit=2000):
    try:
        with Path(path).open("r", encoding="utf-8", newline="") as csv_file:
            rows = list(csv.DictReader(csv_file))
        return rows[-limit:]
    except Exception:
        return []


def load_trade_rows(limit=4000):
    rows = []
    for path in TRADE_PATHS:
        rows.extend(read_csv_rows(path, limit=limit))
    return rows


def safe_float(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            cleaned = value.strip().upper()
            if cleaned in {"TP", "SL", "WIN", "LOSS", "OPEN", "CLOSED", "NONE", ""}:
                return default
        return float(value)
    except Exception:
        return default


def parse_float(value, default=0.0):
    return safe_float(value, default)


def parse_market_status(row):
    raw = row.get("market_status") or row.get("regime") or row.get("reinforcement_regime_key") or ""
    if not isinstance(raw, str):
        return {}
    text = raw.strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {"raw": text}
    except Exception:
        return {"raw": text}


def regime_from_row(row):
    market = parse_market_status(row)
    return (
        market.get("regime")
        or market.get("status")
        or row.get("regime")
        or row.get("reinforcement_regime_key")
        or "UNKNOWN"
    )


def symbol_from_row(row):
    return (row.get("symbol") or row.get("tradingsymbol") or "UNKNOWN").replace(".NS", "")


def setup_from_row(row):
    confirmations = row.get("confirmations") or row.get("reason") or row.get("result_reason") or ""
    if "Breakout: OK" in confirmations:
        return "breakout"
    if "Trend:" in confirmations and "Momentum: OK" in confirmations:
        return "trend_continuation"
    if "gap" in confirmations.lower():
        return "gap"
    return row.get("setup") or row.get("strategy") or row.get("side") or "UNKNOWN"


def is_win(row):
    outcome = (row.get("outcome") or row.get("result") or "").upper()
    return outcome in {"TARGET", "TP", "WIN", "PROFIT"} or parse_float(row.get("realized_pnl") or row.get("pnl_points")) > 0


def is_loss(row):
    outcome = (row.get("outcome") or row.get("result") or "").upper()
    return outcome in {"SL", "LOSS", "STOP_LOSS"} or parse_float(row.get("realized_pnl") or row.get("pnl_points")) < 0


def row_time(row):
    raw = row.get("closed_at") or row.get("opened_at") or row.get("timestamp") or ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(raw)[:19], fmt)
        except ValueError:
            pass
    return None


def recent_rows(rows, days=7):
    dated = [(row_time(row), row) for row in rows]
    dated = [(stamp, row) for stamp, row in dated if stamp is not None]
    if not dated:
        return rows[-100:]
    latest = max(stamp for stamp, _ in dated)
    cutoff = latest - timedelta(days=days)
    return [row for stamp, row in dated if stamp >= cutoff]


def common(counter, limit=10):
    return [{"name": name, "count": count} for name, count in Counter(counter).most_common(limit)]


def report_paths():
    return {
        "backtesting": Path("data") / "research" / "backtesting_validation_report.json",
        "confidence": Path("data") / "confidence_calibration" / "latest_confidence_calibration_report.json",
        "no_trade": Path("data") / "no_trade" / "latest_no_trade_intelligence_report.json",
        "news": Path("data") / "news_intelligence" / "latest_news_intelligence_2_report.json",
        "beliefs": Path("data") / "consciousness_core" / "beliefs.json",
        "proposals": Path("data") / "consciousness_core" / "improvement_queue.json",
        "consciousness_report": Path("data") / "consciousness_core" / "latest_consciousness_report.json",
        "worker_health": Path("data") / "runtime" / "worker_health.json",
    }


def load_standard_reports():
    paths = report_paths()
    return {
        name: load_json(path, {} if name not in {"proposals"} else [])
        for name, path in paths.items()
    }


def text_contains(payload, terms):
    text = json.dumps(payload, default=str).lower()
    return any(term in text for term in terms)
