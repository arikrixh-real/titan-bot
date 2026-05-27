import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from config.upstox_symbols import normalize_symbol


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
RUNTIME_HEALTH_PATH = PROJECT_ROOT / "data" / "runtime" / "ohlc_health.json"
REQUIRED_COLUMNS = {"Open", "High", "Low", "Close", "Volume"}
IST = ZoneInfo("Asia/Kolkata")


def _now_ist():
    return datetime.now(IST)


def _timestamp_ist():
    return _now_ist().isoformat()


def _clean_symbol(symbol):
    return normalize_symbol(symbol)


def _yfinance_symbol(symbol):
    clean = _clean_symbol(symbol)
    return clean if clean.endswith(".NS") else f"{clean}.NS"


def _safe_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def get_cache_file(symbol):
    return CACHE_DIR / f"{_clean_symbol(symbol)}.csv"


def _parse_timestamp(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text or text.lower() in {"nan", "nat"}:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text.replace(" ", "T"))
        except Exception:
            try:
                parsed = pd.to_datetime(text, errors="coerce").to_pydatetime()
            except Exception:
                parsed = None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def _latest_timestamp(df):
    if df is None or df.empty:
        return None
    for column in ("Datetime", "Date", "timestamp", "Timestamp", "time"):
        if column in df.columns:
            for value in reversed(df[column].tolist()):
                parsed = _parse_timestamp(value)
                if parsed is not None:
                    return parsed
    try:
        return _parse_timestamp(df.index[-1])
    except Exception:
        return None


def _read_cache_df(symbol):
    path = get_cache_file(symbol)
    if not path.exists():
        return None, path, "CACHE_FILE_MISSING"
    try:
        return pd.read_csv(path), path, None
    except Exception as exc:
        return None, path, f"CACHE_READ_FAILED:{type(exc).__name__}:{exc}"


def validate_ohlc_df(df, symbol, max_age_hours=24):
    reasons = []
    rows = 0 if df is None else len(df)
    columns = [] if df is None else [str(column).strip() for column in df.columns]

    if df is None:
        reasons.append("OHLC_DF_MISSING")
    elif df.empty:
        reasons.append("OHLC_EMPTY_ROWS")

    missing_columns = sorted(REQUIRED_COLUMNS - set(columns))
    if missing_columns:
        reasons.append("OHLC_MISSING_COLUMNS:" + ",".join(missing_columns))

    latest_dt = _latest_timestamp(df)
    age_hours = None
    if latest_dt is None:
        reasons.append("LATEST_CANDLE_TIMESTAMP_MISSING")
    else:
        age_hours = round((_now_ist() - latest_dt).total_seconds() / 3600.0, 4)
        if age_hours > max_age_hours:
            reasons.append(f"OHLC_STALE:{age_hours}h>{max_age_hours}h")

    close_last = None
    if df is not None and "Close" in df.columns and not df.empty:
        close_series = pd.to_numeric(df["Close"], errors="coerce").dropna()
        close_last = _safe_float(close_series.iloc[-1]) if not close_series.empty else None
        if close_last is None or close_last <= 0:
            reasons.append("CLOSE_INVALID")
    elif df is not None:
        reasons.append("CLOSE_INVALID")

    volume_nonzero = None
    if df is not None and "Volume" in df.columns and not df.empty:
        volume_series = pd.to_numeric(df["Volume"], errors="coerce").fillna(0)
        volume_nonzero = bool((volume_series > 0).any())
        if not volume_nonzero:
            reasons.append("VOLUME_ALL_ZERO_OR_MISSING")
    elif df is not None:
        reasons.append("VOLUME_ALL_ZERO_OR_MISSING")

    status = "PASS" if not reasons else "FAIL"
    return {
        "symbol": _clean_symbol(symbol),
        "status": status,
        "reason": None if status == "PASS" else ";".join(reasons),
        "rows": rows,
        "columns": columns,
        "missing_columns": missing_columns,
        "latest_candle_timestamp": latest_dt.isoformat() if latest_dt else None,
        "age_hours": age_hours,
        "max_age_hours": max_age_hours,
        "close_last": close_last,
        "volume_nonzero": volume_nonzero,
    }


def get_ohlc_freshness(symbol, max_age_hours=24):
    df, path, error = _read_cache_df(symbol)
    result = validate_ohlc_df(df, symbol, max_age_hours=max_age_hours)
    result["cache_file"] = str(path)
    result["file_exists"] = path.exists()
    if error:
        result["status"] = "FAIL"
        result["reason"] = error if not result.get("reason") else f"{error};{result['reason']}"
    return result


def refresh_ohlc_cache(symbol, force=False):
    before = get_ohlc_freshness(symbol)
    if before.get("status") == "PASS" and not force:
        return {
            "symbol": _clean_symbol(symbol),
            "attempted": False,
            "status": "SKIPPED_FRESH",
            "reason": None,
            "source": "CACHE",
            "before": before,
            "after": before,
        }

    upstox_result = {}
    try:
        from data.upstox_ohlc import refresh_symbol_from_upstox

        upstox_result = refresh_symbol_from_upstox(_clean_symbol(symbol))
    except Exception as exc:
        upstox_result = {
            "status": "UPSTOX_EXCEPTION",
            "reason": f"{type(exc).__name__}:{exc}",
            "source": "UPSTOX",
        }

    yfinance_result = {}
    if upstox_result.get("status") != "OK":
        try:
            from scripts.refresh_ohlc_cache import refresh_ohlc_cache as refresh_yfinance_cache

            yfinance_result = refresh_yfinance_cache(
                symbols=[_yfinance_symbol(symbol)],
                pause_seconds=0,
            )
        except Exception as exc:
            yfinance_result = {
                "status": "YFINANCE_EXCEPTION",
                "reason": f"{type(exc).__name__}:{exc}",
            }

    after = get_ohlc_freshness(symbol)
    refreshed = after.get("status") == "PASS"
    source = "UPSTOX" if upstox_result.get("status") == "OK" else "YFINANCE_FALLBACK"
    reason = None if refreshed else (
        f"upstox={upstox_result.get('status')}:{upstox_result.get('reason')};"
        f"yfinance={yfinance_result.get('status') or yfinance_result.get('refreshed')}:{yfinance_result.get('reason') or yfinance_result.get('error_message')}"
    )
    return {
        "symbol": _clean_symbol(symbol),
        "attempted": True,
        "status": "REFRESHED" if refreshed else "FAILED",
        "reason": reason,
        "source": source,
        "upstox_result": {k: v for k, v in upstox_result.items() if k != "dataframe"},
        "yfinance_result": yfinance_result,
        "before": before,
        "after": after,
    }


def ensure_fresh_ohlc(symbols, max_age_hours=24):
    clean_symbols = []
    seen = set()
    for symbol in symbols or []:
        clean = _clean_symbol(symbol)
        if clean and clean not in seen:
            clean_symbols.append(clean)
            seen.add(clean)

    results = []
    valid_symbols = []
    invalid_symbols = []
    refreshed_count = 0
    refresh_attempted_count = 0

    for symbol in clean_symbols:
        freshness = get_ohlc_freshness(symbol, max_age_hours=max_age_hours)
        refresh_result = None
        if freshness.get("status") != "PASS":
            refresh_result = refresh_ohlc_cache(symbol, force=True)
            refresh_attempted_count += 1
            if refresh_result.get("status") == "REFRESHED":
                refreshed_count += 1
            freshness = get_ohlc_freshness(symbol, max_age_hours=max_age_hours)

        valid = freshness.get("status") == "PASS"
        if valid:
            valid_symbols.append(symbol)
        else:
            invalid_symbols.append(symbol)

        results.append(
            {
                "symbol": symbol,
                "valid": valid,
                "freshness": freshness,
                "refresh_attempted": refresh_result is not None,
                "refresh_result": refresh_result,
            }
        )

    requested = len(clean_symbols)
    invalid_count = len(invalid_symbols)
    invalid_ratio = round(invalid_count / requested, 4) if requested else 1.0
    too_many_invalid = bool(requested and invalid_ratio > 0.15)
    status = "PASS" if requested and not too_many_invalid and invalid_count == 0 else "FAIL"
    reason = None
    if not requested:
        reason = "NO_SYMBOLS_REQUESTED"
    elif invalid_count:
        reason = f"OHLC_INVALID_SYMBOLS:{invalid_count}/{requested}"
    payload = {
        "timestamp_ist": _timestamp_ist(),
        "status": status,
        "reason": reason,
        "max_age_hours": max_age_hours,
        "requested_count": requested,
        "valid_count": len(valid_symbols),
        "invalid_count": invalid_count,
        "invalid_ratio": invalid_ratio,
        "too_many_invalid": too_many_invalid,
        "refresh_attempted_count": refresh_attempted_count,
        "refreshed_count": refreshed_count,
        "valid_symbols": valid_symbols,
        "invalid_symbols": invalid_symbols,
        "symbol_results": results,
    }
    _atomic_write_json(RUNTIME_HEALTH_PATH, payload)
    return payload
