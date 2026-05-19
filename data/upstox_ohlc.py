import json
import os
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

from config.upstox_symbols import get_instrument_key, normalize_symbol
from data.live_price import get_upstox_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
UPSTOX_INTRADAY_CANDLE_URL = (
    "https://api.upstox.com/v3/historical-candle/intraday"
)


def _clean_symbol(symbol):
    return normalize_symbol(symbol)


def _cache_path(symbol):
    return CACHE_DIR / f"{_clean_symbol(symbol)}.csv"


def _result(symbol, status, reason=None, **extra):
    payload = {
        "symbol": _clean_symbol(symbol),
        "status": status,
        "reason": reason,
        "source": "UPSTOX",
    }
    payload.update(extra)
    return payload


def _candles_to_frame(candles):
    rows = []
    for candle in candles:
        if not isinstance(candle, list) or len(candle) < 6:
            continue
        rows.append(
            {
                "Datetime": candle[0],
                "Open": candle[1],
                "High": candle[2],
                "Low": candle[3],
                "Close": candle[4],
                "Volume": candle[5],
            }
        )

    if not rows:
        return None

    df = pd.DataFrame(rows)
    parsed_dt = pd.to_datetime(df["Datetime"], errors="coerce")
    df = df.assign(_parsed_datetime=parsed_dt)
    df = df.dropna(subset=["_parsed_datetime"])
    if df.empty:
        return None

    for column in ["Open", "High", "Low", "Close", "Volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    if df.empty:
        return None

    df = df.sort_values("_parsed_datetime")
    df = df[["Datetime", "Open", "High", "Low", "Close", "Volume"]]
    return df


def fetch_upstox_intraday_ohlc(symbol, interval_minutes=15, timeout=10):
    clean_symbol = _clean_symbol(symbol)
    instrument_key = get_instrument_key(clean_symbol)
    if not instrument_key:
        return _result(clean_symbol, "UNMAPPED", "Instrument key missing")

    access_token, token_type_used = get_upstox_token()
    if not access_token:
        return _result(
            clean_symbol,
            "TOKEN_MISSING",
            "Upstox token missing",
            instrument_key=instrument_key,
            token_type_used=token_type_used,
        )

    encoded_key = quote(instrument_key, safe="")
    url = f"{UPSTOX_INTRADAY_CANDLE_URL}/{encoded_key}/minutes/{int(interval_minutes)}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(url, headers=headers, timeout=timeout)
    except Exception as exc:
        error_text = str(exc)
        if "WinError 10013" in error_text:
            status = "NETWORK_BLOCKED"
            reason = "Socket blocked while calling Upstox"
        elif "getaddrinfo failed" in error_text or "NameResolutionError" in error_text:
            status = "DNS_ERROR"
            reason = "DNS resolution failed while calling Upstox"
        else:
            status = "API_ERROR"
            reason = error_text
        return _result(
            clean_symbol,
            status,
            reason,
            instrument_key=instrument_key,
            token_type_used=token_type_used,
        )

    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = None
    except ValueError:
        payload = None

    if response.status_code != 200:
        message = str(payload) if payload is not None else response.text[:300]
        status = "TOKEN_INVALID" if response.status_code in {401, 403} else "HTTP_ERROR"
        return _result(
            clean_symbol,
            status,
            f"HTTP {response.status_code}: {message}",
            instrument_key=instrument_key,
            token_type_used=token_type_used,
        )

    if not isinstance(payload, dict):
        return _result(
            clean_symbol,
            "BAD_RESPONSE",
            "Upstox response was not JSON object",
            instrument_key=instrument_key,
            token_type_used=token_type_used,
        )

    candles = payload.get("data", {}).get("candles")
    if not isinstance(candles, list) or not candles:
        return _result(
            clean_symbol,
            "EMPTY_CANDLES",
            "Upstox returned no intraday candles",
            instrument_key=instrument_key,
            token_type_used=token_type_used,
        )

    df = _candles_to_frame(candles)
    if df is None or df.empty:
        return _result(
            clean_symbol,
            "EMPTY_NORMALIZED_DATA",
            "Upstox candles could not be normalized",
            instrument_key=instrument_key,
            token_type_used=token_type_used,
        )

    return _result(
        clean_symbol,
        "OK",
        None,
        instrument_key=instrument_key,
        token_type_used=token_type_used,
        dataframe=df,
        candle_count=len(df),
        latest_candle_timestamp=str(df["Datetime"].iloc[-1]),
    )


def refresh_symbol_from_upstox(symbol, interval_minutes=15, timeout=10):
    try:
        result = fetch_upstox_intraday_ohlc(
            symbol,
            interval_minutes=interval_minutes,
            timeout=timeout,
        )
    except Exception as exc:
        return _result(
            symbol,
            "API_ERROR",
            f"Upstox OHLC refresh failed before cache write: {exc}",
        )

    df = result.pop("dataframe", None)
    if result.get("status") != "OK" or df is None or df.empty:
        return result

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _cache_path(symbol)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        df.to_csv(temp_path, index=False)
        os.replace(temp_path, path)
        result["cache_path"] = str(path)
        return result
    except Exception as exc:
        return _result(
            symbol,
            "CACHE_WRITE_FAILED",
            f"Upstox cache write failed; previous cache left untouched: {exc}",
            instrument_key=result.get("instrument_key"),
            token_type_used=result.get("token_type_used"),
            candle_count=result.get("candle_count"),
            latest_candle_timestamp=result.get("latest_candle_timestamp"),
        )
