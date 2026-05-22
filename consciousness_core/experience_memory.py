import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from consciousness_core.experience_utils import safe_float
from consciousness_core.state import atomic_write_json, now_ist


MEMORY_PATH = Path("data") / "consciousness_core" / "experience_memory.json"


def _load_json(path, default):
    try:
        with Path(path).open("r", encoding="utf-8") as payload_file:
            payload = json.load(payload_file)
        return payload if isinstance(payload, type(default)) else default
    except Exception:
        return default


def _read_csv_rows(path, limit=500):
    try:
        with Path(path).open("r", encoding="utf-8", newline="") as csv_file:
            rows = list(csv.DictReader(csv_file))
        return rows[-limit:]
    except Exception:
        return []


def _walk_json_files(patterns):
    for pattern in patterns:
        for path in Path(".").glob(pattern):
            if path.is_file():
                yield path, _load_json(path, {})


def _market_regime(row):
    raw = row.get("market_status") or row.get("regime") or ""
    if isinstance(raw, str) and raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            return parsed.get("regime") or parsed.get("status") or "UNKNOWN"
        except Exception:
            return "UNKNOWN"
    return raw or "UNKNOWN"


def _trade_patterns(rows):
    failures = Counter()
    successes = Counter()
    stock_lessons = defaultdict(lambda: {"wins": 0, "losses": 0, "setups": Counter()})
    regime_lessons = defaultdict(lambda: {"wins": 0, "losses": 0})
    for row in rows:
        symbol = row.get("symbol") or row.get("tradingsymbol") or "UNKNOWN"
        side = row.get("side") or row.get("direction") or "UNKNOWN"
        setup = row.get("setup") or row.get("result_reason") or row.get("outcome") or "UNKNOWN"
        outcome = (row.get("outcome") or row.get("result") or "").upper()
        pnl = safe_float(row.get("realized_pnl") or row.get("pnl_points"), 0.0)
        regime = _market_regime(row)
        won = outcome in {"TARGET", "TP", "WIN", "PROFIT"} or pnl > 0
        lost = outcome in {"SL", "LOSS", "STOP_LOSS"} or pnl < 0
        if won:
            successes[f"{symbol}|{side}|{setup}"] += 1
            stock_lessons[symbol]["wins"] += 1
            regime_lessons[regime]["wins"] += 1
        if lost:
            failures[f"{symbol}|{side}|{setup}"] += 1
            stock_lessons[symbol]["losses"] += 1
            regime_lessons[regime]["losses"] += 1
        stock_lessons[symbol]["setups"][setup] += 1
    return failures, successes, stock_lessons, regime_lessons


def _engine_strengths():
    weak = Counter()
    strong = Counter()
    for _, payload in _walk_json_files(
        [
            "data/research/*backtest*.json",
            "data/confidence_calibration/*.json",
            "data/no_trade/*.json",
            "data/runtime/*health*.json",
            "data/runtime/*status*.json",
        ]
    ):
        text = json.dumps(payload, default=str).lower()
        if any(term in text for term in ("no_data", "missing", "error", "failed", "insufficient")):
            weak.update(["evidence_pipeline"])
        if any(term in text for term in ("active", "ok", "healthy", "available")):
            strong.update(["runtime_monitoring"])
        if "calibrated_confidence_score" in text and "26.5" in text:
            weak.update(["confidence_calibration"])
        if "backtest" in text and "sample_size" in text and "0" in text:
            weak.update(["backtesting"])
    return weak, strong


def update_experience_memory(output_path=MEMORY_PATH):
    trade_rows = []
    for path in (
        Path("data/journals/trade_outcomes.csv"),
        Path("data/journals/trade_journal.csv"),
        Path("data/trade_journal.csv"),
    ):
        trade_rows.extend(_read_csv_rows(path))
    journal_json = _load_json(Path("journal") / "trade_journal.json", [])
    if isinstance(journal_json, list):
        trade_rows.extend(item for item in journal_json if isinstance(item, dict))

    failures, successes, stock_lessons, regime_lessons = _trade_patterns(trade_rows)
    weak_engines, strong_engines = _engine_strengths()
    memory = {
        "generated_at": now_ist(),
        "source_trade_rows": len(trade_rows),
        "repeated_failure_patterns": [
            {"pattern": pattern, "count": count}
            for pattern, count in failures.most_common(20)
            if count >= 1
        ],
        "repeated_success_patterns": [
            {"pattern": pattern, "count": count}
            for pattern, count in successes.most_common(20)
            if count >= 1
        ],
        "weak_engines": [{"engine": engine, "signals": count} for engine, count in weak_engines.most_common()],
        "strong_engines": [{"engine": engine, "signals": count} for engine, count in strong_engines.most_common()],
        "regime_lessons": [
            {"regime": regime, "wins": data["wins"], "losses": data["losses"]}
            for regime, data in sorted(regime_lessons.items())
        ],
        "stock_setup_lessons": [
            {
                "symbol": symbol,
                "wins": data["wins"],
                "losses": data["losses"],
                "common_setups": [{"setup": setup, "count": count} for setup, count in data["setups"].most_common(5)],
            }
            for symbol, data in sorted(stock_lessons.items())
        ][:100],
    }
    atomic_write_json(output_path, memory)
    return memory
