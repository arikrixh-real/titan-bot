import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from config.upstox_symbols import get_instrument_key
except Exception:
    get_instrument_key = None

try:
    from utils.market_hours import is_trade_window, is_trading_day
except Exception:
    is_trade_window = None
    is_trading_day = None


IST = ZoneInfo("Asia/Kolkata")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / "data" / "runtime"
STATUS_PATH = RUNTIME_DIR / "truth_gate_status.json"
SCAN_SELECTION_STATE_PATH = PROJECT_ROOT / "data" / "scan_selection_state.json"
LIVE_PRICE_STATUS_PATH = PROJECT_ROOT / "data" / "live_price_status.json"
SCANNER_STATUS_PATH = RUNTIME_DIR / "scanner_status.json"
OHLC_REFRESH_STATUS_PATH = RUNTIME_DIR / "ohlc_refresh_status.json"
OHLC_CACHE_DIR = PROJECT_ROOT / "data" / "cache"
ACTIVE_TRADES_CSV = PROJECT_ROOT / "data" / "journals" / "active_trades.csv"
TRADE_JOURNAL_CSV = PROJECT_ROOT / "data" / "journals" / "trade_journal.csv"

REQUIRED_OHLC_COLUMNS = {"Open", "High", "Low", "Close", "Volume"}
SAFE_SCANNER_PATH = "SCORED_DYNAMIC_50"
UNSAFE_SCANNER_PATH = "CACHED_RANDOM_FALLBACK"
UNSAFE_SOURCES = {"CACHE", "FALLBACK", "CACHED_RANDOM_FALLBACK", "UNKNOWN", "NONE"}
MARKET_OHLC_STALE_MINUTES = 45
MAX_CLOSED_MARKET_CACHE_AGE_HOURS = 24
RR_TARGET = 2.0
RR_TOLERANCE = 0.25


def now_ist():
    return datetime.now(IST)


def timestamp_ist():
    return now_ist().isoformat()


def _atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _read_json(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _read_csv_sample(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                return row
    except Exception:
        return {}
    return {}


def _status(status, reason=None, **extra):
    payload = {
        "status": status,
        "ok": status == "PASS",
        "reason": reason,
    }
    payload.update(extra)
    return payload


def _clean_symbol(symbol):
    return str(symbol or "").strip().upper().replace(".NS", "")


def _market_open(value=None):
    if is_trade_window is None:
        return False
    try:
        return bool(is_trade_window(value))
    except Exception:
        return False


def _trading_day(value=None):
    if is_trading_day is None:
        return now_ist().weekday() < 5
    try:
        return bool(is_trading_day(value))
    except Exception:
        return now_ist().weekday() < 5


def _parse_dt(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        for candidate in (text, text.replace(" ", "T")):
            try:
                parsed = datetime.fromisoformat(candidate)
                break
            except Exception:
                parsed = None
        if parsed is None:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y %H:%M:%S"):
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except Exception:
                    parsed = None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def _safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _df_columns(df):
    try:
        return {str(col).strip() for col in df.columns}
    except Exception:
        return set()


def _df_latest_timestamp(df):
    if df is None:
        return None
    for col in ("Datetime", "Date", "timestamp", "Timestamp", "time"):
        try:
            if col in df.columns and len(df[col]) > 0:
                parsed = _parse_dt(df[col].iloc[-1])
                if parsed:
                    return parsed
        except Exception:
            pass
    try:
        index_value = df.index[-1]
        return _parse_dt(index_value)
    except Exception:
        return None


def _file_age_hours(path):
    try:
        modified = datetime.fromtimestamp(Path(path).stat().st_mtime, tz=IST)
        return (now_ist() - modified).total_seconds() / 3600.0
    except Exception:
        return None


def _instrument_key(symbol):
    if get_instrument_key is None:
        return None
    try:
        return get_instrument_key(symbol)
    except Exception:
        return None


def validate_ohlc(symbol=None, df=None, path=None, now=None):
    now = now or now_ist()
    reasons = []
    stale = False
    columns = _df_columns(df)
    latest_dt = _df_latest_timestamp(df)
    source_path = str(path or "")

    if df is None and path:
        try:
            import pandas as pd

            df = pd.read_csv(path)
            columns = _df_columns(df)
            latest_dt = _df_latest_timestamp(df)
        except Exception as exc:
            return _status(
                "FAIL",
                f"OHLC_READ_FAILED:{type(exc).__name__}:{exc}",
                symbol=_clean_symbol(symbol),
                stale=True,
                source_path=source_path,
            )

    missing = sorted(REQUIRED_OHLC_COLUMNS - columns)
    if missing:
        reasons.append("OHLC_MISSING_COLUMNS:" + ",".join(missing))

    if df is None:
        reasons.append("OHLC_MISSING")

    age_minutes = None
    if latest_dt:
        age_minutes = round((now - latest_dt).total_seconds() / 60.0, 2)
    else:
        reasons.append("OHLC_LATEST_TIMESTAMP_MISSING")
        stale = True

    if _market_open(now):
        if latest_dt is None or latest_dt.date() != now.date() or (age_minutes is not None and age_minutes > MARKET_OHLC_STALE_MINUTES):
            stale = True
            reasons.append("OHLC_STALE_DURING_MARKET")
    else:
        age_hours = _file_age_hours(path) if path else None
        if age_hours is not None and age_hours > MAX_CLOSED_MARKET_CACHE_AGE_HOURS:
            stale = True
            reasons.append("OHLC_CACHE_FILE_STALE")

    status = "FAIL" if reasons else "PASS"
    return _status(
        status,
        ";".join(reasons) if reasons else None,
        symbol=_clean_symbol(symbol),
        columns=sorted(columns),
        latest_timestamp_ist=latest_dt.isoformat() if latest_dt else None,
        latest_age_minutes=age_minutes,
        stale=stale,
        source_path=source_path,
    )


def validate_market_data(symbol=None, df=None, price_result=None, ltp_source=None, ltp_status=None, path=None, now=None):
    now = now or now_ist()
    symbol = _clean_symbol(symbol)
    market_open = _market_open(now)
    reasons = []
    unsafe_sources = []

    instrument_key = _instrument_key(symbol) if symbol else None
    if symbol and not instrument_key:
        reasons.append("INVALID_INSTRUMENT_KEY")

    if price_result is None:
        price_result = {}
    if isinstance(price_result, dict):
        source = str(ltp_source or price_result.get("source") or "").strip().upper()
        status = str(ltp_status or price_result.get("status") or price_result.get("live_source_status") or "").strip().upper()
        price = _safe_float(price_result.get("price"))
    else:
        source = str(ltp_source or "").strip().upper()
        status = str(ltp_status or "").strip().upper()
        price = _safe_float(price_result)

    if not source:
        source = "UNKNOWN"
    if not status:
        status = "UNKNOWN"

    normalized_source = "UPSTOX_LIVE" if source == "UPSTOX" and status == "ACTIVE" else source
    if source in UNSAFE_SOURCES or "FALLBACK" in source or "CACHE" in source:
        unsafe_sources.append(source)

    if market_open:
        if not (source == "UPSTOX" and status == "ACTIVE" and price is not None and price > 0):
            reasons.append("LTP_NOT_UPSTOX_LIVE_DURING_MARKET")
    else:
        if status == "MARKET_CLOSED":
            reasons.append("MARKET_CLOSED_NOT_LIVE_SAFE")
        elif source in {"CACHE", "UNKNOWN", "NONE"}:
            reasons.append("NON_LIVE_LTP_OUTSIDE_MARKET")

    ohlc = validate_ohlc(symbol=symbol, df=df, path=path, now=now) if (df is not None or path is not None) else _status("DEGRADED", "OHLC_NOT_PROVIDED", stale=False)
    if ohlc.get("status") == "FAIL":
        reasons.append(ohlc.get("reason") or "OHLC_INVALID")

    status_value = "PASS"
    if reasons:
        status_value = "FAIL" if market_open or any("OHLC" in reason or "INSTRUMENT" in reason for reason in reasons) else "DEGRADED"

    return _status(
        status_value,
        ";".join(reasons) if reasons else None,
        symbol=symbol,
        market_open=market_open,
        trading_day=_trading_day(now),
        ltp_source=normalized_source,
        raw_ltp_source=source,
        ltp_status=status,
        price=price,
        instrument_key=instrument_key,
        ohlc=ohlc,
        unsafe_sources_detected=unsafe_sources,
        stale_data_detected=bool(ohlc.get("stale")),
        live_action_allowed=status_value == "PASS",
    )


def validate_scanner_path(runtime_path=None, live_mode=True, detail=None):
    runtime_path = str(runtime_path or "").strip().upper()
    if not runtime_path:
        runtime_path = detect_scanner_runtime_path()
    runtime_path = str(runtime_path or "").strip().upper()
    if runtime_path == SAFE_SCANNER_PATH:
        return _status("PASS", None, runtime_path=runtime_path, live_mode=live_mode)
    reason = "RUNTIME_NOT_USING_SCORED_DYNAMIC_50"
    status_value = "FAIL" if live_mode else "DEGRADED"
    return _status(
        status_value,
        reason,
        runtime_path=runtime_path or "UNKNOWN",
        live_mode=live_mode,
        detail=detail,
        unsafe_sources_detected=[runtime_path or "UNKNOWN"],
    )


def detect_scanner_runtime_path():
    selection_state = _read_json(SCAN_SELECTION_STATE_PATH)
    selector = str(selection_state.get("selector") or selection_state.get("runtime_path") or "").upper()
    if selector == SAFE_SCANNER_PATH:
        return SAFE_SCANNER_PATH
    scanner_status = _read_json(SCANNER_STATUS_PATH)
    mode = str(scanner_status.get("mode") or "").upper()
    if "SCORED_DYNAMIC_50" in mode:
        return SAFE_SCANNER_PATH
    if selection_state.get("selected_symbols") or scanner_status:
        return UNSAFE_SCANNER_PATH
    return "UNKNOWN"


def _side(setup):
    raw = str((setup or {}).get("side") or (setup or {}).get("direction") or "").strip().upper()
    if raw == "LONG":
        return "BUY"
    if raw == "SHORT":
        return "SELL"
    return raw


def validate_trade_setup(setup):
    setup = setup if isinstance(setup, dict) else {}
    reasons = []
    symbol = _clean_symbol(setup.get("symbol") or setup.get("stock") or setup.get("ticker"))
    side = _side(setup)
    entry = _safe_float(setup.get("entry") or setup.get("entry_price"))
    stop_loss = _safe_float(setup.get("stop_loss") or setup.get("sl") or setup.get("stoploss"))
    target = _safe_float(setup.get("target") or setup.get("tp") or setup.get("target_price") or setup.get("t1"))
    rr = _safe_float(setup.get("rr") or setup.get("risk_reward"))
    final_score = setup.get("final_score")
    reason_text = str(setup.get("reason") or setup.get("setup_reason") or "").strip()

    if not symbol:
        reasons.append("SYMBOL_MISSING")
    elif not _instrument_key(symbol):
        reasons.append("INVALID_INSTRUMENT_KEY")
    if side not in {"BUY", "SELL"}:
        reasons.append("SIDE_NOT_BUY_SELL")
    if entry is None or entry <= 0:
        reasons.append("ENTRY_INVALID")
    if stop_loss is None or stop_loss <= 0:
        reasons.append("STOP_LOSS_INVALID")
    if target is None or target <= 0:
        reasons.append("TARGET_INVALID")
    if side == "BUY" and entry and stop_loss and target and not (stop_loss < entry < target):
        reasons.append("BUY_LEVEL_ORDER_INVALID")
    if side == "SELL" and entry and stop_loss and target and not (target < entry < stop_loss):
        reasons.append("SELL_LEVEL_ORDER_INVALID")
    if rr is None and entry and stop_loss and target:
        risk = abs(entry - stop_loss)
        reward = abs(target - entry)
        rr = reward / risk if risk > 0 else None
    if rr is None or abs(rr - RR_TARGET) > RR_TOLERANCE:
        reasons.append("RR_NOT_CLOSE_TO_2")
    if final_score is None or str(final_score).strip() == "":
        reasons.append("FINAL_SCORE_MISSING")
    if not reason_text:
        reasons.append("REASON_MISSING")

    return _status(
        "PASS" if not reasons else "FAIL",
        ";".join(reasons) if reasons else None,
        symbol=symbol,
        side=side,
        entry=entry,
        stop_loss=stop_loss,
        target=target,
        rr=round(rr, 4) if rr is not None else None,
        final_score=final_score,
    )


def validate_outcome_check(trade, price_result=None, source_table=None):
    trade = trade if isinstance(trade, dict) else {}
    reasons = []
    symbol = _clean_symbol(trade.get("symbol"))
    side = _side(trade)
    entry = _safe_float(trade.get("entry") or trade.get("entry_price"))
    stop_loss = _safe_float(trade.get("stop_loss") or trade.get("sl") or trade.get("stoploss"))
    target = _safe_float(trade.get("target") or trade.get("tp"))
    status_text = str(trade.get("status") or "").strip().upper()
    known_table = str(source_table or "").strip() in {"active_trades", "trades", "trade_results"}

    if not symbol:
        reasons.append("SYMBOL_MISSING")
    if side not in {"BUY", "SELL"}:
        reasons.append("SIDE_NOT_BUY_SELL")
    if entry is None or entry <= 0:
        reasons.append("ENTRY_INVALID")
    if stop_loss is None or stop_loss <= 0:
        reasons.append("STOP_LOSS_INVALID")
    if target is None or target <= 0:
        reasons.append("TARGET_INVALID")
    if status_text != "OPEN":
        reasons.append("TRADE_NOT_OPEN")
    if not known_table:
        reasons.append("UNKNOWN_SOURCE_TABLE")

    market_result = validate_market_data(symbol=symbol, price_result=price_result)
    if _market_open() and market_result.get("status") != "PASS":
        reasons.append("CURRENT_PRICE_NOT_REAL_LIVE")

    return _status(
        "PASS" if not reasons else "FAIL",
        ";".join(reasons) if reasons else None,
        symbol=symbol,
        side=side,
        source_table=source_table,
        market_data=market_result,
    )


def _component_status(previous, key):
    component = previous.get(key) if isinstance(previous, dict) else None
    return component if isinstance(component, dict) else _status("DEGRADED", "NOT_RUN")


def build_status(
    market_data_status=None,
    scanner_path_status=None,
    trade_validation_status=None,
    outcome_validation_status=None,
    recommended_next_action=None,
):
    previous = _read_json(STATUS_PATH)
    components = {
        "market_data_status": market_data_status or _component_status(previous, "market_data_status"),
        "scanner_path_status": scanner_path_status or _component_status(previous, "scanner_path_status"),
        "trade_validation_status": trade_validation_status or _component_status(previous, "trade_validation_status"),
        "outcome_validation_status": outcome_validation_status or _component_status(previous, "outcome_validation_status"),
    }

    statuses = [str(item.get("status") or "DEGRADED").upper() for item in components.values()]
    if "FAIL" in statuses:
        overall = "FAIL"
    elif "DEGRADED" in statuses:
        overall = "DEGRADED"
    else:
        overall = "PASS"

    reasons = []
    unsafe = []
    stale = False
    for item in components.values():
        reason = item.get("reason")
        if reason:
            reasons.append(reason)
        unsafe.extend(item.get("unsafe_sources_detected") or [])
        nested_market = item.get("market_data") if isinstance(item.get("market_data"), dict) else {}
        unsafe.extend(nested_market.get("unsafe_sources_detected") or [])
        stale = stale or bool(item.get("stale_data_detected")) or bool(nested_market.get("stale_data_detected"))

    if recommended_next_action is None:
        if overall == "PASS":
            recommended_next_action = "NONE"
        elif any("RUNTIME_NOT_USING_SCORED_DYNAMIC_50" in reason for reason in reasons):
            recommended_next_action = "WIRE_RUNTIME_SCANNER_TO_SCORED_DYNAMIC_50"
        elif any("LTP_NOT_UPSTOX_LIVE_DURING_MARKET" in reason for reason in reasons):
            recommended_next_action = "RESTORE_UPSTOX_LIVE_LTP_BEFORE_SCANNER_OR_OUTCOME"
        elif stale:
            recommended_next_action = "REFRESH_OHLC_WITH_LIVE_UPSTOX_DATA"
        else:
            recommended_next_action = "INSPECT_TRUTH_GATE_FAILURES"

    return {
        "timestamp_ist": timestamp_ist(),
        "overall_status": overall,
        "blocked_reason": ";".join(dict.fromkeys(reasons)) if reasons else None,
        "market_data_status": components["market_data_status"],
        "scanner_path_status": components["scanner_path_status"],
        "trade_validation_status": components["trade_validation_status"],
        "outcome_validation_status": components["outcome_validation_status"],
        "unsafe_sources_detected": sorted(set(str(item) for item in unsafe if item)),
        "stale_data_detected": stale,
        "recommended_next_action": recommended_next_action,
    }


def write_status(**kwargs):
    payload = build_status(**kwargs)
    _atomic_write_json(STATUS_PATH, payload)
    return payload


def block_reason_for_setup_engine(scan_path=None, market_status=None):
    scanner_status = validate_scanner_path(scan_path or UNSAFE_SCANNER_PATH, live_mode=True)
    if market_status is None:
        market_status = validate_market_data()
    status_payload = write_status(
        market_data_status=market_status,
        scanner_path_status=scanner_status,
    )
    return status_payload.get("overall_status") != "PASS", status_payload.get("blocked_reason"), status_payload


def scanner_gate_status(runtime_path=None, market_status=None):
    scanner_status = validate_scanner_path(runtime_path or UNSAFE_SCANNER_PATH, live_mode=True)
    status_payload = write_status(
        market_data_status=market_status,
        scanner_path_status=scanner_status,
    )
    return status_payload


def audit_snapshot():
    scanner_path_status = validate_scanner_path(detect_scanner_runtime_path(), live_mode=True)
    live_price_status = _read_json(LIVE_PRICE_STATUS_PATH)
    market_data_status = validate_market_data(
        symbol=live_price_status.get("symbol"),
        price_result=live_price_status,
    )

    ohlc_files = sorted(OHLC_CACHE_DIR.glob("*.csv"))[:5]
    ohlc_samples = [validate_ohlc(symbol=path.stem, path=path) for path in ohlc_files]
    if not ohlc_samples:
        ohlc_status = _status("FAIL", "NO_OHLC_CACHE_FILES", samples=[])
    elif any(sample.get("status") == "FAIL" for sample in ohlc_samples):
        ohlc_status = _status("FAIL", "ONE_OR_MORE_OHLC_SAMPLES_INVALID", samples=ohlc_samples)
    else:
        ohlc_status = _status("PASS", None, samples=ohlc_samples)

    trade_sample = _read_csv_sample(TRADE_JOURNAL_CSV) or _read_csv_sample(ACTIVE_TRADES_CSV)
    trade_validation_status = validate_trade_setup(trade_sample) if trade_sample else _status("DEGRADED", "NO_TRADE_SAMPLE")

    outcome_sample = _read_csv_sample(ACTIVE_TRADES_CSV)
    outcome_validation_status = validate_outcome_check(
        outcome_sample,
        price_result=live_price_status,
        source_table="active_trades",
    ) if outcome_sample else _status("DEGRADED", "NO_OUTCOME_SAMPLE")

    status_payload = write_status(
        market_data_status=market_data_status,
        scanner_path_status=scanner_path_status,
        trade_validation_status=trade_validation_status,
        outcome_validation_status=outcome_validation_status,
    )
    return {
        "truth_gate_status": status_payload,
        "market_data": market_data_status,
        "ohlc_freshness": ohlc_status,
        "scanner_path": scanner_path_status,
        "trade_validation_sample": trade_validation_status,
        "outcome_validation_sample": outcome_validation_status,
    }
