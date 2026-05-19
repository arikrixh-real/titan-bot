import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

YFINANCE_CACHE_DIR = PROJECT_ROOT / "data" / "yfinance_cache"
YFINANCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
try:
    yf.set_tz_cache_location(str(YFINANCE_CACHE_DIR))
except Exception:
    pass

from config.settings import DATA_INTERVAL, DATA_PERIOD
from config.universe import NSE_STOCKS


CACHE_DIR = PROJECT_ROOT / "data" / "cache"
YFINANCE_SYMBOL_ALIASES = {
    # Upstox currently lists the local legacy TATAMOTORS alias under TMPV.
    "TATAMOTORS.NS": "TMPV.NS",
}


def _clean_symbol(symbol):
    return str(symbol).replace(".NS", "").upper().strip()


def _download_symbol(symbol):
    return YFINANCE_SYMBOL_ALIASES.get(str(symbol).upper().strip(), symbol)


def _normalize_downloaded_frame(df):
    if df is None or df.empty:
        return None

    df = df.copy()

    if isinstance(df.columns, pd.MultiIndex):
        first_level = [str(col[0]) for col in df.columns]
        if set(first_level).issubset({"Open", "High", "Low", "Close", "Adj Close", "Volume"}):
            df.columns = first_level
        else:
            df.columns = [
                "_".join(str(part) for part in col if str(part) and str(part) != "nan")
                for col in df.columns
            ]

    df = df.dropna(how="all")
    if df.empty:
        return None

    return df


def _save_symbol_frame(symbol, df):
    df = _normalize_downloaded_frame(df)
    if df is None:
        return False

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{_clean_symbol(symbol)}.csv"
    df.to_csv(path, index_label="Datetime")
    return True


def refresh_ohlc_cache(symbols=None, pause_seconds=0.2):
    symbols = list(symbols or NSE_STOCKS)
    refreshed = []
    skipped = []
    failed = []
    symbol_results = []

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    for symbol in symbols:
        try:
            download_symbol = _download_symbol(symbol)
            alias_note = f" via {download_symbol}" if download_symbol != symbol else ""
            print(f"[OHLCRefresh] fetching {symbol}{alias_note}")
            df = yf.download(
                download_symbol,
                period=DATA_PERIOD,
                interval=DATA_INTERVAL,
                progress=False,
                threads=False,
            )

            if df is None or df.empty:
                skipped.append(symbol)
                symbol_results.append({
                    "symbol": symbol,
                    "status": "SKIPPED",
                    "reason": "YFINANCE_EMPTY_FRAME",
                })
                print(f"[OHLCRefresh] skipped {symbol}: no data")
                continue

            if _save_symbol_frame(symbol, df):
                refreshed.append(symbol)
                last_timestamp = None
                try:
                    last_timestamp = str(df.index[-1])
                except Exception:
                    last_timestamp = None
                symbol_results.append({
                    "symbol": symbol,
                    "status": "REFRESHED",
                    "reason": None,
                    "latest_candle_timestamp": last_timestamp,
                })
                print(f"[OHLCRefresh] refreshed {symbol}")
            else:
                skipped.append(symbol)
                symbol_results.append({
                    "symbol": symbol,
                    "status": "SKIPPED",
                    "reason": "EMPTY_NORMALIZED_DATA",
                })
                print(f"[OHLCRefresh] skipped {symbol}: empty normalized data")

            if pause_seconds > 0:
                time.sleep(pause_seconds)

        except Exception as exc:
            failed.append({"symbol": symbol, "error": str(exc)})
            symbol_results.append({
                "symbol": symbol,
                "status": "FAILED",
                "reason": str(exc),
            })
            print(f"[OHLCRefresh] failed {symbol}: {exc}")

    print("========== OHLC REFRESH SUMMARY ==========")
    print(f"Requested: {len(symbols)}")
    print(f"Refreshed: {len(refreshed)}")
    print(f"Skipped: {len(skipped)}")
    print(f"Failed: {len(failed)}")
    if skipped:
        print(f"Skipped symbols: {', '.join(skipped)}")
    if failed:
        print("Failed symbols:")
        for item in failed:
            print(f"- {item['symbol']}: {item['error']}")
    print("==========================================")

    return {
        "requested": len(symbols),
        "refreshed": len(refreshed),
        "skipped": len(skipped),
        "failed": len(failed),
        "symbol_results": symbol_results,
    }


def main():
    parser = argparse.ArgumentParser(description="Refresh TITAN OHLC cache files safely.")
    parser.add_argument(
        "--symbols",
        nargs="*",
        default=None,
        help="Optional symbols to refresh. Defaults to config.universe.NSE_STOCKS.",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.2,
        help="Small pause between yfinance calls.",
    )
    args = parser.parse_args()

    symbols = args.symbols if args.symbols else NSE_STOCKS
    refresh_ohlc_cache(symbols=symbols, pause_seconds=args.pause_seconds)


if __name__ == "__main__":
    main()
