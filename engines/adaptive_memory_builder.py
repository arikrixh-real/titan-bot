"""
TITAN Phase 3 - Adaptive Intelligence Memory Builder
===================================================

Builds cached, explainable adaptive memory from existing journals.

Safe properties:
- Does not send Telegram alerts.
- Does not create trades or broker orders.
- Does not change existing journal/outcome files.
- Runtime scanner does not train; it only reads this cache.
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
JOURNAL_DIR = DATA_DIR / "journals"
MEMORY_DIR = DATA_DIR / "memory"
REPORTS_DIR = PROJECT_ROOT / "reports"

TRADE_JOURNAL_CSV = JOURNAL_DIR / "trade_journal.csv"
TRADE_OUTCOMES_JSONL = JOURNAL_DIR / "trade_outcomes.jsonl"
TRADE_OUTCOMES_OLD_CSV = JOURNAL_DIR / "trade_outcomes_old.csv"

ADAPTIVE_STATE_PATH = MEMORY_DIR / "adaptive_intelligence_state.json"
ADAPTIVE_REPORT_PATH = REPORTS_DIR / "adaptive_intelligence_report.txt"

STATE_VERSION = "3.0"
MIN_BUCKET_TRADES = 3
MAX_REASONABLE_ROWS = 10000


FALLBACK_STOCK_SECTORS = {
    "RELIANCE": "Energy / Telecom / Retail",
    "ONGC": "Oil & Gas",
    "COALINDIA": "Energy / Coal",
    "NTPC": "Power",
    "POWERGRID": "Power",
    "TCS": "IT",
    "INFY": "IT",
    "WIPRO": "IT",
    "HCLTECH": "IT",
    "TECHM": "IT",
    "HDFCBANK": "Banking",
    "ICICIBANK": "Banking",
    "SBIN": "Banking",
    "AXISBANK": "Banking",
    "KOTAKBANK": "Banking",
    "BAJFINANCE": "NBFC",
    "BAJAJFINSV": "Financial Services",
    "BHARTIARTL": "Telecom",
    "ADANIENT": "Conglomerate / Infrastructure",
    "ADANIPORTS": "Ports / Logistics",
    "LT": "Capital Goods / Infrastructure",
    "MARUTI": "Auto",
    "M&M": "Auto",
    "BAJAJ-AUTO": "Auto",
    "EICHERMOT": "Auto",
    "HEROMOTOCO": "Auto",
    "HINDUNILVR": "FMCG",
    "ITC": "FMCG",
    "TATACONSUM": "FMCG",
    "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG",
    "SUNPHARMA": "Pharma",
    "DRREDDY": "Pharma",
    "CIPLA": "Pharma",
    "DIVISLAB": "Pharma",
    "TATASTEEL": "Metals",
    "JSWSTEEL": "Metals",
    "HINDALCO": "Metals",
    "ULTRACEMCO": "Cement",
    "GRASIM": "Cement / Chemicals",
    "ASIANPAINT": "Paints / Consumer",
    "TITAN": "Consumer / Jewellery",
}

try:
    from intelligence.news_engine import STOCK_SECTORS as NEWS_STOCK_SECTORS
    STOCK_SECTORS = {**FALLBACK_STOCK_SECTORS, **NEWS_STOCK_SECTORS}
except Exception:
    STOCK_SECTORS = dict(FALLBACK_STOCK_SECTORS)


DEFAULT_STATE: Dict[str, Any] = {
    "version": STATE_VERSION,
    "last_updated": None,
    "total_closed_trades": 0,
    "total_wins": 0,
    "total_losses": 0,
    "bayesian_prior": {"alpha": 2.0, "beta": 2.0},
    "global_confidence": {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "posterior_win_rate": 0.5,
        "adaptive_confidence_score": 50.0,
        "sample_confidence": 0.0,
    },
    "feature_memory": {},
    "regime_memory": {},
    "sector_memory": {},
    "cluster_memory": {},
    "symbol_memory": {},
    "side_memory": {},
    "news_reaction_memory": {
        "seen_news_hashes": [],
        "symbol_sentiment": {},
        "sector_sentiment": {},
    },
    "builder_notes": [],
}


FEATURE_KEYWORDS: Dict[str, List[str]] = {
    "volume": ["volume", "vol spike", "volume spike"],
    "strength": ["strength", "relative strength", "stronger than market"],
    "compression": ["compression", "squeeze", "tight range"],
    "momentum": ["momentum", "rsi"],
    "trend": ["trend", "ema", "moving average"],
    "breakout": ["breakout", "range break", "resistance break"],
    "trap_avoidance": ["trap", "fakeout", "fake breakout"],
    "market_filter": ["market status", "market filter", "market regime", "nifty", "index"],
    "news": ["news", "event", "earnings", "result", "announcement"],
}


POSITIVE_WORDS = {
    "rise", "rises", "gain", "gains", "jump", "jumps", "surge", "surges",
    "beats", "profit", "growth", "strong", "record", "wins", "order",
    "deal", "approval", "upgrade", "expansion", "dividend",
}

NEGATIVE_WORDS = {
    "fall", "falls", "decline", "declines", "drop", "drops", "loss",
    "weak", "cuts", "slow", "miss", "downgrade", "penalty", "probe",
    "fraud", "debt", "resigns", "impact",
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _ensure_dirs() -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _read_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        return rows[-MAX_REASONABLE_ROWS:]
    except Exception:
        return []


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        return rows[-MAX_REASONABLE_ROWS:]
    except Exception:
        return []


def _symbol(value: Any) -> str:
    text = _safe_upper(value)
    return text.replace(".NS", "")


def _side(value: Any) -> str:
    side = _safe_upper(value)
    if side == "BUY":
        return "LONG"
    if side == "SELL":
        return "SHORT"
    return side if side in {"LONG", "SHORT"} else "UNKNOWN"


def _outcome(value: Any) -> Optional[str]:
    raw = _safe_upper(value)
    if raw in {"TP", "TARGET", "TARGET_HIT", "WIN", "WON", "PROFIT", "SUCCESS"}:
        return "WIN"
    if raw in {"SL", "SL_HIT", "STOPLOSS", "STOP_LOSS", "LOSS", "LOST", "FAILED"}:
        return "LOSS"
    return None


def _trade_key(row: Dict[str, Any]) -> str:
    trade_id = str(row.get("trade_id") or "").strip()
    if trade_id:
        return trade_id
    return "|".join([
        str(row.get("scan_id", "")).strip(),
        _symbol(row.get("symbol")),
        _side(row.get("side")),
        str(row.get("entry", "")).strip(),
    ])


def _journal_lookup(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        symbol = _symbol(row.get("symbol"))
        side = _side(row.get("side"))
        entry = str(row.get("entry", "")).strip()
        scan_id = str(row.get("scan_id", "")).strip()
        exact_key = "|".join([scan_id, symbol, side, entry])
        if exact_key.strip("|"):
            lookup[exact_key] = row
        trade_id = str(row.get("trade_id") or "").strip()
        if trade_id:
            lookup[trade_id] = row
    return lookup


def _find_journal_row(outcome_row: Dict[str, Any], lookup: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    key = _trade_key(outcome_row)
    if key in lookup:
        return lookup[key]
    fallback = "|".join([
        str(outcome_row.get("scan_id", "")).strip(),
        _symbol(outcome_row.get("symbol")),
        _side(outcome_row.get("side")),
        str(outcome_row.get("entry", "")).strip(),
    ])
    return lookup.get(fallback, {})


def _extract_features(reason: str, confirmations: str = "") -> List[str]:
    text = f"{reason} {confirmations}".lower()
    found = []
    for feature, words in FEATURE_KEYWORDS.items():
        if any(word in text for word in words):
            found.append(feature)
    return sorted(set(found)) or ["general"]


def _regime(market_status: Any) -> str:
    text = str(market_status or "").lower()
    if "volatile" in text:
        return "VOLATILE"
    if "sideways" in text or "range" in text:
        return "SIDEWAYS"
    if "trend" in text:
        return "TRENDING"
    if "market_ok" in text or "level 1" in text:
        return "NEUTRAL_OK"
    return "NEUTRAL"


def _sector(symbol: str) -> str:
    plain = _symbol(symbol)
    sector = STOCK_SECTORS.get(plain)
    if sector:
        return str(sector)
    return "UNKNOWN"


def _cluster_id(side: str, features: List[str], regime: str, sector: str) -> str:
    feature_part = "+".join(sorted(features[:5])) if features else "general"
    sector_part = re.sub(r"[^A-Z0-9]+", "_", str(sector).upper()).strip("_") or "UNKNOWN"
    return f"{side}|{regime}|{sector_part}|{feature_part}"


def _new_bucket() -> Dict[str, Any]:
    return {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "posterior_win_rate": 0.5,
        "sample_confidence": 0.0,
        "weight": 1.0,
    }


def _update_bucket(bucket: Dict[str, Any], outcome: str) -> Dict[str, Any]:
    bucket["trades"] = int(bucket.get("trades", 0)) + 1
    if outcome == "WIN":
        bucket["wins"] = int(bucket.get("wins", 0)) + 1
    elif outcome == "LOSS":
        bucket["losses"] = int(bucket.get("losses", 0)) + 1
    return bucket


def _finalize_bucket(bucket: Dict[str, Any], alpha: float = 2.0, beta: float = 2.0) -> Dict[str, Any]:
    trades = int(bucket.get("trades", 0) or 0)
    wins = int(bucket.get("wins", 0) or 0)
    losses = int(bucket.get("losses", 0) or 0)
    total = wins + losses
    win_rate = wins / total if total else 0.0
    posterior = (wins + alpha) / (total + alpha + beta) if total else 0.5
    sample_conf = min(1.0, trades / 30.0)
    edge = posterior - 0.5
    weight = 1.0 + (edge * 0.50 * sample_conf)

    bucket["win_rate"] = round(win_rate, 4)
    bucket["posterior_win_rate"] = round(posterior, 4)
    bucket["sample_confidence"] = round(sample_conf, 4)
    bucket["weight"] = round(_clamp(weight, 0.90, 1.10), 4)
    return bucket


def _finalize_memory(memory: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    finalized = {}
    for key, bucket in memory.items():
        finalized[key] = _finalize_bucket(bucket)
    return finalized


def _confidence_score(bucket: Dict[str, Any]) -> float:
    posterior = _safe_float(bucket.get("posterior_win_rate"), 0.5)
    sample_conf = _safe_float(bucket.get("sample_confidence"), 0.0)
    shrunk = 0.5 + ((posterior - 0.5) * sample_conf)
    return round(_clamp(shrunk * 100.0, 35.0, 65.0), 2)


def _load_news_batch() -> Dict[str, Any]:
    path = PROJECT_ROOT / "titan_brain" / "memory" / "news_batch_state.json"
    try:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _news_sentiment(title: str, summary: str = "") -> Tuple[str, int]:
    words = set(re.findall(r"[a-zA-Z]+", f"{title} {summary}".lower()))
    pos = len(words.intersection(POSITIVE_WORDS))
    neg = len(words.intersection(NEGATIVE_WORDS))
    if pos > neg:
        return "POSITIVE", pos - neg
    if neg > pos:
        return "NEGATIVE", neg - pos
    return "NEUTRAL", 0


def _build_news_memory() -> Dict[str, Any]:
    batch = _load_news_batch()
    news_items = batch.get("news", []) if isinstance(batch, dict) else []
    seen = []
    symbol_scores: Dict[str, List[float]] = defaultdict(list)
    sector_scores: Dict[str, List[float]] = defaultdict(list)

    for item in news_items[-100:]:
        if not isinstance(item, dict):
            continue
        news_hash = str(item.get("news_hash") or item.get("link") or item.get("title") or "").strip()
        if not news_hash or news_hash in seen:
            continue
        seen.append(news_hash)
        sentiment, strength = _news_sentiment(item.get("title", ""), item.get("summary", ""))
        if sentiment == "NEUTRAL" or strength <= 0:
            score = 0.0
        else:
            signed = 1.0 if sentiment == "POSITIVE" else -1.0
            score = signed * min(1.0, strength / 3.0)

        for symbol in item.get("detected_symbols", []) or []:
            symbol_scores[_symbol(symbol)].append(score)
        for sector in item.get("sectors", []) or []:
            sector_scores[str(sector)].append(score)

    def average(values: List[float]) -> Dict[str, Any]:
        if not values:
            return {"items": 0, "sentiment_score": 0.0}
        return {
            "items": len(values),
            "sentiment_score": round(_clamp(sum(values) / len(values), -1.0, 1.0), 4),
        }

    return {
        "seen_news_hashes": seen[-500:],
        "symbol_sentiment": {k: average(v) for k, v in symbol_scores.items()},
        "sector_sentiment": {k: average(v) for k, v in sector_scores.items()},
    }


def build_adaptive_memory(write_files: bool = True) -> Dict[str, Any]:
    _ensure_dirs()

    journal_rows = _read_csv(TRADE_JOURNAL_CSV)
    outcome_rows = _read_jsonl(TRADE_OUTCOMES_JSONL)
    if not outcome_rows:
        outcome_rows = _read_csv(TRADE_OUTCOMES_OLD_CSV)

    lookup = _journal_lookup(journal_rows)

    latest_by_key: Dict[str, Dict[str, Any]] = {}
    for row in outcome_rows:
        outcome = _outcome(row.get("outcome") or row.get("result") or row.get("status"))
        if outcome not in {"WIN", "LOSS"}:
            continue
        latest_by_key[_trade_key(row)] = row

    closed_rows = list(latest_by_key.values())

    state = json.loads(json.dumps(DEFAULT_STATE))
    state["last_updated"] = _now()

    feature_memory: Dict[str, Dict[str, Any]] = {}
    regime_memory: Dict[str, Dict[str, Any]] = {}
    sector_memory: Dict[str, Dict[str, Any]] = {}
    cluster_memory: Dict[str, Dict[str, Any]] = {}
    symbol_memory: Dict[str, Dict[str, Any]] = {}
    side_memory: Dict[str, Dict[str, Any]] = {}

    wins = 0
    losses = 0

    for outcome_row in closed_rows:
        outcome = _outcome(outcome_row.get("outcome") or outcome_row.get("result") or outcome_row.get("status"))
        if outcome not in {"WIN", "LOSS"}:
            continue

        wins += 1 if outcome == "WIN" else 0
        losses += 1 if outcome == "LOSS" else 0

        journal_row = _find_journal_row(outcome_row, lookup)
        symbol = _symbol(outcome_row.get("symbol") or journal_row.get("symbol"))
        side = _side(outcome_row.get("side") or journal_row.get("side"))
        reason = str(journal_row.get("reason") or outcome_row.get("reason") or outcome_row.get("result_reason") or "")
        confirmations = str(journal_row.get("confirmations") or "")
        regime = _regime(journal_row.get("market_status") or outcome_row.get("market_status"))
        sector = _sector(symbol)
        features = _extract_features(reason, confirmations)
        cluster = _cluster_id(side, features, regime, sector)

        for memory, key in [
            (regime_memory, regime),
            (sector_memory, sector),
            (cluster_memory, cluster),
            (symbol_memory, symbol),
            (side_memory, side),
        ]:
            if key not in memory:
                memory[key] = _new_bucket()
            _update_bucket(memory[key], outcome)

        for feature in features:
            if feature not in feature_memory:
                feature_memory[feature] = _new_bucket()
            _update_bucket(feature_memory[feature], outcome)

    global_bucket = _finalize_bucket({
        "trades": wins + losses,
        "wins": wins,
        "losses": losses,
    })

    state.update({
        "total_closed_trades": wins + losses,
        "total_wins": wins,
        "total_losses": losses,
        "global_confidence": {
            **global_bucket,
            "adaptive_confidence_score": _confidence_score(global_bucket),
        },
        "feature_memory": _finalize_memory(feature_memory),
        "regime_memory": _finalize_memory(regime_memory),
        "sector_memory": _finalize_memory(sector_memory),
        "cluster_memory": _finalize_memory(cluster_memory),
        "symbol_memory": _finalize_memory(symbol_memory),
        "side_memory": _finalize_memory(side_memory),
        "news_reaction_memory": _build_news_memory(),
        "builder_notes": _build_notes(wins + losses),
    })

    if write_files:
        with ADAPTIVE_STATE_PATH.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        _write_report(state)

    return state


def _top(memory: Dict[str, Any], limit: int = 10) -> List[Tuple[str, Dict[str, Any]]]:
    items = list(memory.items())
    items.sort(
        key=lambda item: (
            int(item[1].get("trades", 0)),
            float(item[1].get("posterior_win_rate", 0.5)),
        ),
        reverse=True,
    )
    return items[:limit]


def _build_notes(total_closed: int) -> List[str]:
    if total_closed < 10:
        return [
            "Learning phase active. Runtime adjustments should remain neutral until more closed trades exist."
        ]
    return [
        "Adaptive memory is available for conservative post-score ranking adjustments.",
        "All adjustments are bounded and should not hard-block any setup.",
    ]


def _write_report(state: Dict[str, Any]) -> None:
    lines = [
        "TITAN PHASE 3 ADAPTIVE INTELLIGENCE REPORT",
        "=" * 60,
        f"Updated: {state.get('last_updated')}",
        f"Closed trades: {state.get('total_closed_trades')}",
        f"Wins: {state.get('total_wins')}",
        f"Losses: {state.get('total_losses')}",
        f"Adaptive confidence: {state.get('global_confidence', {}).get('adaptive_confidence_score')}",
        "",
        "NOTES",
        "-" * 60,
    ]
    for note in state.get("builder_notes", []):
        lines.append(f"- {note}")

    sections = [
        ("FEATURE MEMORY", "feature_memory"),
        ("REGIME MEMORY", "regime_memory"),
        ("SECTOR MEMORY", "sector_memory"),
        ("PATTERN CLUSTERS", "cluster_memory"),
    ]
    for title, key in sections:
        lines.extend(["", title, "-" * 60])
        for name, bucket in _top(state.get(key, {}), 12):
            lines.append(
                f"{name}: trades={bucket.get('trades')}, wins={bucket.get('wins')}, "
                f"losses={bucket.get('losses')}, posterior={bucket.get('posterior_win_rate')}, "
                f"weight={bucket.get('weight')}"
            )

    ADAPTIVE_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def get_adaptive_state_path() -> Path:
    return ADAPTIVE_STATE_PATH


def get_adaptive_report_path() -> Path:
    return ADAPTIVE_REPORT_PATH


if __name__ == "__main__":
    result = build_adaptive_memory(write_files=True)
    print("TITAN Phase 3 adaptive memory built")
    print(f"Closed trades: {result.get('total_closed_trades')}")
    print(f"State: {ADAPTIVE_STATE_PATH}")
    print(f"Report: {ADAPTIVE_REPORT_PATH}")
