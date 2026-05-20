"""
TITAN Historical Experience Feeder
----------------------------------

Converts cached historical OHLC data into Experience Vault-compatible
simulated experience records.

Safety contract:
- Writes only to data/experience_vault/imported_trade_logs/
- Does not write live journals, active trades, Telegram, broker, or orders
- Records are tagged as HISTORICAL_SIMULATED / BACKTEST_SIMULATED

Safe test command:
python research/historical_experience_feeder.py --dry-run --limit 100
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from engines.momentum_engine import strong_momentum
from engines.trade_levels import calculate_trade_levels
from engines.trend_engine import trade_side_from_trend, trend_direction
from scanners.compression_scanner import compression_score
from scanners.strength_scanner import price_strength_score
from scanners.volume_scanner import volume_anomaly_score


CACHE_DIR = PROJECT_ROOT / "data" / "cache"
OUTPUT_DIR = PROJECT_ROOT / "data" / "experience_vault" / "imported_trade_logs"
JSONL_PATH = OUTPUT_DIR / "historical_experience_import.jsonl"
CSV_PATH = OUTPUT_DIR / "historical_experience_import.csv"
REPORT_PATH = OUTPUT_DIR / "historical_experience_import_report.json"

SAFETY_TAGS = {
    "source_type": "HISTORICAL_SIMULATED",
    "trust_level": "BACKTEST_SIMULATED",
    "validation_status": "UNVALIDATED",
    "native_trade_import": False,
    "live_mutation": False,
    "broker_mutation": False,
    "telegram_mutation": False,
}

CSV_FIELDS = [
    "experience_hash",
    "symbol",
    "date",
    "signal_time",
    "timeframe",
    "setup_type",
    "side",
    "entry",
    "sl",
    "target",
    "outcome",
    "outcome_reason",
    "pnl_points",
    "rr",
    "score",
    "trend",
    "volume_score",
    "strength_score",
    "compression_score",
    "reason",
    "lesson_learned",
    "source_type",
    "trust_level",
    "validation_status",
    "native_trade_import",
    "live_mutation",
    "broker_mutation",
    "telegram_mutation",
]


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_symbol(symbol: str) -> str:
    return str(symbol or "").replace(".NS", "").upper().strip()


def discover_symbols(requested: Optional[Iterable[str]] = None) -> List[str]:
    if requested:
        return sorted({normalize_symbol(symbol) for symbol in requested if normalize_symbol(symbol)})

    configured: List[str] = []
    try:
        from config.universe import NSE_STOCKS

        configured = [normalize_symbol(symbol) for symbol in NSE_STOCKS]
    except Exception:
        configured = []

    cached = {path.stem.upper() for path in CACHE_DIR.glob("*.csv") if path.is_file()}
    if configured:
        symbols = [symbol for symbol in configured if symbol in cached]
        return symbols or sorted(cached)
    return sorted(cached)


def read_candles(symbol: str) -> pd.DataFrame:
    path = CACHE_DIR / f"{normalize_symbol(symbol)}.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    required = {"Datetime", "Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(df.columns):
        return pd.DataFrame()
    df = df.copy()
    df["Datetime"] = pd.to_datetime(df["Datetime"], errors="coerce", utc=True)
    for column in ("Open", "High", "Low", "Close", "Volume"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["Datetime", "Open", "High", "Low", "Close"]).sort_values("Datetime")
    return df.reset_index(drop=True)


def infer_timeframe(df: pd.DataFrame) -> str:
    if len(df) < 3:
        return "UNKNOWN"
    diffs = df["Datetime"].diff().dropna()
    if diffs.empty:
        return "UNKNOWN"
    minutes = int(round(diffs.median().total_seconds() / 60))
    return f"{minutes}m" if minutes > 0 else "UNKNOWN"


def simulated_score(volume: float, strength: float, compression: float, momentum_ok: bool) -> float:
    volume_component = min(max(volume, 0.0), 3.0) * 20.0
    strength_component = min(abs(strength), 5.0) * 8.0
    compression_component = min(max(compression, 0.0), 10.0) * 4.0
    bonus = 10.0 if momentum_ok else 0.0
    return round(min(100.0, volume_component + strength_component + compression_component + bonus), 2)


def classify_setup(side: str, volume: float, strength: float, compression: float) -> str:
    directional_strength = strength if side == "LONG" else -strength
    if volume >= 1.5 and directional_strength > 0:
        return "trend_momentum_breakout"
    if compression >= 5.0 and directional_strength >= 0:
        return "compression_breakout_attempt"
    return "trend_continuation"


def should_simulate(history: pd.DataFrame, side: str, volume: float, strength: float, compression: float) -> bool:
    if side not in {"LONG", "SHORT"}:
        return False
    if not strong_momentum(history, side=side):
        return False
    directional_strength = strength if side == "LONG" else -strength
    return volume >= 1.15 and directional_strength >= 0.15 and compression >= 1.0


def evaluate_outcome(
    future: pd.DataFrame,
    side: str,
    entry: float,
    sl: float,
    target: float,
) -> Tuple[str, str, float, float]:
    if future.empty:
        return "NO_FOLLOWUP", "No future candles available after signal", 0.0, 0.0

    risk = abs(entry - sl)
    if risk <= 0:
        return "INVALID_LEVELS", "Risk is zero or negative", 0.0, 0.0

    for _, candle in future.iterrows():
        high = float(candle["High"])
        low = float(candle["Low"])
        stamp = candle["Datetime"].isoformat()
        if side == "LONG":
            stopped = low <= sl
            targeted = high >= target
            if stopped and targeted:
                return "LOSS", f"SL and target touched in same candle; conservative SL-first at {stamp}", round(sl - entry, 4), -1.0
            if stopped:
                return "LOSS", f"Stop loss touched at {stamp}", round(sl - entry, 4), -1.0
            if targeted:
                return "WIN", f"Target touched at {stamp}", round(target - entry, 4), round((target - entry) / risk, 3)
        else:
            stopped = high >= sl
            targeted = low <= target
            if stopped and targeted:
                return "LOSS", f"SL and target touched in same candle; conservative SL-first at {stamp}", round(entry - sl, 4), -1.0
            if stopped:
                return "LOSS", f"Stop loss touched at {stamp}", round(entry - sl, 4), -1.0
            if targeted:
                return "WIN", f"Target touched at {stamp}", round(entry - target, 4), round((entry - target) / risk, 3)

    final_close = float(future.iloc[-1]["Close"])
    pnl = final_close - entry if side == "LONG" else entry - final_close
    outcome = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "FLAT"
    rr = round(pnl / risk, 3)
    return outcome, "Neither SL nor target touched; marked by final lookahead close", round(pnl, 4), rr


def build_reason(
    trend: str,
    side: str,
    setup_type: str,
    volume: float,
    strength: float,
    compression: float,
    score: float,
) -> str:
    return (
        f"{setup_type} simulated from cached candles: trend={trend}, side={side}, "
        f"volume_ratio={volume}, strength_pct={strength}, compression={compression}, score={score}"
    )


def build_lesson(record: Dict[str, Any]) -> str:
    if record["outcome"] == "WIN":
        return (
            f"{record['setup_type']} on {record['symbol']} worked in {record['trend']} conditions; "
            f"preserve as simulated evidence only until validated."
        )
    if record["outcome"] == "LOSS":
        return (
            f"{record['setup_type']} on {record['symbol']} failed or underperformed; "
            f"treat similar conditions cautiously until live/paper validation confirms."
        )
    return (
        f"{record['setup_type']} on {record['symbol']} produced inconclusive simulated evidence; "
        f"do not promote without more validation."
    )


def simulate_symbol(symbol: str, limit: int, lookahead: int, min_history: int) -> List[Dict[str, Any]]:
    df = read_candles(symbol)
    if df.empty or len(df) < min_history + lookahead + 1:
        return []

    timeframe = infer_timeframe(df)
    records: List[Dict[str, Any]] = []
    max_index = len(df) - lookahead
    for index in range(min_history, max_index):
        history = df.iloc[: index + 1].copy()
        future = df.iloc[index + 1 : index + 1 + lookahead].copy()
        trend = trend_direction(history)
        side = trade_side_from_trend(trend)
        if not side:
            continue

        volume = float(volume_anomaly_score(history))
        strength = float(price_strength_score(history))
        compression = float(compression_score(history))
        if not should_simulate(history, side, volume, strength, compression):
            continue

        entry, sl, target = calculate_trade_levels(history, side)
        if entry is None or sl is None or target is None:
            continue

        setup_type = classify_setup(side, volume, strength, compression)
        momentum_ok = strong_momentum(history, side=side)
        score = simulated_score(volume, strength, compression, momentum_ok)
        outcome, outcome_reason, pnl_points, rr = evaluate_outcome(future, side, entry, sl, target)
        signal_time = history.iloc[-1]["Datetime"].to_pydatetime()
        record = {
            **SAFETY_TAGS,
            "symbol": normalize_symbol(symbol),
            "date": signal_time.date().isoformat(),
            "signal_time": signal_time.isoformat(),
            "timeframe": timeframe,
            "setup_type": setup_type,
            "side": side,
            "entry": entry,
            "sl": sl,
            "target": target,
            "outcome": outcome,
            "outcome_reason": outcome_reason,
            "pnl_points": pnl_points,
            "rr": rr,
            "score": score,
            "trend": trend,
            "volume_score": volume,
            "strength_score": strength,
            "compression_score": compression,
            "reason": build_reason(trend, side, setup_type, volume, strength, compression, score),
        }
        record["lesson_learned"] = build_lesson(record)
        record["experience_hash"] = stable_hash(
            {
                "symbol": record["symbol"],
                "date": record["date"],
                "timeframe": record["timeframe"],
                "setup_type": record["setup_type"],
                "side": record["side"],
                "outcome": record["outcome"],
            }
        )
        records.append(record)
        if len(records) >= limit:
            break
    return records


def load_existing_hashes() -> set:
    hashes = set()
    if JSONL_PATH.exists():
        for line in JSONL_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                if payload.get("experience_hash"):
                    hashes.add(payload["experience_hash"])
            except Exception:
                continue
    return hashes


def write_jsonl(path: Path, records: List[Dict[str, Any]]) -> None:
    with path.open("a", encoding="utf-8") as output_file:
        for record in records:
            output_file.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def write_csv(path: Path, records: List[Dict[str, Any]]) -> None:
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        for record in records:
            writer.writerow(record)


def build_report(records: List[Dict[str, Any]], skipped_duplicates: int, dry_run: bool, symbols: List[str]) -> Dict[str, Any]:
    outcome_counts: Dict[str, int] = {}
    setup_counts: Dict[str, int] = {}
    for record in records:
        outcome_counts[record["outcome"]] = outcome_counts.get(record["outcome"], 0) + 1
        setup_counts[record["setup_type"]] = setup_counts.get(record["setup_type"], 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "DRY_RUN" if dry_run else "WRITTEN",
        "records_generated": len(records),
        "skipped_duplicates": skipped_duplicates,
        "symbols_scanned": len(symbols),
        "output_jsonl": str(JSONL_PATH),
        "output_csv": str(CSV_PATH),
        "safety": SAFETY_TAGS,
        "outcome_counts": outcome_counts,
        "setup_counts": setup_counts,
        "note": "Historical simulated experience only; no native trade import and no live mutation.",
    }


def run_feeder(
    symbols: Optional[Iterable[str]] = None,
    limit: int = 100,
    lookahead: int = 16,
    min_history: int = 80,
    dry_run: bool = False,
) -> Dict[str, Any]:
    selected_symbols = discover_symbols(symbols)
    existing_hashes = load_existing_hashes()
    emitted_hashes = set(existing_hashes)
    records: List[Dict[str, Any]] = []
    skipped_duplicates = 0

    per_symbol_limit = max(1, limit)
    for symbol in selected_symbols:
        if len(records) >= limit:
            break
        candidates = simulate_symbol(symbol, per_symbol_limit, lookahead, min_history)
        for candidate in candidates:
            if candidate["experience_hash"] in emitted_hashes:
                skipped_duplicates += 1
                continue
            emitted_hashes.add(candidate["experience_hash"])
            records.append(candidate)
            if len(records) >= limit:
                break

    report = build_report(records, skipped_duplicates, dry_run, selected_symbols)
    if not dry_run:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        write_jsonl(JSONL_PATH, records)
        write_csv(CSV_PATH, records)
        REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate HISTORICAL_SIMULATED records for the TITAN Experience Vault.",
        epilog="Safe test command: python research/historical_experience_feeder.py --dry-run --limit 100",
    )
    parser.add_argument("--symbols", nargs="*", help="Optional NSE symbols, e.g. RELIANCE TCS INFY")
    parser.add_argument("--limit", type=int, default=100, help="Maximum new records to generate")
    parser.add_argument("--lookahead", type=int, default=16, help="Future candles used to resolve outcome")
    parser.add_argument("--min-history", type=int, default=80, help="Minimum candles before a signal can be simulated")
    parser.add_argument("--dry-run", action="store_true", help="Generate summary without writing output files")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_feeder(
        symbols=args.symbols,
        limit=max(1, args.limit),
        lookahead=max(1, args.lookahead),
        min_history=max(60, args.min_history),
        dry_run=args.dry_run,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
