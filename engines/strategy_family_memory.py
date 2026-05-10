"""
TITAN Phase 5 - Strategy Family Memory Builder
----------------------------------------------

Builds offline memory for broad strategy families from existing journals.
This is intentionally outside the live ranking hot path.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engines.meta_intelligence_engine import classify_strategy_family

JOURNAL_DIR = PROJECT_ROOT / "data" / "journals"
MEMORY_DIR = PROJECT_ROOT / "data" / "memory"
REPORTS_DIR = PROJECT_ROOT / "reports"

TRADE_JOURNAL_CSV = JOURNAL_DIR / "trade_journal.csv"
TRADE_OUTCOMES_JSONL = JOURNAL_DIR / "trade_outcomes.jsonl"
TRADE_OUTCOMES_OLD_CSV = JOURNAL_DIR / "trade_outcomes_old.csv"
FAMILY_MEMORY_PATH = MEMORY_DIR / "strategy_family_memory.json"
SELF_EVALUATION_REPORT_PATH = REPORTS_DIR / "self_evaluation_report.txt"

STATE_VERSION = "5.0"
MAX_ROWS = 10000
DECAY_FACTOR = 0.985
MIN_FAMILY_TRADES = 5


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
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))[-MAX_ROWS:]
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
        return rows[-MAX_ROWS:]
    except Exception:
        return []


def _symbol(value: Any) -> str:
    return _safe_upper(value).replace(".NS", "")


def _side(value: Any) -> str:
    side = _safe_upper(value)
    if side == "BUY":
        return "LONG"
    if side == "SELL":
        return "SHORT"
    return side


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


def _journal_lookup(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = "|".join([
            str(row.get("scan_id", "")).strip(),
            _symbol(row.get("symbol")),
            _side(row.get("side")),
            str(row.get("entry", "")).strip(),
        ])
        if key.strip("|"):
            lookup[key] = row
        trade_id = str(row.get("trade_id") or "").strip()
        if trade_id:
            lookup[trade_id] = row
    return lookup


def _new_bucket() -> Dict[str, Any]:
    return {
        "trades": 0.0,
        "wins": 0.0,
        "losses": 0.0,
        "win_rate": 0.0,
        "posterior_win_rate": 0.5,
        "sample_confidence": 0.0,
        "family_quality_score": 50.0,
        "weight": 1.0,
    }


def _update_bucket(bucket: Dict[str, Any], outcome: str, age_index: int, total: int) -> None:
    decay_power = max(0, total - age_index - 1)
    weight = DECAY_FACTOR ** decay_power
    bucket["trades"] = _safe_float(bucket.get("trades")) + weight
    if outcome == "WIN":
        bucket["wins"] = _safe_float(bucket.get("wins")) + weight
    elif outcome == "LOSS":
        bucket["losses"] = _safe_float(bucket.get("losses")) + weight


def _finalize_bucket(bucket: Dict[str, Any]) -> Dict[str, Any]:
    trades = _safe_float(bucket.get("trades"))
    wins = _safe_float(bucket.get("wins"))
    losses = _safe_float(bucket.get("losses"))
    total = wins + losses
    win_rate = wins / total if total else 0.0
    posterior = (wins + 2.0) / (total + 4.0) if total else 0.5
    sample_conf = min(1.0, trades / 30.0)
    shrunk_edge = (posterior - 0.5) * sample_conf
    quality = _clamp((0.5 + shrunk_edge) * 100.0, 35.0, 65.0)
    weight = _clamp(1.0 + (shrunk_edge * 0.40), 0.94, 1.06)

    return {
        "trades": round(trades, 4),
        "wins": round(wins, 4),
        "losses": round(losses, 4),
        "win_rate": round(win_rate, 4),
        "posterior_win_rate": round(posterior, 4),
        "sample_confidence": round(sample_conf, 4),
        "family_quality_score": round(quality, 2),
        "weight": round(weight, 4),
        "memory_active": bool(trades >= MIN_FAMILY_TRADES),
    }


def _top_items(memory: Dict[str, Any], limit: int = 10) -> List[tuple[str, Dict[str, Any]]]:
    items = list(memory.items())
    items.sort(
        key=lambda item: (
            _safe_float(item[1].get("trades")),
            _safe_float(item[1].get("family_quality_score")),
        ),
        reverse=True,
    )
    return items[:limit]


def build_strategy_family_memory(write_files: bool = True) -> Dict[str, Any]:
    _ensure_dirs()

    journal_rows = _read_csv(TRADE_JOURNAL_CSV)
    outcome_rows = _read_jsonl(TRADE_OUTCOMES_JSONL)
    if not outcome_rows:
        outcome_rows = _read_csv(TRADE_OUTCOMES_OLD_CSV)

    lookup = _journal_lookup(journal_rows)
    latest: Dict[str, Dict[str, Any]] = {}
    for row in outcome_rows:
        outcome = _outcome(row.get("outcome") or row.get("result") or row.get("status"))
        if outcome in {"WIN", "LOSS"}:
            latest[_trade_key(row)] = row

    closed = list(latest.values())
    families: Dict[str, Dict[str, Any]] = {}
    symbols: Dict[str, Dict[str, Any]] = {}
    regimes: Dict[str, Dict[str, Any]] = {}
    wins = losses = 0

    total = len(closed)
    for idx, outcome_row in enumerate(closed):
        outcome = _outcome(outcome_row.get("outcome") or outcome_row.get("result") or outcome_row.get("status"))
        if outcome not in {"WIN", "LOSS"}:
            continue

        wins += 1 if outcome == "WIN" else 0
        losses += 1 if outcome == "LOSS" else 0

        journal_row = lookup.get(_trade_key(outcome_row), {})
        merged = {**journal_row, **outcome_row}
        family = classify_strategy_family(merged)
        symbol = _symbol(merged.get("symbol"))
        regime = str(merged.get("market_status") or "UNKNOWN")[:80]

        for memory, key in [(families, family), (symbols, symbol), (regimes, regime)]:
            if key not in memory:
                memory[key] = _new_bucket()
            _update_bucket(memory[key], outcome, idx, total)

    finalized_families = {key: _finalize_bucket(bucket) for key, bucket in families.items()}
    finalized_symbols = {key: _finalize_bucket(bucket) for key, bucket in symbols.items()}
    finalized_regimes = {key: _finalize_bucket(bucket) for key, bucket in regimes.items()}

    total_closed = wins + losses
    global_bucket = _finalize_bucket({"trades": total_closed, "wins": wins, "losses": losses})

    state = {
        "version": STATE_VERSION,
        "last_updated": _now(),
        "total_closed_trades": total_closed,
        "total_wins": wins,
        "total_losses": losses,
        "global": global_bucket,
        "families": finalized_families,
        "symbols": finalized_symbols,
        "regimes": finalized_regimes,
        "overfitting_controls": {
            "minimum_global_trades": 10,
            "minimum_family_trades": MIN_FAMILY_TRADES,
            "decay_factor": DECAY_FACTOR,
            "bayesian_prior": {"alpha": 2.0, "beta": 2.0},
            "family_quality_score_cap": [35.0, 65.0],
            "runtime_adjustment_cap": [-0.30, 0.20],
        },
    }

    if write_files:
        with FAMILY_MEMORY_PATH.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        write_self_evaluation_report(state)

    return state


def write_self_evaluation_report(state: Dict[str, Any]) -> None:
    _ensure_dirs()

    lines = [
        "TITAN PHASE 5 SELF-EVALUATION REPORT",
        "=" * 60,
        f"Updated: {state.get('last_updated')}",
        f"Closed trades: {state.get('total_closed_trades')}",
        f"Wins: {state.get('total_wins')}",
        f"Losses: {state.get('total_losses')}",
        f"Global calibrated quality: {(state.get('global') or {}).get('family_quality_score')}",
        "",
        "WHAT TITAN LEARNED",
        "-" * 60,
    ]

    if _safe_float(state.get("total_closed_trades"), 0.0) < 10:
        lines.append("- Learning phase active. Meta intelligence remains mostly neutral.")
    else:
        lines.append("- Strategy-family memory can influence ranking within strict caps.")

    lines.extend(["", "STRONGEST STRATEGY FAMILIES", "-" * 60])
    for family, bucket in _top_items(state.get("families", {}), 8):
        lines.append(
            f"{family}: trades={bucket.get('trades')}, wins={bucket.get('wins')}, "
            f"losses={bucket.get('losses')}, posterior={bucket.get('posterior_win_rate')}, "
            f"quality={bucket.get('family_quality_score')}"
        )

    weakest = list(state.get("families", {}).items())
    weakest.sort(
        key=lambda item: (
            _safe_float(item[1].get("family_quality_score"), 50.0),
            -_safe_float(item[1].get("trades"), 0.0),
        )
    )
    lines.extend(["", "WEAKEST SETUPS TO AVOID", "-" * 60])
    for family, bucket in weakest[:8]:
        lines.append(
            f"{family}: trades={bucket.get('trades')}, posterior={bucket.get('posterior_win_rate')}, "
            f"quality={bucket.get('family_quality_score')}, active={bucket.get('memory_active')}"
        )

    lines.extend(["", "STRONGEST SYMBOLS", "-" * 60])
    for symbol, bucket in _top_items(state.get("symbols", {}), 8):
        lines.append(
            f"{symbol}: trades={bucket.get('trades')}, posterior={bucket.get('posterior_win_rate')}, "
            f"quality={bucket.get('family_quality_score')}"
        )

    lines.extend(["", "REGIME PERFORMANCE SUMMARY", "-" * 60])
    for regime, bucket in _top_items(state.get("regimes", {}), 8):
        lines.append(
            f"{regime}: trades={bucket.get('trades')}, posterior={bucket.get('posterior_win_rate')}, "
            f"quality={bucket.get('family_quality_score')}"
        )

    lines.extend(["", "CONFIDENCE CALIBRATION SUMMARY", "-" * 60])
    controls = state.get("overfitting_controls", {})
    for key, value in controls.items():
        lines.append(f"{key}: {value}")

    SELF_EVALUATION_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def get_strategy_family_memory_path() -> Path:
    return FAMILY_MEMORY_PATH


def get_self_evaluation_report_path() -> Path:
    return SELF_EVALUATION_REPORT_PATH


if __name__ == "__main__":
    built = build_strategy_family_memory(write_files=True)
    print("TITAN Phase 5 strategy family memory built")
    print(f"Closed trades: {built.get('total_closed_trades')}")
    print(f"State: {FAMILY_MEMORY_PATH}")
    print(f"Report: {SELF_EVALUATION_REPORT_PATH}")
