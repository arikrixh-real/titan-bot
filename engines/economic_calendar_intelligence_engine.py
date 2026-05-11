"""
TITAN Phase 29 - Economic Calendar Intelligence
-----------------------------------------------

Economic calendar risk sidecar. Uses real calendar events when available,
context proxy flags when calendar data is missing, and neutral insufficient
mode otherwise. It never places orders or enables live execution.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


REPORT_PATH = Path("data/economic_calendar/latest_economic_calendar_report.json")

EVENT_KEYWORDS = {
    "RBI": {"rbi", "reserve bank", "mpc", "repo rate", "monetary policy"},
    "FED": {"fed", "fomc", "federal reserve", "powell", "us rates"},
    "INFLATION": {"inflation", "cpi", "wpi", "ppi", "core cpi"},
    "GDP": {"gdp", "growth data", "iip", "industrial production"},
    "BUDGET": {"budget", "union budget", "fiscal", "tax", "capex"},
    "EARNINGS": {"earnings", "results", "quarterly", "q1", "q2", "q3", "q4"},
    "EXPIRY": {"expiry", "expiration", "weekly expiry", "monthly expiry", "f&o expiry", "fo expiry"},
}

HIGH_IMPACT_TYPES = {"RBI", "FED", "INFLATION", "BUDGET"}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        result = float(value)
        if not math.isfinite(result):
            return default
        return result
    except Exception:
        return default


def safe_text(value: Any, default: str = "") -> str:
    try:
        if value is None:
            return default
        text = str(value).strip()
        return text if text else default
    except Exception:
        return default


def safe_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def clamp(value: Any, min_value: float = 0.0, max_value: float = 100.0) -> float:
    low = safe_float(min_value, 0.0)
    high = safe_float(max_value, 100.0)
    if low > high:
        low, high = high, low
    return max(low, min(high, safe_float(value, low)))


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first(data: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for key in keys:
        if key in data and data.get(key) is not None:
            return data.get(key)
    return default


def _blob(*values: Any) -> str:
    return " ".join(safe_text(value) for value in values if value is not None).lower()


def _parse_time(value: Any) -> datetime | None:
    text = safe_text(value)
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _event_type(event: Dict[str, Any]) -> str:
    explicit = safe_text(event.get("event_type") or event.get("type") or event.get("category")).upper()
    if explicit in EVENT_KEYWORDS:
        return explicit
    text = _blob(event.get("title"), event.get("name"), event.get("description"), event.get("country"))
    for event_type, keywords in EVENT_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return event_type
    return "GENERAL"


def _impact_score(value: Any, event_type: str = "GENERAL") -> float:
    text = safe_text(value).lower()
    if text in {"high", "3", "major"}:
        return 85.0
    if text in {"medium", "2", "moderate"}:
        return 60.0
    if text in {"low", "1", "minor"}:
        return 35.0
    if event_type in HIGH_IMPACT_TYPES:
        return 78.0
    if event_type in {"EXPIRY", "EARNINGS"}:
        return 62.0
    return 40.0


def normalize_calendar_events(calendar_events: Any = None) -> List[Dict[str, Any]]:
    raw_events = []
    if isinstance(calendar_events, dict):
        for key in ("events", "calendar_events", "data", "items", "economic_calendar"):
            if isinstance(calendar_events.get(key), list):
                raw_events = calendar_events.get(key)
                break
        if not raw_events and (calendar_events.get("title") or calendar_events.get("name")):
            raw_events = [calendar_events]
    else:
        raw_events = safe_list(calendar_events)

    normalized = []
    for event in raw_events:
        if not isinstance(event, dict):
            continue
        title = safe_text(_first(event, ["title", "name", "event", "headline"]))
        description = safe_text(_first(event, ["description", "summary", "details"]))
        if not title and not description:
            continue
        event_type = _event_type(event)
        timestamp = safe_text(_first(event, ["timestamp", "datetime", "date", "time", "event_time"]))
        country = safe_text(_first(event, ["country", "region", "market"]), "")
        impact = _impact_score(_first(event, ["impact", "importance", "priority"]), event_type)
        parsed = _parse_time(timestamp)
        hours_until = None
        if parsed is not None:
            hours_until = (parsed.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds() / 3600.0
        normalized.append({
            "title": title,
            "description": description,
            "event_type": event_type,
            "timestamp": timestamp,
            "country": country,
            "impact_score": round(clamp(impact), 2),
            "hours_until": None if hours_until is None else round(hours_until, 2),
            "symbol": safe_text(event.get("symbol") or event.get("stock")).upper(),
            "raw": event,
        })
    return normalized


def _detect_type(calendar_events: Any, event_type: str, context: Any = None) -> Dict[str, Any]:
    events = [event for event in normalize_calendar_events(calendar_events) if event.get("event_type") == event_type]
    max_impact = max([safe_float(event.get("impact_score")) for event in events], default=0.0)
    nearest = None
    upcoming_hours = [safe_float(event.get("hours_until"), 9999.0) for event in events if event.get("hours_until") is not None and safe_float(event.get("hours_until"), 9999.0) >= -24.0]
    if upcoming_hours:
        nearest = min(upcoming_hours)
    return {
        "active": bool(events),
        "count": len(events),
        "max_impact_score": round(max_impact, 2),
        "nearest_hours_until": None if nearest is None else round(nearest, 2),
        "events": events[:5],
    }


def detect_rbi_events(calendar_events: Any = None, context: Any = None) -> Dict[str, Any]:
    result = _detect_type(calendar_events, "RBI", context)
    if not result["active"] and _dict(context).get("rbi_event"):
        result.update({"active": True, "count": 1, "max_impact_score": 78.0, "proxy": True})
    return result


def detect_fed_events(calendar_events: Any = None, context: Any = None) -> Dict[str, Any]:
    result = _detect_type(calendar_events, "FED", context)
    if not result["active"] and (_dict(context).get("fed_event") or _dict(context).get("fomc_event")):
        result.update({"active": True, "count": 1, "max_impact_score": 78.0, "proxy": True})
    return result


def detect_inflation_events(calendar_events: Any = None, context: Any = None) -> Dict[str, Any]:
    result = _detect_type(calendar_events, "INFLATION", context)
    if not result["active"] and (_dict(context).get("inflation_event") or _dict(context).get("cpi_event")):
        result.update({"active": True, "count": 1, "max_impact_score": 75.0, "proxy": True})
    return result


def detect_gdp_events(calendar_events: Any = None, context: Any = None) -> Dict[str, Any]:
    result = _detect_type(calendar_events, "GDP", context)
    if not result["active"] and _dict(context).get("gdp_event"):
        result.update({"active": True, "count": 1, "max_impact_score": 62.0, "proxy": True})
    return result


def detect_budget_events(calendar_events: Any = None, context: Any = None) -> Dict[str, Any]:
    result = _detect_type(calendar_events, "BUDGET", context)
    if not result["active"] and _dict(context).get("budget_event"):
        result.update({"active": True, "count": 1, "max_impact_score": 80.0, "proxy": True})
    return result


def detect_earnings_calendar_events(calendar_events: Any = None, setup: Any = None, context: Any = None) -> Dict[str, Any]:
    events = [event for event in normalize_calendar_events(calendar_events) if event.get("event_type") == "EARNINGS"]
    setup_data = _dict(setup)
    raw = _dict(setup_data.get("raw"))
    symbol = safe_text(setup_data.get("symbol") or raw.get("symbol") or setup_data.get("stock") or raw.get("stock")).upper()
    matched = [event for event in events if not event.get("symbol") or event.get("symbol") == symbol]
    if not matched and _dict(context).get("earnings_event"):
        matched = [{"title": "Proxy earnings event", "event_type": "EARNINGS", "impact_score": 62.0, "proxy": True}]
    max_impact = max([safe_float(event.get("impact_score")) for event in matched], default=0.0)
    return {"active": bool(matched), "count": len(matched), "max_impact_score": round(max_impact, 2), "events": matched[:5]}


def detect_expiry_events(calendar_events: Any = None, context: Any = None) -> Dict[str, Any]:
    result = _detect_type(calendar_events, "EXPIRY", context)
    ctx = _dict(context)
    days = safe_float(ctx.get("days_to_expiry") if ctx.get("days_to_expiry") is not None else ctx.get("dte"), 999.0)
    is_expiry = bool(ctx.get("is_expiry_day") or days == 0)
    if not result["active"] and (is_expiry or days <= 1):
        result.update({"active": True, "count": 1, "max_impact_score": 65.0 if is_expiry else 52.0, "proxy": True})
    result["is_expiry_day"] = is_expiry
    result["days_to_expiry"] = None if days == 999.0 else days
    return result


def calculate_event_risk_score(calendar_events: Any = None, setup: Any = None, context: Any = None) -> float:
    detectors = [
        detect_rbi_events(calendar_events, context),
        detect_fed_events(calendar_events, context),
        detect_inflation_events(calendar_events, context),
        detect_gdp_events(calendar_events, context),
        detect_budget_events(calendar_events, context),
        detect_earnings_calendar_events(calendar_events, setup, context),
        detect_expiry_events(calendar_events, context),
    ]
    score = 0.0
    for item in detectors:
        if not item.get("active"):
            continue
        impact = safe_float(item.get("max_impact_score"))
        nearest = item.get("nearest_hours_until")
        proximity = 1.0
        if nearest is not None:
            hours = abs(safe_float(nearest))
            proximity = 1.35 if hours <= 2 else 1.15 if hours <= 8 else 0.85 if hours <= 48 else 0.45
        score += impact * proximity * 0.22
    vix = safe_float(_dict(context).get("india_vix") or _dict(context).get("vix"), 0.0)
    score += max(0.0, vix - 20.0) * 1.5
    return round(clamp(score), 2)


def detect_no_trade_caution_windows(calendar_events: Any = None, context: Any = None) -> Dict[str, Any]:
    events = normalize_calendar_events(calendar_events)
    caution_events = []
    for event in events:
        hours = event.get("hours_until")
        if hours is None:
            continue
        h = safe_float(hours)
        if -1.0 <= h <= 2.0 and safe_float(event.get("impact_score")) >= 60.0:
            caution_events.append(event)
    proxy = False
    if not caution_events and _dict(context).get("no_trade_event_window"):
        proxy = True
    active = bool(caution_events or proxy)
    return {
        "active": active,
        "warning": "WAIT" if active else "NONE",
        "event_count": len(caution_events) if caution_events else (1 if proxy else 0),
        "window": "T_MINUS_1H_TO_T_PLUS_2H" if active else "NONE",
        "events": caution_events[:5],
        "proxy": proxy,
    }


def forecast_macro_impact(calendar_events: Any = None, setup: Any = None, context: Any = None) -> Dict[str, Any]:
    rbi = detect_rbi_events(calendar_events, context)
    fed = detect_fed_events(calendar_events, context)
    inflation = detect_inflation_events(calendar_events, context)
    budget = detect_budget_events(calendar_events, context)
    risk = calculate_event_risk_score(calendar_events, setup, context)
    side = safe_text(_dict(setup).get("side") or _dict(setup).get("direction")).upper()
    if budget.get("active") and side == "LONG":
        bias = "BULLISH"
    elif rbi.get("active") or fed.get("active") or inflation.get("active"):
        bias = "NEUTRAL"
    else:
        bias = "NEUTRAL"
    return {
        "macro_risk_state": "HIGH" if risk >= 70 else "ELEVATED" if risk >= 45 else "NORMAL",
        "expected_directional_bias": bias,
        "sensitive_events": [name for name, active in [("RBI", rbi), ("FED", fed), ("INFLATION", inflation), ("BUDGET", budget)] if active.get("active")],
    }


def anticipate_event_volatility(calendar_events: Any = None, context: Any = None) -> Dict[str, Any]:
    risk = calculate_event_risk_score(calendar_events, context=context)
    expiry = detect_expiry_events(calendar_events, context)
    score = clamp(risk * 0.75 + (20.0 if expiry.get("active") else 0.0))
    return {
        "volatility_score": round(score, 2),
        "volatility_state": "HIGH" if score >= 70 else "ELEVATED" if score >= 45 else "NORMAL",
        "expiry_volatility_caution": bool(expiry.get("active")),
    }


def _has_proxy_context(context: Dict[str, Any]) -> bool:
    keys = (
        "rbi_event", "fed_event", "fomc_event", "inflation_event", "cpi_event",
        "gdp_event", "budget_event", "earnings_event", "is_expiry_day",
        "days_to_expiry", "dte", "event_risk_score", "no_trade_event_window",
        "event_calendar_proxy",
    )
    return any(context.get(key) is not None for key in keys)


def build_economic_calendar_report(setup: Any = None, calendar_events: Any = None, context: Any = None) -> Dict[str, Any]:
    setup_data = _dict(setup)
    raw = _dict(setup_data.get("raw"))
    ctx = _dict(context)
    if calendar_events is None:
        calendar_events = (
            setup_data.get("calendar_events")
            or raw.get("calendar_events")
            or ctx.get("calendar_events")
            or ctx.get("economic_calendar")
        )
    events = normalize_calendar_events(calendar_events)
    mode = "REAL_CALENDAR" if events else "PROXY" if _has_proxy_context(ctx) else "INSUFFICIENT"

    rbi = detect_rbi_events(events, ctx)
    fed = detect_fed_events(events, ctx)
    inflation = detect_inflation_events(events, ctx)
    gdp = detect_gdp_events(events, ctx)
    budget = detect_budget_events(events, ctx)
    earnings = detect_earnings_calendar_events(events, setup_data, ctx)
    expiry = detect_expiry_events(events, ctx)
    risk = calculate_event_risk_score(events, setup_data, ctx) if mode != "INSUFFICIENT" else 0.0
    if mode == "PROXY" and ctx.get("event_risk_score") is not None:
        risk = clamp(ctx.get("event_risk_score"))
    no_trade = detect_no_trade_caution_windows(events, ctx)
    macro = forecast_macro_impact(events, setup_data, ctx)
    volatility = anticipate_event_volatility(events, ctx)

    if mode == "INSUFFICIENT":
        intelligence_score = 50.0
        warning = "REVIEW"
    else:
        intelligence_score = clamp(100.0 - risk)
        if no_trade.get("active") or risk >= 85:
            warning = "SKIP"
        elif risk >= 60:
            warning = "WAIT"
        elif risk >= 38 or volatility.get("volatility_state") == "ELEVATED":
            warning = "REVIEW"
        else:
            warning = "NONE"

    symbol = safe_text(setup_data.get("symbol") or raw.get("symbol") or setup_data.get("stock") or raw.get("stock"), "UNKNOWN").upper()
    explanations = [f"Calendar data mode: {mode}."]
    if risk:
        explanations.append(f"Event risk score is {round(risk, 2)}.")
    if expiry.get("active"):
        explanations.append("Expiry-related volatility caution is active.")
    if no_trade.get("active"):
        explanations.append("No-trade caution window is active around a high-impact event.")
    if mode == "INSUFFICIENT":
        explanations.append("No useful calendar or proxy event data; score kept neutral.")

    report = {
        "symbol": symbol,
        "calendar_data_mode": mode,
        "rbi_events": rbi,
        "fed_events": fed,
        "inflation_events": inflation,
        "gdp_events": gdp,
        "budget_events": budget,
        "earnings_events": earnings,
        "expiry_events": expiry,
        "event_risk_score": round(clamp(risk), 2),
        "no_trade_caution": no_trade,
        "macro_impact_forecast": macro,
        "event_volatility_anticipation": volatility,
        "calendar_intelligence_score": round(clamp(intelligence_score), 2),
        "calendar_bias": macro.get("expected_directional_bias", "NEUTRAL"),
        "calendar_warning": warning,
        "live_order_allowed": False,
        "explanations": explanations[:8],
    }
    try:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return report


if __name__ == "__main__":
    sample_events = [
        {"title": "RBI MPC policy decision", "date": datetime.now(timezone.utc).isoformat(), "impact": "high", "country": "IN"},
        {"title": "NIFTY weekly expiry", "date": datetime.now(timezone.utc).isoformat(), "impact": "medium"},
        {"title": "RELIANCE quarterly earnings results", "symbol": "RELIANCE", "impact": "medium"},
    ]
    sample_setup = {"symbol": "RELIANCE", "side": "LONG", "sector": "Energy"}
    sample_context = {"india_vix": 17.5, "days_to_expiry": 0, "is_expiry_day": True}
    print(json.dumps(build_economic_calendar_report(sample_setup, sample_events, sample_context), indent=2, sort_keys=True))
