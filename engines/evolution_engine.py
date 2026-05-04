"""
TITAN Evolution Engine
======================

Purpose:
- Learns from completed trade outcomes.
- Auto-improves scoring, ranking, and filtering weights.
- Does NOT send Telegram alerts.
- Does NOT change the 3 alerts/day cap.
- Does NOT modify existing journal/outcome files.
- Safe to run every 5 minutes after Outcome Tracker.

Expected flow:
Scan -> Journal -> Outcome -> Learning -> Evolution

Main public functions:
- run_evolution_engine()
- get_evolution_state()
- apply_evolution_score(symbol, base_score, setup_data)

This file is defensive:
It works even if some CSV columns are missing.
It creates required folders/files automatically.
"""

from __future__ import annotations

import csv
import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# =========================
# PATH CONFIG
# =========================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
MEMORY_DIR = DATA_DIR / "memory"
REPORTS_DIR = PROJECT_ROOT / "reports"

TRADE_JOURNAL_PATH = DATA_DIR / "trade_journal.csv"
SCAN_JOURNAL_PATH = DATA_DIR / "scan_journal.csv"

EVOLUTION_STATE_PATH = MEMORY_DIR / "evolution_state.json"
EVOLUTION_REPORT_PATH = REPORTS_DIR / "evolution_report.txt"

MIN_CLOSED_TRADES_TO_EVOLVE = 5

MAX_WEIGHT = 1.35
MIN_WEIGHT = 0.70

DEFAULT_STATE: Dict[str, Any] = {
    "version": "1.0",
    "last_updated": None,
    "total_closed_trades": 0,
    "total_wins": 0,
    "total_losses": 0,
    "win_rate": 0.0,
    "avg_rr": 0.0,
    "avg_score_winners": 0.0,
    "avg_score_losers": 0.0,
    "score_boost": 1.0,
    "filter_strictness": 1.0,
    "ranking_confidence": 1.0,
    "symbol_memory": {},
    "side_memory": {
        "LONG": {"trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "weight": 1.0},
        "SHORT": {"trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "weight": 1.0},
    },
    "reason_memory": {},
    "evolution_notes": [],
}


# =========================
# BASIC UTILS
# =========================

def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        text = str(value).strip()
        if text == "":
            return default
        return float(text)
    except Exception:
        return default


def _safe_upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _ensure_dirs() -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if not path.exists():
            return json.loads(json.dumps(default))
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        merged = json.loads(json.dumps(default))
        merged.update(data)
        return merged
    except Exception:
        return json.loads(json.dumps(default))


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    _ensure_dirs()
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _read_csv_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(dict(row))
    except Exception:
        return []

    return rows


# =========================
# OUTCOME DETECTION
# =========================

def _get_symbol(row: Dict[str, Any]) -> str:
    for key in ["symbol", "stock", "ticker", "Stock", "SYMBOL"]:
        if row.get(key):
            return str(row.get(key)).strip().upper()
    return "UNKNOWN"


def _get_side(row: Dict[str, Any]) -> str:
    for key in ["side", "direction", "trade_side", "Side", "SIDE"]:
        val = _safe_upper(row.get(key))
        if val in {"LONG", "BUY"}:
            return "LONG"
        if val in {"SHORT", "SELL"}:
            return "SHORT"
    return "LONG"


def _get_score(row: Dict[str, Any]) -> float:
    for key in ["score", "final_score", "signal_score", "setup_score", "Score", "SCORE"]:
        if key in row:
            return _safe_float(row.get(key), 0.0)
    return 0.0


def _get_rr(row: Dict[str, Any]) -> float:
    for key in ["rr", "risk_reward", "risk_reward_ratio", "RR", "RiskReward"]:
        if key in row:
            return _safe_float(row.get(key), 0.0)
    return 0.0


def _get_reason(row: Dict[str, Any]) -> str:
    for key in ["reason", "setup_reason", "Reason", "REASON"]:
        if row.get(key):
            return str(row.get(key)).strip()
    return ""


def _get_outcome(row: Dict[str, Any]) -> Optional[str]:
    """
    Returns:
    - WIN
    - LOSS
    - None for open/pending/unknown trades
    """

    possible_keys = [
        "outcome",
        "result",
        "status",
        "trade_result",
        "Outcome",
        "Result",
        "STATUS",
    ]

    raw = ""
    for key in possible_keys:
        if row.get(key):
            raw = _safe_upper(row.get(key))
            break

    if raw in {"WIN", "WON", "TP", "TARGET", "TARGET_HIT", "T1", "T2", "PROFIT", "SUCCESS"}:
        return "WIN"

    if raw in {"LOSS", "LOST", "SL", "STOPLOSS", "STOP_LOSS", "SL_HIT", "FAILED"}:
        return "LOSS"

    return None


def _closed_trades_from_journal() -> List[Dict[str, Any]]:
    """
    Reads trade_journal first.
    If no closed trades found there, tries scan_journal as fallback.
    """

    rows = _read_csv_rows(TRADE_JOURNAL_PATH)
    closed = [r for r in rows if _get_outcome(r) in {"WIN", "LOSS"}]

    if closed:
        return closed

    fallback_rows = _read_csv_rows(SCAN_JOURNAL_PATH)
    return [r for r in fallback_rows if _get_outcome(r) in {"WIN", "LOSS"}]


# =========================
# LEARNING CALCULATIONS
# =========================

def _calc_weight(win_rate: float, trades: int) -> float:
    """
    Conservative auto-weighting.

    Small sample = smaller adjustment.
    Bigger sample = stronger adjustment.
    """

    if trades <= 0:
        return 1.0

    confidence = min(1.0, trades / 30.0)
    edge = win_rate - 0.50
    raw_weight = 1.0 + (edge * 0.70 * confidence)
    return round(_clamp(raw_weight, MIN_WEIGHT, MAX_WEIGHT), 4)


def _extract_reason_tags(reason: str) -> List[str]:
    """
    Converts reason text into stable learning tags.
    This avoids overfitting to the full sentence.
    """

    reason_l = reason.lower()
    tags = []

    keywords = {
        "breakout": ["breakout", "resistance break", "range break"],
        "volume": ["volume", "vol spike", "volume spike"],
        "momentum": ["momentum", "rsi", "strength"],
        "trend": ["trend", "ema", "moving average"],
        "relative_strength": ["relative strength", "rs", "stronger than market"],
        "trap_avoidance": ["trap", "fakeout", "fake breakout"],
        "compression": ["compression", "squeeze", "tight range"],
        "news": ["news", "event", "result", "earnings", "announcement"],
        "market_regime": ["market regime", "nifty", "index", "market filter"],
    }

    for tag, words in keywords.items():
        if any(w in reason_l for w in words):
            tags.append(tag)

    return tags or ["general"]


def _build_memory_bucket() -> Dict[str, Any]:
    return {"trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "weight": 1.0}


def _update_bucket(bucket: Dict[str, Any], outcome: str) -> Dict[str, Any]:
    bucket["trades"] = int(bucket.get("trades", 0)) + 1

    if outcome == "WIN":
        bucket["wins"] = int(bucket.get("wins", 0)) + 1
    elif outcome == "LOSS":
        bucket["losses"] = int(bucket.get("losses", 0)) + 1

    trades = max(1, int(bucket.get("trades", 0)))
    wins = int(bucket.get("wins", 0))

    bucket["win_rate"] = round(wins / trades, 4)
    bucket["weight"] = _calc_weight(bucket["win_rate"], trades)

    return bucket


def _calculate_global_controls(
    win_rate: float,
    avg_score_winners: float,
    avg_score_losers: float,
    total_closed: int,
) -> Tuple[float, float, float, List[str]]:
    """
    Produces global evolution controls.

    score_boost:
    - Slightly boosts or reduces final score.

    filter_strictness:
    - Above 1.0 = stricter.
    - Below 1.0 = looser.

    ranking_confidence:
    - Used to sort stronger setups above weaker setups.
    """

    notes: List[str] = []

    if total_closed < MIN_CLOSED_TRADES_TO_EVOLVE:
        return 1.0, 1.0, 1.0, [
            f"Waiting for more closed trades. Need at least {MIN_CLOSED_TRADES_TO_EVOLVE}, found {total_closed}."
        ]

    if win_rate >= 0.60:
        score_boost = 1.05
        filter_strictness = 0.98
        ranking_confidence = 1.08
        notes.append("Win rate is strong. Slight boost applied to ranking confidence.")
    elif win_rate >= 0.50:
        score_boost = 1.02
        filter_strictness = 1.00
        ranking_confidence = 1.03
        notes.append("Win rate is stable. Mild score boost applied.")
    elif win_rate >= 0.40:
        score_boost = 0.98
        filter_strictness = 1.05
        ranking_confidence = 1.00
        notes.append("Win rate is weak. Filters made slightly stricter.")
    else:
        score_boost = 0.95
        filter_strictness = 1.10
        ranking_confidence = 0.97
        notes.append("Win rate is poor. Strict filtering mode enabled.")

    if avg_score_losers > avg_score_winners and avg_score_losers > 0:
        filter_strictness += 0.05
        score_boost -= 0.02
        notes.append("Losing trades had higher/equal scores than winners. Score model made stricter.")

    return (
        round(_clamp(score_boost, 0.85, 1.15), 4),
        round(_clamp(filter_strictness, 0.90, 1.20), 4),
        round(_clamp(ranking_confidence, 0.90, 1.20), 4),
        notes,
    )


# =========================
# PUBLIC ENGINE
# =========================

def run_evolution_engine() -> Dict[str, Any]:
    """
    Run this every 5 minutes after Outcome Tracker.

    It reads completed outcomes and updates:
    - evolution_state.json
    - evolution_report.txt
    """

    _ensure_dirs()

    closed_trades = _closed_trades_from_journal()

    state = json.loads(json.dumps(DEFAULT_STATE))
    old_state = _load_json(EVOLUTION_STATE_PATH, DEFAULT_STATE)

    total_closed = len(closed_trades)
    wins = 0
    losses = 0
    rr_values: List[float] = []

    winner_scores: List[float] = []
    loser_scores: List[float] = []

    symbol_memory: Dict[str, Any] = {}
    side_memory: Dict[str, Any] = {
        "LONG": _build_memory_bucket(),
        "SHORT": _build_memory_bucket(),
    }
    reason_memory: Dict[str, Any] = {}

    for row in closed_trades:
        outcome = _get_outcome(row)
        if outcome not in {"WIN", "LOSS"}:
            continue

        symbol = _get_symbol(row)
        side = _get_side(row)
        score = _get_score(row)
        rr = _get_rr(row)
        reason = _get_reason(row)

        if outcome == "WIN":
            wins += 1
            winner_scores.append(score)
        else:
            losses += 1
            loser_scores.append(score)

        if rr > 0:
            rr_values.append(rr)

        if symbol not in symbol_memory:
            symbol_memory[symbol] = _build_memory_bucket()
        symbol_memory[symbol] = _update_bucket(symbol_memory[symbol], outcome)

        if side not in side_memory:
            side_memory[side] = _build_memory_bucket()
        side_memory[side] = _update_bucket(side_memory[side], outcome)

        for tag in _extract_reason_tags(reason):
            if tag not in reason_memory:
                reason_memory[tag] = _build_memory_bucket()
            reason_memory[tag] = _update_bucket(reason_memory[tag], outcome)

    win_rate = round(wins / total_closed, 4) if total_closed else 0.0
    avg_rr = round(sum(rr_values) / len(rr_values), 4) if rr_values else 0.0
    avg_score_winners = round(sum(winner_scores) / len(winner_scores), 4) if winner_scores else 0.0
    avg_score_losers = round(sum(loser_scores) / len(loser_scores), 4) if loser_scores else 0.0

    score_boost, filter_strictness, ranking_confidence, notes = _calculate_global_controls(
        win_rate=win_rate,
        avg_score_winners=avg_score_winners,
        avg_score_losers=avg_score_losers,
        total_closed=total_closed,
    )

    state.update(
        {
            "version": DEFAULT_STATE["version"],
            "last_updated": _now_iso(),
            "total_closed_trades": total_closed,
            "total_wins": wins,
            "total_losses": losses,
            "win_rate": win_rate,
            "avg_rr": avg_rr,
            "avg_score_winners": avg_score_winners,
            "avg_score_losers": avg_score_losers,
            "score_boost": score_boost,
            "filter_strictness": filter_strictness,
            "ranking_confidence": ranking_confidence,
            "symbol_memory": symbol_memory,
            "side_memory": side_memory,
            "reason_memory": reason_memory,
            "evolution_notes": notes,
        }
    )

    _save_json(EVOLUTION_STATE_PATH, state)
    _write_evolution_report(state, old_state)

    return state


def get_evolution_state() -> Dict[str, Any]:
    """
    Safe reader for dashboard/setup engine.
    """

    _ensure_dirs()
    return _load_json(EVOLUTION_STATE_PATH, DEFAULT_STATE)


def apply_evolution_score(
    symbol: str,
    base_score: float,
    setup_data: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Use this later inside setup ranking.

    It adjusts score using:
    - global score boost
    - symbol performance memory
    - side performance memory
    - reason tag performance memory

    This function is safe:
    If evolution memory is missing, it returns base_score.
    """

    setup_data = setup_data or {}
    state = get_evolution_state()

    score = _safe_float(base_score, 0.0)
    symbol_key = str(symbol or "UNKNOWN").upper()
    side = _get_side(setup_data)
    reason = _get_reason(setup_data)

    score *= _safe_float(state.get("score_boost"), 1.0)

    symbol_bucket = state.get("symbol_memory", {}).get(symbol_key)
    if symbol_bucket:
        score *= _safe_float(symbol_bucket.get("weight"), 1.0)

    side_bucket = state.get("side_memory", {}).get(side)
    if side_bucket:
        score *= _safe_float(side_bucket.get("weight"), 1.0)

    reason_tags = _extract_reason_tags(reason)
    reason_weights = []
    for tag in reason_tags:
        bucket = state.get("reason_memory", {}).get(tag)
        if bucket:
            reason_weights.append(_safe_float(bucket.get("weight"), 1.0))

    if reason_weights:
        score *= sum(reason_weights) / len(reason_weights)

    score *= _safe_float(state.get("ranking_confidence"), 1.0)

    return round(_clamp(score, 0.0, 100.0), 2)


def get_evolution_filter_threshold(base_threshold: float = 70.0) -> float:
    """
    Use this later for adaptive filtering.

    Higher filter_strictness means threshold goes up.
    Example:
    base 70 and strictness 1.10 = threshold 77.
    """

    state = get_evolution_state()
    strictness = _safe_float(state.get("filter_strictness"), 1.0)
    return round(_clamp(base_threshold * strictness, 50.0, 95.0), 2)


# =========================
# REPORT
# =========================

def _top_items(memory: Dict[str, Any], limit: int = 10) -> List[Tuple[str, Dict[str, Any]]]:
    items = list(memory.items())
    items.sort(
        key=lambda x: (
            int(x[1].get("trades", 0)),
            float(x[1].get("win_rate", 0.0)),
            float(x[1].get("weight", 1.0)),
        ),
        reverse=True,
    )
    return items[:limit]


def _write_evolution_report(state: Dict[str, Any], old_state: Dict[str, Any]) -> None:
    _ensure_dirs()

    lines: List[str] = []
    lines.append("TITAN EVOLUTION REPORT")
    lines.append("=" * 60)
    lines.append(f"Updated: {state.get('last_updated')}")
    lines.append("")
    lines.append("GLOBAL PERFORMANCE")
    lines.append("-" * 60)
    lines.append(f"Closed trades      : {state.get('total_closed_trades')}")
    lines.append(f"Wins               : {state.get('total_wins')}")
    lines.append(f"Losses             : {state.get('total_losses')}")
    lines.append(f"Win rate           : {round(float(state.get('win_rate', 0)) * 100, 2)}%")
    lines.append(f"Average RR         : {state.get('avg_rr')}")
    lines.append(f"Avg score winners  : {state.get('avg_score_winners')}")
    lines.append(f"Avg score losers   : {state.get('avg_score_losers')}")
    lines.append("")
    lines.append("EVOLUTION CONTROLS")
    lines.append("-" * 60)
    lines.append(f"Score boost        : {state.get('score_boost')}  | old: {old_state.get('score_boost')}")
    lines.append(f"Filter strictness  : {state.get('filter_strictness')}  | old: {old_state.get('filter_strictness')}")
    lines.append(f"Ranking confidence : {state.get('ranking_confidence')}  | old: {old_state.get('ranking_confidence')}")
    lines.append("")
    lines.append("NOTES")
    lines.append("-" * 60)

    for note in state.get("evolution_notes", []):
        lines.append(f"- {note}")

    lines.append("")
    lines.append("TOP SYMBOL MEMORY")
    lines.append("-" * 60)
    for symbol, bucket in _top_items(state.get("symbol_memory", {}), 10):
        lines.append(
            f"{symbol}: trades={bucket.get('trades')}, wins={bucket.get('wins')}, "
            f"losses={bucket.get('losses')}, win_rate={round(float(bucket.get('win_rate', 0)) * 100, 2)}%, "
            f"weight={bucket.get('weight')}"
        )

    lines.append("")
    lines.append("SIDE MEMORY")
    lines.append("-" * 60)
    for side, bucket in state.get("side_memory", {}).items():
        lines.append(
            f"{side}: trades={bucket.get('trades')}, wins={bucket.get('wins')}, "
            f"losses={bucket.get('losses')}, win_rate={round(float(bucket.get('win_rate', 0)) * 100, 2)}%, "
            f"weight={bucket.get('weight')}"
        )

    lines.append("")
    lines.append("REASON / SETUP TAG MEMORY")
    lines.append("-" * 60)
    for tag, bucket in _top_items(state.get("reason_memory", {}), 20):
        lines.append(
            f"{tag}: trades={bucket.get('trades')}, wins={bucket.get('wins')}, "
            f"losses={bucket.get('losses')}, win_rate={round(float(bucket.get('win_rate', 0)) * 100, 2)}%, "
            f"weight={bucket.get('weight')}"
        )

    EVOLUTION_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


# =========================
# CLI TEST
# =========================

if __name__ == "__main__":
    result = run_evolution_engine()
    print("✅ TITAN Evolution Engine completed")
    print(f"Closed trades: {result.get('total_closed_trades')}")
    print(f"Win rate: {round(float(result.get('win_rate', 0)) * 100, 2)}%")
    print(f"Score boost: {result.get('score_boost')}")
    print(f"Filter strictness: {result.get('filter_strictness')}")
    print(f"Ranking confidence: {result.get('ranking_confidence')}")
    print(f"Report: {EVOLUTION_REPORT_PATH}")