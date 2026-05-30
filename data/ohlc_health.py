import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from config.upstox_symbols import normalize_symbol
from scripts.refresh_ohlc_cache import YFINANCE_SYMBOL_ALIASES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
RUNTIME_HEALTH_PATH = PROJECT_ROOT / "data" / "runtime" / "ohlc_health.json"
AUTHORITATIVE_OHLC_STATUS_PATH = RUNTIME_HEALTH_PATH
REQUIRED_COLUMNS = {"Open", "High", "Low", "Close", "Volume"}
REQUIRED_ROWS = 100
MINIMUM_ROWS = 60
IST = ZoneInfo("Asia/Kolkata")

OHLC_OWNERSHIP_CONTRACT = {
    "owner": "data.ohlc_health",
    "authoritative_status_path": "data/runtime/ohlc_health.json",
    "authoritative_for": [
        "ohlc_freshness",
        "ohlc_health",
        "scanner_ohlc_gate",
        "dashboard_ohlc_status",
    ],
    "diagnostic_only_paths": [
        "data/runtime/ohlc_refresh_status.json",
        "data/runtime/ohlc_freshness_status.json",
        "data/runtime/stale_symbol_diagnostics.json",
    ],
    "contract": (
        "Refresh modules may update data/cache CSVs and publish refresh telemetry, "
        "but runtime health consumers must read data/runtime/ohlc_health.json for "
        "OHLC freshness truth."
    ),
}


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


def ownership_contract():
    return dict(OHLC_OWNERSHIP_CONTRACT)


def publish_ohlc_health(payload, path=AUTHORITATIVE_OHLC_STATUS_PATH):
    authoritative = dict(payload or {})
    authoritative["ownership_contract"] = ownership_contract()
    authoritative["authoritative"] = True
    authoritative["authoritative_status_path"] = "data/runtime/ohlc_health.json"
    _atomic_write_json(path, authoritative)
    return authoritative


def read_authoritative_ohlc_health(path=AUTHORITATIVE_OHLC_STATUS_PATH):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def authoritative_ohlc_is_fresh(payload=None):
    health = payload if isinstance(payload, dict) else read_authoritative_ohlc_health()
    status = str(health.get("status") or "").upper()
    if status == "PASS":
        return True
    if status == "FAIL":
        return False
    return None


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


def _normalize_frame(df):
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
    if "Datetime" not in df.columns:
        df = df.reset_index()
        first = df.columns[0]
        if first != "Datetime":
            df = df.rename(columns={first: "Datetime"})
    df.columns = [str(column).strip() for column in df.columns]
    if "Date" in df.columns and "Datetime" not in df.columns:
        df = df.rename(columns={"Date": "Datetime"})
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        return None
    parsed = pd.to_datetime(df["Datetime"], errors="coerce", utc=True)
    df = df.assign(_parsed_datetime=parsed)
    df = df.dropna(subset=["_parsed_datetime"])
    for column in REQUIRED_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    if df.empty:
        return None
    df = df.sort_values("_parsed_datetime")
    df = df.drop_duplicates(subset=["_parsed_datetime"], keep="last")
    df["Datetime"] = df["_parsed_datetime"].apply(
        lambda value: value.isoformat() if hasattr(value, "isoformat") else str(value)
    )
    return df[["Datetime", "Open", "High", "Low", "Close", "Volume"]]


def _write_cache_df(symbol, df):
    normalized = _normalize_frame(df)
    if normalized is None or normalized.empty:
        return False
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = get_cache_file(symbol)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    normalized.to_csv(temp_path, index=False)
    os.replace(temp_path, path)
    return True


def _merge_with_existing_cache(symbol, new_df):
    existing, _path, _error = _read_cache_df(symbol)
    frames = []
    if existing is not None and not existing.empty:
        frames.append(existing)
    if new_df is not None and not new_df.empty:
        frames.append(new_df)
    if not frames:
        return False
    merged = pd.concat(frames, ignore_index=True)
    return _write_cache_df(symbol, merged)


def validate_ohlc_df(df, symbol, max_age_hours=24):
    reasons = []
    rows = 0 if df is None else len(df)
    columns = [] if df is None else [str(column).strip() for column in df.columns]

    if df is None:
        reasons.append("OHLC_DF_MISSING")
    elif df.empty:
        reasons.append("OHLC_EMPTY_ROWS")
    elif rows < MINIMUM_ROWS:
        reasons.append("INSUFFICIENT_HISTORY_ROWS")
    elif rows < REQUIRED_ROWS:
        reasons.append("BELOW_IDEAL_HISTORY_ROWS")

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

    hard_fail_reasons = [
        reason for reason in reasons
        if not reason.startswith("BELOW_IDEAL_HISTORY_ROWS")
    ]
    if hard_fail_reasons:
        status = "FAIL"
    elif reasons:
        status = "DEGRADED"
    else:
        status = "PASS"
    return {
        "symbol": _clean_symbol(symbol),
        "status": status,
        "reason": None if status == "PASS" else ";".join(reasons),
        "rows": rows,
        "required_rows": REQUIRED_ROWS,
        "minimum_rows": MINIMUM_ROWS,
        "history_depth_status": (
            "PASS" if rows >= REQUIRED_ROWS else (
                "DEGRADED" if rows >= MINIMUM_ROWS else "FAIL"
            )
        ),
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
        from data.upstox_ohlc import fetch_upstox_intraday_ohlc

        upstox_result = fetch_upstox_intraday_ohlc(_clean_symbol(symbol))
        upstox_df = upstox_result.get("dataframe") if isinstance(upstox_result, dict) else None
        if upstox_result.get("status") == "OK" and upstox_df is not None:
            _merge_with_existing_cache(symbol, upstox_df)
    except Exception as exc:
        upstox_result = {
            "status": "UPSTOX_EXCEPTION",
            "reason": f"{type(exc).__name__}:{exc}",
            "source": "UPSTOX",
        }

    after_upstox = get_ohlc_freshness(symbol)
    yfinance_result = {}
    after_upstox_reason = str(after_upstox.get("reason") or "")
    upstox_status = upstox_result.get("status")
    upstox_failed_or_unmapped = upstox_status != "OK" or upstox_status == "UNMAPPED"
    cache_still_stale = "OHLC_STALE:" in after_upstox_reason
    if (
        after_upstox.get("rows", 0) < REQUIRED_ROWS
        or (upstox_failed_or_unmapped and cache_still_stale)
    ):
        yfinance_result = _refresh_from_yfinance(symbol)

    after = get_ohlc_freshness(symbol)
    refreshed = after.get("status") in {"PASS", "DEGRADED"}
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


def _refresh_from_yfinance(symbol):
    clean = _clean_symbol(symbol)
    yf_symbol = _yfinance_symbol(clean)
    yf_symbol = YFINANCE_SYMBOL_ALIASES.get(yf_symbol, yf_symbol)
    try:
        df = yf.download(
            yf_symbol,
            period="60d",
            interval="15m",
            progress=False,
            threads=False,
        )
        normalized = _normalize_frame(df)
        if normalized is None or normalized.empty:
            return {
                "status": "SKIPPED",
                "reason": "YFINANCE_EMPTY_FRAME",
                "symbol": clean,
                "download_symbol": yf_symbol,
                "rows": 0,
            }
        _merge_with_existing_cache(clean, normalized)
        return {
            "status": "REFRESHED",
            "reason": None,
            "symbol": clean,
            "download_symbol": yf_symbol,
            "rows": len(normalized),
            "period": "60d",
            "interval": "15m",
        }
    except Exception as exc:
        return {
            "status": "YFINANCE_EXCEPTION",
            "reason": f"{type(exc).__name__}:{exc}",
            "symbol": clean,
            "download_symbol": yf_symbol,
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

        valid = freshness.get("status") in {"PASS", "DEGRADED"}
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
    degraded_count = sum(
        1
        for item in results
        if (item.get("freshness") or {}).get("status") == "DEGRADED"
    )
    if requested and not too_many_invalid and invalid_count == 0 and degraded_count == 0:
        status = "PASS"
    elif requested and not too_many_invalid:
        status = "DEGRADED"
    else:
        status = "FAIL"
    reason = None
    if not requested:
        reason = "NO_SYMBOLS_REQUESTED"
    elif invalid_count:
        reason = f"OHLC_INVALID_SYMBOLS:{invalid_count}/{requested}"
    elif degraded_count:
        reason = f"OHLC_DEGRADED_HISTORY:{degraded_count}/{requested}"
    payload = {
        "timestamp_ist": _timestamp_ist(),
        "status": status,
        "reason": reason,
        "max_age_hours": max_age_hours,
        "requested_count": requested,
        "valid_count": len(valid_symbols),
        "invalid_count": invalid_count,
        "degraded_count": degraded_count,
        "invalid_ratio": invalid_ratio,
        "too_many_invalid": too_many_invalid,
        "refresh_attempted_count": refresh_attempted_count,
        "refreshed_count": refreshed_count,
        "valid_symbols": valid_symbols,
        "invalid_symbols": invalid_symbols,
        "symbol_results": results,
    }
    return publish_ohlc_health(payload)
