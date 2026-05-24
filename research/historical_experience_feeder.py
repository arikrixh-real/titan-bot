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
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union


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
from research.experience_interpretation_engine import (
    EXPERIENCE_INTERPRETATION_FIELDS,
    build_experience_interpretation_fields,
)
from research.replay_realism_enrichment import REPLAY_REALISM_FIELDS, build_replay_realism_fields
from research.semantic_replay_enrichment import build_semantic_replay_labels


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
    "semantic_labels",
    "trap_label",
    "fake_breakout_label",
    "liquidity_sweep_label",
    "regime_label",
    "volatility_state_label",
    "mtf_alignment_label",
    "gap_behavior_label",
    "panic_euphoria_label",
    "sector_rotation_label",
    "correlation_state_label",
    "news_reaction_label",
    "semantic_label_confidence",
    "semantic_label_reasons",
    *REPLAY_REALISM_FIELDS,
    *EXPERIENCE_INTERPRETATION_FIELDS,
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


def parse_year_focus(value: Optional[Union[str, Iterable[int]]]) -> List[int]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.split(",")
    else:
        parts = list(value)
    years: List[int] = []
    seen = set()
    for part in parts:
        try:
            year = int(str(part).strip())
        except Exception:
            continue
        if 1900 <= year <= 2100 and year not in seen:
            years.append(year)
            seen.add(year)
    return years


def resolve_source_dir(source_dir: Optional[Path] = None) -> Path:
    return Path(source_dir) if source_dir is not None else CACHE_DIR


def discover_symbols(requested: Optional[Iterable[str]] = None, source_dir: Optional[Path] = None) -> List[str]:
    source_path = resolve_source_dir(source_dir)
    if requested:
        return sorted({normalize_symbol(symbol) for symbol in requested if normalize_symbol(symbol)})

    configured: List[str] = []
    try:
        from config.universe import NSE_STOCKS

        configured = [normalize_symbol(symbol) for symbol in NSE_STOCKS]
    except Exception:
        configured = []

    cached = {path.stem.upper() for path in source_path.glob("*.csv") if path.is_file()}
    if configured:
        symbols = [symbol for symbol in configured if symbol in cached]
        return symbols or sorted(cached)
    return sorted(cached)


def read_candles(symbol: str, source_dir: Optional[Path] = None) -> pd.DataFrame:
    source_path = resolve_source_dir(source_dir)
    path = source_path / f"{normalize_symbol(symbol)}.csv"
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


def build_experience_hash(record: Dict[str, Any]) -> str:
    return stable_hash(
        {
            "symbol": record["symbol"],
            "date": record["date"],
            "signal_time": record["signal_time"],
            "timeframe": record["timeframe"],
            "setup_type": record["setup_type"],
            "side": record["side"],
            "outcome": record["outcome"],
        }
    )


def simulate_symbol(
    symbol: str,
    limit: int,
    lookahead: int,
    min_history: int,
    source_dir: Optional[Path] = None,
    year_focus: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    df = read_candles(symbol, source_dir=source_dir)
    if df.empty or len(df) < min_history + lookahead + 1:
        return []

    timeframe = infer_timeframe(df)
    records: List[Dict[str, Any]] = []
    max_index = len(df) - lookahead
    year_filter = set(year_focus or [])
    for index in range(min_history, max_index):
        signal_timestamp = df.iloc[index]["Datetime"]
        if year_filter and int(signal_timestamp.year) not in year_filter:
            continue
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
        signal_time = signal_timestamp.to_pydatetime()
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
        record.update(build_semantic_replay_labels(history, future, record))
        record.update(build_replay_realism_fields(history, future, record))
        record.update(build_experience_interpretation_fields(history, future, record))
        record["lesson_learned"] = build_lesson(record)
        record["experience_hash"] = build_experience_hash(record)
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
                try:
                    hashes.add(build_experience_hash(payload))
                except Exception:
                    pass
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


def record_year(record: Dict[str, Any]) -> Optional[int]:
    value = str(record.get("date") or record.get("signal_time") or "")
    if len(value) < 4:
        return None
    try:
        return int(value[:4])
    except Exception:
        return None


def _can_accept_record(
    record: Dict[str, Any],
    emitted_hashes: Set[str],
    symbol_counts: Dict[str, int],
    year_counts: Dict[int, int],
    year_focus: List[int],
    max_per_symbol: Optional[int],
    max_per_year: Optional[int],
) -> bool:
    if record.get("experience_hash") in emitted_hashes:
        return False
    symbol = str(record.get("symbol") or "")
    year = record_year(record)
    year_filter = set(year_focus)
    if year_filter and year not in year_filter:
        return False
    if max_per_symbol is not None and symbol_counts.get(symbol, 0) >= max_per_symbol:
        return False
    if max_per_year is not None and year is not None and year_counts.get(year, 0) >= max_per_year:
        return False
    return True


def _accept_record(
    record: Dict[str, Any],
    records: List[Dict[str, Any]],
    emitted_hashes: Set[str],
    symbol_counts: Dict[str, int],
    year_counts: Dict[int, int],
) -> None:
    records.append(record)
    emitted_hashes.add(str(record.get("experience_hash")))
    symbol = str(record.get("symbol") or "")
    symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
    year = record_year(record)
    if year is not None:
        year_counts[year] = year_counts.get(year, 0) + 1


def _sequential_select_records(
    selected_symbols: List[str],
    limit: int,
    lookahead: int,
    min_history: int,
    source_path: Path,
    emitted_hashes: Set[str],
    year_focus: List[int],
    max_per_symbol: Optional[int],
    max_per_year: Optional[int],
) -> Tuple[List[Dict[str, Any]], int]:
    records: List[Dict[str, Any]] = []
    skipped_duplicates = 0
    symbol_counts: Dict[str, int] = {}
    year_counts: Dict[int, int] = {}
    per_symbol_limit = max(1, max_per_symbol or limit)

    for symbol in selected_symbols:
        if len(records) >= limit:
            break
        candidates = simulate_symbol(
            symbol,
            per_symbol_limit,
            lookahead,
            min_history,
            source_dir=source_path,
            year_focus=year_focus,
        )
        for candidate in candidates:
            if candidate["experience_hash"] in emitted_hashes:
                skipped_duplicates += 1
                continue
            if not _can_accept_record(
                candidate,
                emitted_hashes,
                symbol_counts,
                year_counts,
                year_focus,
                max_per_symbol,
                max_per_year,
            ):
                continue
            _accept_record(candidate, records, emitted_hashes, symbol_counts, year_counts)
            if len(records) >= limit:
                break

    return records, skipped_duplicates


def _stratified_select_records(
    selected_symbols: List[str],
    limit: int,
    lookahead: int,
    min_history: int,
    source_path: Path,
    emitted_hashes: Set[str],
    year_focus: List[int],
    max_per_symbol: Optional[int],
    max_per_year: Optional[int],
) -> Tuple[List[Dict[str, Any]], int]:
    records: List[Dict[str, Any]] = []
    skipped_duplicates = 0
    symbol_counts: Dict[str, int] = {}
    year_counts: Dict[int, int] = {}
    candidate_limit = max(1, limit)
    buckets: Dict[Tuple[int, str, str], List[Dict[str, Any]]] = {}

    for symbol in selected_symbols:
        candidates = simulate_symbol(
            symbol,
            candidate_limit,
            lookahead,
            min_history,
            source_dir=source_path,
            year_focus=year_focus,
        )
        for candidate in candidates:
            if candidate["experience_hash"] in emitted_hashes:
                skipped_duplicates += 1
                continue
            year = record_year(candidate)
            year_filter = set(year_focus)
            if year_filter and year not in year_filter:
                continue
            bucket_key = (
                year or 0,
                str(candidate.get("setup_type") or "UNKNOWN"),
                str(candidate.get("symbol") or symbol),
            )
            buckets.setdefault(bucket_key, []).append(candidate)

    ordered_keys = sorted(buckets, key=lambda key: (key[0], key[1], key[2]))
    while len(records) < limit and ordered_keys:
        next_keys: List[Tuple[int, str, str]] = []
        accepted_this_round = False
        for key in ordered_keys:
            bucket = buckets.get(key) or []
            while bucket:
                candidate = bucket.pop(0)
                if candidate["experience_hash"] in emitted_hashes:
                    skipped_duplicates += 1
                    continue
                if not _can_accept_record(
                    candidate,
                    emitted_hashes,
                    symbol_counts,
                    year_counts,
                    year_focus,
                    max_per_symbol,
                    max_per_year,
                ):
                    continue
                _accept_record(candidate, records, emitted_hashes, symbol_counts, year_counts)
                accepted_this_round = True
                break
            if bucket:
                next_keys.append(key)
            if len(records) >= limit:
                break
        if not accepted_this_round:
            break
        ordered_keys = next_keys

    return records, skipped_duplicates


def build_report(
    records: List[Dict[str, Any]],
    skipped_duplicates: int,
    dry_run: bool,
    symbols: List[str],
    source_dir: Optional[Path] = None,
    sampling_mode: str = "sequential",
    year_focus: Optional[List[int]] = None,
    max_per_symbol: Optional[int] = None,
    max_per_year: Optional[int] = None,
) -> Dict[str, Any]:
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
        "source_dir": str(resolve_source_dir(source_dir)),
        "output_jsonl": str(JSONL_PATH),
        "output_csv": str(CSV_PATH),
        "sampling_mode": sampling_mode,
        "year_focus": year_focus or [],
        "max_per_symbol": max_per_symbol,
        "max_per_year": max_per_year,
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
    source_dir: Optional[Path] = None,
    sampling_mode: str = "sequential",
    year_focus: Optional[Union[str, Iterable[int]]] = None,
    max_per_symbol: Optional[int] = None,
    max_per_year: Optional[int] = None,
) -> Dict[str, Any]:
    source_path = resolve_source_dir(source_dir)
    selected_symbols = discover_symbols(symbols, source_dir=source_path)
    existing_hashes = load_existing_hashes()
    emitted_hashes = set(existing_hashes)
    clean_sampling_mode = sampling_mode if sampling_mode in {"sequential", "stratified"} else "sequential"
    clean_year_focus = parse_year_focus(year_focus)
    clean_max_per_symbol = max(1, int(max_per_symbol)) if max_per_symbol is not None else None
    clean_max_per_year = max(1, int(max_per_year)) if max_per_year is not None else None

    if clean_sampling_mode == "stratified":
        records, skipped_duplicates = _stratified_select_records(
            selected_symbols,
            limit,
            lookahead,
            min_history,
            source_path,
            emitted_hashes,
            clean_year_focus,
            clean_max_per_symbol,
            clean_max_per_year,
        )
    else:
        records, skipped_duplicates = _sequential_select_records(
            selected_symbols,
            limit,
            lookahead,
            min_history,
            source_path,
            emitted_hashes,
            clean_year_focus,
            clean_max_per_symbol,
            clean_max_per_year,
        )

    report = build_report(
        records,
        skipped_duplicates,
        dry_run,
        selected_symbols,
        source_dir=source_path,
        sampling_mode=clean_sampling_mode,
        year_focus=clean_year_focus,
        max_per_symbol=clean_max_per_symbol,
        max_per_year=clean_max_per_year,
    )
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
    parser.add_argument("--source-dir", type=Path, default=CACHE_DIR, help="Folder containing source candle CSV files")
    parser.add_argument(
        "--sampling-mode",
        choices=("sequential", "stratified"),
        default="sequential",
        help="Record selection mode; sequential preserves existing behavior.",
    )
    parser.add_argument("--year-focus", help="Comma-separated years to prefer/include, e.g. 2008,2020,2022,2024")
    parser.add_argument("--max-per-symbol", type=int, help="Maximum accepted records per symbol")
    parser.add_argument("--max-per-year", type=int, help="Maximum accepted records per year")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_feeder(
        symbols=args.symbols,
        limit=max(1, args.limit),
        lookahead=max(1, args.lookahead),
        min_history=max(60, args.min_history),
        dry_run=args.dry_run,
        source_dir=args.source_dir,
        sampling_mode=args.sampling_mode,
        year_focus=args.year_focus,
        max_per_symbol=args.max_per_symbol,
        max_per_year=args.max_per_year,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
