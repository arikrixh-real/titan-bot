import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.ohlc_health import ensure_fresh_ohlc, get_cache_file  # noqa: E402


PROOF_SYMBOLS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]


def main():
    result = ensure_fresh_ohlc(PROOF_SYMBOLS, max_age_hours=24)
    print(f"OHLC HEALTH STATUS: {result.get('status')}")
    print(f"Reason: {result.get('reason')}")
    print()
    for item in result.get("symbol_results", []):
        symbol = item.get("symbol")
        freshness = item.get("freshness") or {}
        refresh = item.get("refresh_result") or {}
        print(f"{symbol}")
        print(f"- cache_file: {get_cache_file(symbol)}")
        print(f"- rows: {freshness.get('rows')}")
        print(f"- latest_candle_timestamp: {freshness.get('latest_candle_timestamp')}")
        print(f"- age_hours: {freshness.get('age_hours')}")
        print(f"- status: {freshness.get('status')}")
        print(f"- reason: {freshness.get('reason')}")
        print(f"- refresh_attempted: {'yes' if item.get('refresh_attempted') else 'no'}")
        print(f"- refresh_result: {refresh.get('status') if refresh else 'NOT_ATTEMPTED'}")
        if refresh.get("reason"):
            print(f"- refresh_reason: {refresh.get('reason')}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
