import json
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd


IST = timezone(timedelta(hours=5, minutes=30))
TREND_DIAGNOSTICS_PATH = Path("data") / "runtime" / "trend_diagnostics.json"
TREND_PIPELINE_DIAGNOSTICS_PATH = Path("data") / "runtime" / "trend_pipeline_diagnostics.json"
SIDEWAYS_ANALYSIS_PATH = Path("data") / "runtime" / "sideways_analysis.json"
ADAPTIVE_TREND_REPORT_PATH = Path("data") / "runtime" / "adaptive_trend_report.json"
ADAPTIVE_TREND_MIN_SCORE = 65.0
STRICT_TREND_REQUIRED_SCORE = 5
STRICT_TREND_CONDITION_COUNT = 6


def _timestamp_ist():
    return datetime.now(IST).isoformat()


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _round(value, digits=4):
    value = _safe_float(value)
    return round(value, digits) if value is not None else None


def _safe_series(df, column):
    try:
        if df is None or df.empty or column not in df.columns:
            return None
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        return series if len(series) else None
    except Exception:
        return None


def _ema(series, period):
    try:
        return series.ewm(span=period, adjust=False).mean()
    except Exception:
        return None


def _atr(high, low, close, period=14):
    try:
        if high is None or low is None or close is None or len(close) < period + 1:
            return None
        prev_close = close.shift(1)
        tr = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]
        return _safe_float(atr)
    except Exception:
        return None


def _adx(high, low, close, period=14):
    try:
        if high is None or low is None or close is None or len(close) < (period * 2) + 1:
            return None
        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
        prev_close = close.shift(1)
        tr = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(period).mean()
        plus_di = 100 * plus_dm.rolling(period).mean() / atr
        minus_di = 100 * minus_dm.rolling(period).mean() / atr
        dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, pd.NA)) * 100
        adx = dx.rolling(period).mean().iloc[-1]
        return _safe_float(adx)
    except Exception:
        return None


def _volatility_state(atr_pct):
    if atr_pct is None:
        return "UNKNOWN"
    if atr_pct < 0.8:
        return "COMPRESSED"
    if atr_pct > 3.0:
        return "EXPANDED"
    return "NORMAL"


def _side_from_direction(direction):
    if direction == "LONG":
        return "LONG"
    if direction == "SHORT":
        return "SHORT"
    return None


def _result_label(trend_result):
    trend = str(trend_result or "").upper()
    if trend in {"BULLISH", "UP", "UPTREND", "LONG"}:
        return "UP"
    if trend in {"BEARISH", "DOWN", "DOWNTREND", "SHORT"}:
        return "DOWN"
    return "SIDEWAYS"


def _failed_conditions(direction, conditions):
    labels = {
        "LONG": [
            ("price_above_ema20", "price not above EMA20"),
            ("ema20_above_ema50", "EMA20 not above EMA50"),
            ("ema20_slope_up", "EMA20 slope not up"),
            ("ema50_slope_up", "EMA50 slope not up"),
            ("close_not_below_previous", "close below previous close"),
            ("recent_high_break", "recent high not broken"),
        ],
        "SHORT": [
            ("price_below_ema20", "price not below EMA20"),
            ("ema20_below_ema50", "EMA20 not below EMA50"),
            ("ema20_slope_down", "EMA20 slope not down"),
            ("ema50_slope_down", "EMA50 slope not down"),
            ("close_not_above_previous", "close above previous close"),
            ("recent_low_break", "recent low not broken"),
        ],
    }
    return [label for key, label in labels[direction] if not conditions.get(key)]


def explain_trend(symbol, df, trend_result):
    close = _safe_series(df, "Close")
    high = _safe_series(df, "High")
    low = _safe_series(df, "Low")

    base = {
        "symbol": symbol,
        "trend_result": _result_label(trend_result),
        "ema20": None,
        "ema50": None,
        "ema_distance_pct": None,
        "price_vs_ema20": None,
        "price_vs_ema50": None,
        "slope_ema20": None,
        "slope_ema50": None,
        "adx": None,
        "atr": None,
        "atr_pct": None,
        "volatility_state": "UNKNOWN",
        "failed_conditions": [],
        "trend_reason": "insufficient data",
        "original_trend_pass": False,
        "adaptive_trend_pass": False,
        "adaptive_trend_score": 0.0,
        "adaptive_trend_reason": "insufficient data",
        "adaptive_accepted": False,
        "adaptive_side": None,
        "diagnostic_scores": {"long": 0, "short": 0, "best": 0},
        "conditions": {},
    }

    if close is None or high is None or low is None:
        base["failed_conditions"] = ["missing OHLC data"]
        return base
    if len(close) < 60:
        base["failed_conditions"] = ["less than 60 candles"]
        return base

    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    if ema20 is None or ema50 is None:
        base["failed_conditions"] = ["EMA calculation unavailable"]
        return base

    last_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    ema20_now = float(ema20.iloc[-1])
    ema50_now = float(ema50.iloc[-1])
    ema20_prev = float(ema20.iloc[-5])
    ema50_prev = float(ema50.iloc[-5])
    recent_high_now = float(high.iloc[-1])
    recent_high_prev = float(high.iloc[-6:-1].max())
    recent_low_now = float(low.iloc[-1])
    recent_low_prev = float(low.iloc[-6:-1].min())

    slope_ema20 = ema20_now - ema20_prev
    slope_ema50 = ema50_now - ema50_prev
    atr = _atr(high, low, close)
    atr_pct = (atr / last_close * 100.0) if atr is not None and last_close else None

    conditions = {
        "price_above_ema20": last_close > ema20_now,
        "ema20_above_ema50": ema20_now > ema50_now,
        "ema20_slope_up": ema20_now > ema20_prev,
        "ema50_slope_up": ema50_now > ema50_prev,
        "close_not_below_previous": last_close >= prev_close,
        "recent_high_break": recent_high_now >= recent_high_prev,
        "price_below_ema20": last_close < ema20_now,
        "ema20_below_ema50": ema20_now < ema50_now,
        "ema20_slope_down": ema20_now < ema20_prev,
        "ema50_slope_down": ema50_now < ema50_prev,
        "close_not_above_previous": last_close <= prev_close,
        "recent_low_break": recent_low_now <= recent_low_prev,
    }

    long_score = sum(
        bool(conditions[key])
        for key in (
            "price_above_ema20",
            "ema20_above_ema50",
            "ema20_slope_up",
            "ema50_slope_up",
            "close_not_below_previous",
            "recent_high_break",
        )
    )
    short_score = sum(
        bool(conditions[key])
        for key in (
            "price_below_ema20",
            "ema20_below_ema50",
            "ema20_slope_down",
            "ema50_slope_down",
            "close_not_above_previous",
            "recent_low_break",
        )
    )
    best_direction = "LONG" if long_score >= short_score else "SHORT"
    failed = _failed_conditions(best_direction, conditions)
    best_score = max(long_score, short_score)

    original_trend_pass = base["trend_result"] != "SIDEWAYS"
    if original_trend_pass:
        reason = f"{base['trend_result']} trend passed with score {best_score}/6"
        failed = []
    else:
        reason = f"best {best_direction.lower()} score {best_score}/6; needs 5/6"

    adaptive_score = round((best_score / 6.0) * 100.0, 2)

    base.update(
        {
            "ema20": _round(ema20_now, 4),
            "ema50": _round(ema50_now, 4),
            "ema_distance_pct": _round(abs(ema20_now - ema50_now) / last_close * 100.0, 4) if last_close else None,
            "price_vs_ema20": _round((last_close - ema20_now) / ema20_now * 100.0, 4) if ema20_now else None,
            "price_vs_ema50": _round((last_close - ema50_now) / ema50_now * 100.0, 4) if ema50_now else None,
            "slope_ema20": _round(slope_ema20, 4),
            "slope_ema50": _round(slope_ema50, 4),
            "adx": _round(_adx(high, low, close), 4),
            "atr": _round(atr, 4),
            "atr_pct": _round(atr_pct, 4),
            "volatility_state": _volatility_state(atr_pct),
            "failed_conditions": failed,
            "trend_reason": reason,
            "original_trend_pass": original_trend_pass,
            "adaptive_trend_pass": original_trend_pass,
            "adaptive_trend_score": adaptive_score if not original_trend_pass else 100.0,
            "adaptive_trend_reason": "strict trend pass" if original_trend_pass else reason,
            "adaptive_accepted": False,
            "adaptive_side": _side_from_direction(best_direction) if original_trend_pass else None,
            "diagnostic_scores": {
                "long": long_score,
                "short": short_score,
                "best": best_score,
                "best_direction": best_direction,
            },
            "conditions": conditions,
        }
    )
    return base


def _text_contains_any(value, keywords):
    text = json.dumps(value, default=str).upper() if isinstance(value, (dict, list)) else str(value or "").upper()
    return any(keyword in text for keyword in keywords)


def _dangerous_regime(regime_diagnostics):
    status = (regime_diagnostics or {}).get("market_status") if isinstance(regime_diagnostics, dict) else {}
    if isinstance(status, dict) and status.get("market_ok") is False:
        return True, "market_status market_ok=false"
    if _text_contains_any(status, ("PANIC", "CRASH", "RISK_OFF", "LIQUIDITY_CRISIS", "VOLATILITY_SPIKE")):
        return True, "dangerous market regime"
    return False, ""


def _strong_ema_opposite(item, direction):
    conditions = item.get("conditions") or {}
    ema_distance = _safe_float(item.get("ema_distance_pct"), 0.0) or 0.0
    if direction == "LONG" and conditions.get("ema20_below_ema50") and ema_distance >= 0.5:
        return True
    if direction == "SHORT" and conditions.get("ema20_above_ema50") and ema_distance >= 0.5:
        return True
    return False


def _strong_structure_opposite(item, direction):
    conditions = item.get("conditions") or {}
    if direction == "LONG":
        return bool(conditions.get("recent_low_break") and not conditions.get("recent_high_break"))
    if direction == "SHORT":
        return bool(conditions.get("recent_high_break") and not conditions.get("recent_low_break"))
    return False


def _volatility_panic(item, regime_diagnostics):
    atr_pct = _safe_float(item.get("atr_pct"), 0.0) or 0.0
    status = (regime_diagnostics or {}).get("market_status") if isinstance(regime_diagnostics, dict) else {}
    return bool(atr_pct >= 5.0 or _text_contains_any(status, ("VOLATILITY_SPIKE", "PANIC_VOLATILITY", "PANIC")))


def _liquidity_or_manipulation_warning_high(regime_diagnostics):
    status = (regime_diagnostics or {}).get("market_status") if isinstance(regime_diagnostics, dict) else {}
    return _text_contains_any(status, ("LIQUIDITY_CRISIS", "MANIPULATION_HIGH", "HIGH_MANIPULATION"))


def apply_adaptive_trend(item, regime_diagnostics=None):
    result = dict(item or {})
    original_pass = bool(result.get("original_trend_pass"))
    best_score = int((result.get("diagnostic_scores") or {}).get("best") or 0)
    best_direction = (result.get("diagnostic_scores") or {}).get("best_direction")
    adaptive_score = 100.0 if original_pass else round((best_score / 6.0) * 100.0, 2)
    result["adaptive_trend_score"] = adaptive_score

    if original_pass:
        result["adaptive_trend_pass"] = True
        result["adaptive_accepted"] = False
        result["adaptive_side"] = _side_from_direction(best_direction)
        result["adaptive_trend_reason"] = "strict trend pass"
        return result

    dangerous, dangerous_reason = _dangerous_regime(regime_diagnostics or {})
    failed = result.get("failed_conditions") or []
    blockers = []
    if adaptive_score < ADAPTIVE_TREND_MIN_SCORE:
        blockers.append(f"adaptive score {adaptive_score} below {ADAPTIVE_TREND_MIN_SCORE}")
    if best_score != 4:
        blockers.append(f"not exactly one condition short: {best_score}/6")
    if dangerous:
        blockers.append(dangerous_reason)
    if _strong_ema_opposite(result, best_direction):
        blockers.append("EMA direction strongly opposite")
    if _strong_structure_opposite(result, best_direction):
        blockers.append("price structure strongly opposite")
    if _volatility_panic(result, regime_diagnostics or {}):
        blockers.append("volatility panic")
    if _liquidity_or_manipulation_warning_high(regime_diagnostics or {}):
        blockers.append("liquidity/manipulation warning high")

    if blockers:
        result["adaptive_trend_pass"] = False
        result["adaptive_accepted"] = False
        result["adaptive_side"] = None
        result["adaptive_trend_reason"] = "; ".join(blockers)
        return result

    result["adaptive_trend_pass"] = True
    result["adaptive_accepted"] = True
    result["adaptive_side"] = _side_from_direction(best_direction)
    result["adaptive_trend_reason"] = (
        f"adaptive near-pass accepted: {best_score}/6, "
        f"missing {', '.join(failed) if failed else 'no listed condition'}"
    )
    return result


def _primary_sideways_reason(item):
    failed = item.get("failed_conditions") or []
    if not failed:
        return "unknown"
    if any("EMA20 not above EMA50" in x or "EMA20 not below EMA50" in x for x in failed):
        return "EMA spread direction mismatch"
    if any("EMA20 slope" in x or "EMA50 slope" in x for x in failed):
        return "weak slope"
    if any("recent high" in x or "recent low" in x for x in failed):
        return "timeframe structure not aligned"
    if any("price not" in x for x in failed):
        return "price not aligned with EMA20"
    if any("previous close" in x for x in failed):
        return "last candle direction mismatch"
    return failed[0]


def _dominant_failure_reason(symbol_items):
    reasons = Counter()
    for item in symbol_items or []:
        reason = item.get("primary_rejection_reason") or _primary_sideways_reason(item)
        reasons[str(reason or "unknown")] += 1
    return reasons.most_common(1)[0][0] if reasons else "none"


def _trend_confidence_summary(symbol_items):
    scores = [
        _safe_float(item.get("adaptive_trend_score"))
        for item in symbol_items or []
        if _safe_float(item.get("adaptive_trend_score")) is not None
    ]
    strict_passed = [item for item in symbol_items or [] if item.get("original_trend_pass")]
    adaptive_accepted = [item for item in symbol_items or [] if item.get("adaptive_accepted")]
    rejected = [
        item for item in symbol_items or []
        if not item.get("original_trend_pass") and not item.get("adaptive_accepted")
    ]
    return {
        "strict_passed": len(strict_passed),
        "adaptive_accepted": len(adaptive_accepted),
        "rejected": len(rejected),
        "average_adaptive_score": _avg(scores),
        "max_adaptive_score": max(scores) if scores else None,
        "near_pass_count": sum(
            1
            for item in rejected
            if int((item.get("diagnostic_scores") or {}).get("best") or 0) == 4
        ),
    }


def _build_rejection_reason(item):
    if item.get("original_trend_pass") or item.get("adaptive_accepted"):
        return "TREND_ACCEPTED"
    failed = item.get("failed_conditions") or []
    if item.get("data_stale"):
        return "STALE_OHLC"
    if "missing OHLC data" in failed:
        return "MISSING_OHLC"
    if "less than 60 candles" in failed:
        return "INSUFFICIENT_CANDLES"
    if item.get("adaptive_trend_reason"):
        return str(item.get("adaptive_trend_reason"))
    return _primary_sideways_reason(item)


def _compact_pipeline_symbol(item):
    diagnostic_scores = item.get("diagnostic_scores") or {}
    live_price = item.get("live_price_check") if isinstance(item.get("live_price_check"), dict) else {}
    return {
        "symbol": item.get("symbol"),
        "accepted": bool(item.get("original_trend_pass") or item.get("adaptive_accepted")),
        "trend_result": item.get("trend_result"),
        "primary_rejection_reason": item.get("primary_rejection_reason"),
        "exact_rejection_reasons": item.get("exact_rejection_reasons") or [],
        "adaptive_trend_reason": item.get("adaptive_trend_reason"),
        "failed_conditions": item.get("failed_conditions") or [],
        "threshold_values_used": {
            "strict_required_score": STRICT_TREND_REQUIRED_SCORE,
            "strict_condition_count": STRICT_TREND_CONDITION_COUNT,
            "adaptive_min_score": ADAPTIVE_TREND_MIN_SCORE,
            "min_candles": 60,
            "strong_opposite_ema_distance_pct": 0.5,
            "volatility_panic_atr_pct": 5.0,
        },
        "stale_data_indicators": {
            "data_stale": bool(item.get("data_stale")),
            "latest_candle_timestamp": item.get("latest_candle_timestamp"),
            "latest_candle_age_minutes": item.get("latest_candle_age_minutes"),
            "stale_reason": item.get("stale_reason"),
            "repeated_data_signature": bool(item.get("repeated_data_signature")),
        },
        "regime_blockers": item.get("regime_blockers") or [],
        "ema_state": {
            "ema20": item.get("ema20"),
            "ema50": item.get("ema50"),
            "ema_distance_pct": item.get("ema_distance_pct"),
            "price_vs_ema20": item.get("price_vs_ema20"),
            "price_vs_ema50": item.get("price_vs_ema50"),
            "slope_ema20": item.get("slope_ema20"),
            "slope_ema50": item.get("slope_ema50"),
            "diagnostic_scores": diagnostic_scores,
            "conditions": item.get("conditions") or {},
        },
        "timeframe_structure": {
            "recent_high_break": (item.get("conditions") or {}).get("recent_high_break"),
            "recent_low_break": (item.get("conditions") or {}).get("recent_low_break"),
        },
        "normalization": {
            "trend_result_label": item.get("trend_result"),
            "adaptive_side": item.get("adaptive_side"),
        },
        "live_price_mismatch": live_price,
    }


def _build_pipeline_diagnostics(scan_cycle_id, symbol_items, regime_diagnostics):
    enriched = []
    for item in symbol_items or []:
        cloned = dict(item)
        exact_reasons = list(cloned.get("failed_conditions") or [])
        primary = _build_rejection_reason(cloned)
        if primary and primary != "TREND_ACCEPTED" and primary not in exact_reasons:
            exact_reasons.insert(0, primary)
        cloned["primary_rejection_reason"] = primary
        cloned["exact_rejection_reasons"] = exact_reasons
        dangerous, dangerous_reason = _dangerous_regime(regime_diagnostics or {})
        blockers = []
        if dangerous:
            blockers.append(dangerous_reason)
        if _liquidity_or_manipulation_warning_high(regime_diagnostics or {}):
            blockers.append("liquidity/manipulation warning high")
        cloned["regime_blockers"] = blockers
        enriched.append(cloned)

    reason_counts = Counter(
        item.get("primary_rejection_reason") or "unknown"
        for item in enriched
        if not (item.get("original_trend_pass") or item.get("adaptive_accepted"))
    )
    return {
        "updated_at_ist": _timestamp_ist(),
        "scan_cycle_id": scan_cycle_id,
        "symbols_checked": len(enriched),
        "threshold_values_used": {
            "strict_required_score": STRICT_TREND_REQUIRED_SCORE,
            "strict_condition_count": STRICT_TREND_CONDITION_COUNT,
            "adaptive_min_score": ADAPTIVE_TREND_MIN_SCORE,
            "min_candles": 60,
            "stale_data_is_diagnostic_only": True,
        },
        "rejection_reason_counts": dict(reason_counts.most_common()),
        "dominant_failure_reason": _dominant_failure_reason(
            [item for item in enriched if not (item.get("original_trend_pass") or item.get("adaptive_accepted"))]
        ),
        "trend_confidence_summary": _trend_confidence_summary(enriched),
        "regime_blockers": {
            "current_regime": (regime_diagnostics or {}).get("current_regime"),
            "rejected_regimes": (regime_diagnostics or {}).get("rejected_regimes") or [],
            "market_status": (regime_diagnostics or {}).get("market_status") or {},
        },
        "symbols": [_compact_pipeline_symbol(item) for item in enriched],
        "safety_scope": {
            "diagnostics_only": True,
            "filters_loosened": False,
            "forced_trades": False,
            "broker_orders": False,
            "telegram_changes": False,
            "strategy_weight_mutation": False,
        },
    }


def _avg(values):
    nums = [_safe_float(value) for value in values]
    nums = [value for value in nums if value is not None]
    return round(sum(nums) / len(nums), 4) if nums else None


def save_trend_diagnostics(scan_cycle_id, symbols, regime_diagnostics=None):
    symbol_items = [apply_adaptive_trend(item, regime_diagnostics or {}) for item in list(symbols or [])]
    sideways = [item for item in symbol_items if item.get("trend_result") == "SIDEWAYS"]
    reason_counts = Counter(_primary_sideways_reason(item) for item in sideways)
    failed_condition_counts = Counter()
    for item in sideways:
        failed_condition_counts.update(item.get("failed_conditions") or [])

    closest = sorted(
        sideways,
        key=lambda item: (
            -(item.get("diagnostic_scores") or {}).get("best", 0),
            abs(_safe_float(item.get("ema_distance_pct"), 999.0)),
        ),
    )
    tiny_margin = [
        item
        for item in closest
        if (item.get("diagnostic_scores") or {}).get("best") == 4
    ]

    trend_payload = {
        "updated_at_ist": _timestamp_ist(),
        "scan_cycle_id": scan_cycle_id,
        "symbols_checked": len(symbol_items),
        "symbols": symbol_items,
        "regime_diagnostics": regime_diagnostics or {},
    }
    sideways_payload = {
        "updated_at_ist": _timestamp_ist(),
        "scan_cycle_id": scan_cycle_id,
        "total_sideways_symbols": len(sideways),
        "most_common_failed_condition": dict(failed_condition_counts.most_common()),
        "top_sideways_reasons": dict(reason_counts.most_common()),
        "average_ema_distance": _avg(item.get("ema_distance_pct") for item in sideways),
        "average_volatility": _avg(item.get("atr_pct") for item in sideways),
        "symbols_closest_to_passing_trend_gate": [
            {
                "symbol": item.get("symbol"),
                "best_score": (item.get("diagnostic_scores") or {}).get("best"),
                "best_direction": (item.get("diagnostic_scores") or {}).get("best_direction"),
                "failed_conditions": item.get("failed_conditions"),
                "ema_distance_pct": item.get("ema_distance_pct"),
                "atr_pct": item.get("atr_pct"),
            }
            for item in closest[:10]
        ],
        "symbols_rejected_only_by_tiny_margin": [
            {
                "symbol": item.get("symbol"),
                "best_direction": (item.get("diagnostic_scores") or {}).get("best_direction"),
                "failed_conditions": item.get("failed_conditions"),
                "trend_reason": item.get("trend_reason"),
            }
            for item in tiny_margin[:10]
        ],
        "regime_diagnostics": regime_diagnostics or {},
    }
    adaptive_accepted = [item for item in symbol_items if item.get("adaptive_accepted")]
    strict_passed = [item for item in symbol_items if item.get("original_trend_pass")]
    adaptive_rejected = [
        item
        for item in symbol_items
        if not item.get("original_trend_pass") and not item.get("adaptive_accepted")
    ]
    adaptive_report = {
        "updated_at_ist": _timestamp_ist(),
        "scan_cycle_id": scan_cycle_id,
        "symbols_checked": len(symbol_items),
        "strict_trend_passed": len(strict_passed),
        "adaptive_trend_accepted": len(adaptive_accepted),
        "trend_passed_total": len(strict_passed) + len(adaptive_accepted),
        "adaptive_rejected": len(adaptive_rejected),
        "adaptive_min_score": ADAPTIVE_TREND_MIN_SCORE,
        "accepted_symbols": [
            {
                "symbol": item.get("symbol"),
                "adaptive_side": item.get("adaptive_side"),
                "adaptive_trend_score": item.get("adaptive_trend_score"),
                "adaptive_trend_reason": item.get("adaptive_trend_reason"),
                "failed_conditions": item.get("failed_conditions"),
            }
            for item in adaptive_accepted
        ],
        "rejected_near_pass_symbols": [
            {
                "symbol": item.get("symbol"),
                "best_score": (item.get("diagnostic_scores") or {}).get("best"),
                "adaptive_trend_score": item.get("adaptive_trend_score"),
                "adaptive_trend_reason": item.get("adaptive_trend_reason"),
                "failed_conditions": item.get("failed_conditions"),
            }
            for item in adaptive_rejected
            if (item.get("diagnostic_scores") or {}).get("best") == 4
        ],
        "regime_diagnostics": regime_diagnostics or {},
    }
    pipeline_diagnostics = _build_pipeline_diagnostics(
        scan_cycle_id,
        symbol_items,
        regime_diagnostics or {},
    )

    for path, payload in (
        (TREND_DIAGNOSTICS_PATH, trend_payload),
        (TREND_PIPELINE_DIAGNOSTICS_PATH, pipeline_diagnostics),
        (SIDEWAYS_ANALYSIS_PATH, sideways_payload),
        (ADAPTIVE_TREND_REPORT_PATH, adaptive_report),
    ):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(f"{path.suffix}.tmp")
            tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            tmp_path.replace(path)
        except Exception:
            pass

    return trend_payload, sideways_payload, adaptive_report, pipeline_diagnostics
