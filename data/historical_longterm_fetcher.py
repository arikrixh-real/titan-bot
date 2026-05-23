import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.universe import NSE_STOCKS


DEFAULT_PERIOD = "20y"
DEFAULT_INTERVAL = "1d"
OUTPUT_DIR = Path("data") / "historical_longterm"
REPORT_PATH = OUTPUT_DIR / "historical_longterm_fetch_report.json"
OUTPUT_COLUMNS = ["Datetime", "Open", "High", "Low", "Close", "Volume"]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Safely fetch long-term NSE OHLCV data into data/historical_longterm."
    )
    parser.add_argument("--period", default=DEFAULT_PERIOD, help="yfinance period, default: 20y")
    parser.add_argument("--interval", default=DEFAULT_INTERVAL, help="yfinance interval, default: 1d")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of symbols to fetch")
    parser.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated NSE symbols. Accepts INFY or INFY.NS format.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print intended work without writing files")
    return parser.parse_args()


def normalize_symbol(symbol):
    clean = str(symbol).strip().upper()
    if not clean:
        return ""
    return clean if clean.endswith(".NS") else f"{clean}.NS"


def output_symbol_name(symbol):
    return normalize_symbol(symbol).replace(".NS", "")


def selected_symbols(symbols_arg, limit):
    if symbols_arg:
        raw_symbols = symbols_arg.split(",")
    else:
        raw_symbols = NSE_STOCKS

    symbols = []
    seen = set()
    for raw_symbol in raw_symbols:
        symbol = normalize_symbol(raw_symbol)
        if symbol and symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)

    if limit is not None:
        if limit < 0:
            raise ValueError("--limit must be zero or greater")
        symbols = symbols[:limit]

    return symbols


def flatten_columns(df):
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = [
            next((str(part) for part in column if str(part) in OUTPUT_COLUMNS), str(column[0]))
            for column in df.columns
        ]
    return df


def normalize_ohlcv(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    df = flatten_columns(df)
    normalized = df.reset_index()

    index_column = normalized.columns[0]
    normalized = normalized.rename(columns={index_column: "Datetime"})

    missing_columns = [column for column in OUTPUT_COLUMNS if column not in normalized.columns]
    if missing_columns:
        raise ValueError(f"download missing required columns: {', '.join(missing_columns)}")

    normalized = normalized[OUTPUT_COLUMNS].copy()
    normalized["Datetime"] = pd.to_datetime(normalized["Datetime"], errors="coerce")
    normalized = normalized.dropna(subset=["Datetime"])
    return normalized


def fetch_symbol(symbol, period, interval):
    print(f"Fetching {symbol} ({period}, {interval})...")
    return yf.download(
        symbol,
        period=period,
        interval=interval,
        progress=False,
        auto_adjust=False,
        threads=False,
    )


def report_entry(symbol, status, rows=0, path=None, error=None):
    entry = {
        "symbol": symbol,
        "output_symbol": output_symbol_name(symbol),
        "status": status,
        "rows": rows,
    }
    if path is not None:
        entry["path"] = str(path)
    if error is not None:
        entry["error"] = str(error)
    return entry


def write_report(report):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")


def fetch_and_save_longterm(period=DEFAULT_PERIOD, interval=DEFAULT_INTERVAL, limit=None, symbols_arg=None, dry_run=False):
    symbols = selected_symbols(symbols_arg, limit)
    print(f"Selected {len(symbols)} symbol(s).")

    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "period": period,
        "interval": interval,
        "dry_run": dry_run,
        "output_dir": str(OUTPUT_DIR),
        "symbols_requested": len(symbols),
        "saved": 0,
        "empty": 0,
        "failed": 0,
        "entries": [],
    }

    if dry_run:
        for symbol in symbols:
            target_path = OUTPUT_DIR / f"{output_symbol_name(symbol)}.csv"
            print(f"DRY RUN: would fetch {symbol} -> {target_path}")
            report["entries"].append(report_entry(symbol, "dry_run", path=target_path))
        print("DRY RUN: no files written.")
        return report

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for position, symbol in enumerate(symbols, start=1):
        target_path = OUTPUT_DIR / f"{output_symbol_name(symbol)}.csv"
        print(f"[{position}/{len(symbols)}] Target: {target_path}")

        try:
            raw_df = fetch_symbol(symbol, period, interval)
            df = normalize_ohlcv(raw_df)

            if df.empty:
                print(f"Skipped {symbol}: empty download.")
                report["empty"] += 1
                report["entries"].append(report_entry(symbol, "empty", path=target_path))
                continue

            df.to_csv(target_path, index=False)
            print(f"Saved {len(df)} rows -> {target_path}")
            report["saved"] += 1
            report["entries"].append(report_entry(symbol, "saved", rows=len(df), path=target_path))

        except Exception as exc:
            print(f"Failed {symbol}: {exc}")
            report["failed"] += 1
            report["entries"].append(report_entry(symbol, "failed", path=target_path, error=exc))

    write_report(report)
    print(f"Report saved -> {REPORT_PATH}")
    return report


def main():
    args = parse_args()
    fetch_and_save_longterm(
        period=args.period,
        interval=args.interval,
        limit=args.limit,
        symbols_arg=args.symbols,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
