"""
TITAN Phase 7 - Trade Lifecycle Intelligence Shadow Layer.

This module observes existing trade lifecycle data only. It does not fetch
prices, send alerts, place orders, update trade status, alter TP/SL/RR, or
write to Supabase.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "lifecycle_memory.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "lifecycle_shadow_report.txt"

STATE_VERSION = "7.0"
MAX_TRADE_RECORDS = 300
MAX_REPORT_ITEMS = 10
REPORT_REFRESH_SECONDS = 3600


def _now_text() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _trade_id(row: Dict[str, Any]) -> str:
    trade_id = str(row.get("trade_id") or "").strip()
    if trade_id:
        return trade_id
    return "|".join(
        [
            str(row.get("scan_id") or "").strip(),
            _safe_upper(row.get("symbol")),
            _safe_upper(row.get("side")),
            str(row.get("entry") or "").strip(),
        ]
    )


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=IST)
            return parsed.astimezone(IST)
        except Exception:
            continue

    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=IST)
        return parsed.astimezone(IST)
    except Exception:
        return None


def _hours_open(opened_at: Any, observed_at: datetime) -> float:
    opened = _parse_time(opened_at)
    if opened is None:
        return 0.0
    return max(0.0, round((observed_at - opened).total_seconds() / 3600.0, 4))


def _side_excursion(side: str, entry: float, price: float) -> tuple[float, float, float]:
    if side == "LONG":
        pnl = price - entry
    elif side == "SHORT":
        pnl = entry - price
    else:
        pnl = 0.0

    favorable = max(0.0, pnl)
    adverse = max(0.0, -pnl)
    return round(favorable, 4), round(adverse, 4), round(pnl, 4)


def _distance_to_levels(side: str, price: float, sl: float, target: float) -> tuple[float, float]:
    if side == "LONG":
        distance_to_tp = target - price
        distance_to_sl = price - sl
    elif side == "SHORT":
        distance_to_tp = price - target
        distance_to_sl = sl - price
    else:
        distance_to_tp = 0.0
        distance_to_sl = 0.0

    return round(distance_to_tp, 4), round(distance_to_sl, 4)


def _momentum_status(favorable_r: float, adverse_r: float) -> str:
    if favorable_r >= 0.75:
        return "STRONG_FOLLOW_THROUGH"
    if favorable_r >= 0.25 and adverse_r < 0.35:
        return "POSITIVE_FOLLOW_THROUGH"
    if adverse_r >= 0.75:
        return "ADVERSE_PRESSURE"
    if adverse_r >= 0.35:
        return "WEAKENING"
    return "NEUTRAL"


def _time_quality(hours: float, favorable_r: float, adverse_r: float) -> str:
    if hours <= 0:
        return "UNKNOWN"
    if hours <= 0.5 and adverse_r >= 0.35:
        return "FAST_ADVERSE_MOVE"
    if hours >= 3.0 and favorable_r < 0.20:
        return "TIME_DECAY"
    if favorable_r >= 0.50 and adverse_r < 0.30:
        return "HEALTHY"
    return "NORMAL"


def _setup_family(row: Dict[str, Any]) -> str:
    for key in ("strategy_family", "strategy", "setup_type"):
        value = str(row.get(key) or "").strip()
        if value:
            return value[:80]

    try:
        from engines.meta_intelligence_engine import classify_strategy_family

        return str(classify_strategy_family(row))[:80]
    except Exception:
        return "UNKNOWN"


def _classify_failure(
    row: Dict[str, Any],
    outcome_status: str,
    favorable_r: float,
    adverse_r: float,
    hours: float,
    observation: Dict[str, Any],
) -> str:
    status = _safe_upper(outcome_status)
    score = _safe_float(row.get("score"), 0.0)
    reason = str(row.get("reason") or row.get("result_reason") or row.get("market_status") or "").lower()
    warning = str(observation.get("invalidation_warning") or "").lower()

    if status in {"TP", "TARGET", "WIN"}:
        return "successful_follow_through"
    if "news" in reason or "news" in warning:
        return "news_shock"
    if "sector" in reason or "sector" in warning:
        return "sector_weakness"
    if "slippage" in reason or "liquidity" in reason:
        return "liquidity_issue"
    if "volatility" in reason or "panic" in reason:
        return "volatility_spike"
    if score > 0 and score < 2.5:
        return "weak_setup_quality"
    if hours >= 3.0 and favorable_r < 0.20:
        return "time_decay"
    if adverse_r >= 0.75 and hours <= 1.0:
        return "bad_entry"
    if adverse_r >= 0.75:
        return "market_reversal"
    if status in {"SL", "LOSS", "STOPLOSS", "STOP_LOSS"}:
        return "market_reversal"
    return "unclassified_shadow"


def observe_trade_lifecycle(
    row: Dict[str, Any],
    live_price: Any,
    outcome_status: str = "OPEN",
    observed_at: datetime | None = None,
) -> Dict[str, Any]:
    """
    Build one shadow lifecycle observation using a live price the caller already
    fetched. Raises are intentionally caught by public safe wrappers.
    """

    observed_at = observed_at or datetime.now(IST)
    side = _safe_upper(row.get("side"))
    entry = _safe_float(row.get("entry"))
    sl = _safe_float(row.get("sl"))
    target = _safe_float(row.get("target"))
    price = _safe_float(live_price)

    risk_points = abs(entry - sl)
    reward_points = abs(target - entry)
    favorable, adverse, unrealized_pnl = _side_excursion(side, entry, price)
    favorable_r = favorable / risk_points if risk_points else 0.0
    adverse_r = adverse / risk_points if risk_points else 0.0
    distance_to_tp, distance_to_sl = _distance_to_levels(side, price, sl, target)
    hours = _hours_open(row.get("opened_at"), observed_at)

    momentum_status = _momentum_status(favorable_r, adverse_r)
    time_quality = _time_quality(hours, favorable_r, adverse_r)
    setup_decay_warning = bool(hours >= 3.0 and favorable_r < 0.20 and _safe_upper(outcome_status) == "OPEN")
    invalidation_warning = ""
    if distance_to_sl <= max(risk_points * 0.20, 0.01):
        invalidation_warning = "price is close to stop-loss invalidation"
    elif adverse_r >= 0.60:
        invalidation_warning = "adverse excursion is pressuring setup"

    score = _safe_float(row.get("score"), 0.0)
    base_confidence = _clamp((score / 4.0) * 100.0 if score else 50.0)
    health = base_confidence
    health += min(25.0, favorable_r * 20.0)
    health -= min(35.0, adverse_r * 30.0)
    if setup_decay_warning:
        health -= 12.0
    if invalidation_warning:
        health -= 10.0
    if time_quality == "HEALTHY":
        health += 6.0
    elif time_quality == "FAST_ADVERSE_MOVE":
        health -= 10.0

    trade_health_score = round(_clamp(health), 2)
    confidence_drift = round(trade_health_score - base_confidence, 2)

    observation = {
        "trade_id": _trade_id(row),
        "observed_at": observed_at.strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": _safe_upper(row.get("symbol")),
        "side": side,
        "status": _safe_upper(row.get("status") or outcome_status),
        "outcome_status_shadow": _safe_upper(outcome_status),
        "entry": round(entry, 4),
        "sl": round(sl, 4),
        "target": round(target, 4),
        "last_price": round(price, 4),
        "risk_points": round(risk_points, 4),
        "reward_points": round(reward_points, 4),
        "current_favorable_excursion": favorable,
        "current_adverse_excursion": adverse,
        "current_favorable_r": round(favorable_r, 4),
        "current_adverse_r": round(adverse_r, 4),
        "unrealized_pnl_points_shadow": unrealized_pnl,
        "distance_to_tp": distance_to_tp,
        "distance_to_sl": distance_to_sl,
        "time_in_trade_hours": hours,
        "time_in_trade_quality": time_quality,
        "post_entry_momentum_status": momentum_status,
        "setup_decay_warning": setup_decay_warning,
        "invalidation_warning": invalidation_warning,
        "confidence_drift": confidence_drift,
        "trade_health_score": trade_health_score,
        "setup_family": _setup_family(row),
    }
    observation["failure_cause_classification"] = _classify_failure(
        row=row,
        outcome_status=outcome_status,
        favorable_r=favorable_r,
        adverse_r=adverse_r,
        hours=hours,
        observation=observation,
    )
    return observation


def observe_trade_lifecycle_safely(
    row: Dict[str, Any],
    live_price: Any,
    outcome_status: str = "OPEN",
    observed_at: datetime | None = None,
) -> Dict[str, Any] | None:
    try:
        if not isinstance(row, dict):
            return None
        if live_price is None or live_price == "":
            return None
        return observe_trade_lifecycle(row, live_price, outcome_status, observed_at)
    except Exception:
        return None


def _load_memory() -> Dict[str, Any]:
    if not MEMORY_PATH.exists():
        return {
            "version": STATE_VERSION,
            "last_updated": None,
            "trade_lifecycle": {},
            "symbol_stats": {},
            "setup_family_stats": {},
            "failure_cause_counts": {},
        }

    try:
        with MEMORY_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _average(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _stats_bucket(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not items:
        return {
            "observations": 0,
            "avg_trade_health_score": 0.0,
            "avg_confidence_drift": 0.0,
            "max_favorable_excursion": 0.0,
            "max_adverse_excursion": 0.0,
            "failure_causes": {},
        }

    causes = Counter(str(item.get("failure_cause_classification") or "unclassified_shadow") for item in items)
    return {
        "observations": len(items),
        "avg_trade_health_score": _average(_safe_float(item.get("trade_health_score")) for item in items),
        "avg_confidence_drift": _average(_safe_float(item.get("confidence_drift")) for item in items),
        "max_favorable_excursion": round(max(_safe_float(item.get("max_favorable_excursion")) for item in items), 4),
        "max_adverse_excursion": round(max(_safe_float(item.get("max_adverse_excursion")) for item in items), 4),
        "failure_causes": dict(causes),
    }


def _trim_trade_records(trades: Dict[str, Any]) -> Dict[str, Any]:
    items = list(trades.items())
    items.sort(key=lambda item: str(item[1].get("last_observed_at") or ""), reverse=True)
    return dict(items[:MAX_TRADE_RECORDS])


def update_lifecycle_memory_safely(observations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Persist compact shadow lifecycle memory. This function never raises.
    """

    try:
        clean_observations = [item for item in observations or [] if isinstance(item, dict)]
        if not clean_observations:
            return {"skipped": "NO_OBSERVATIONS"}

        memory = _load_memory()
        trades = memory.get("trade_lifecycle")
        if not isinstance(trades, dict):
            trades = {}

        for obs in clean_observations:
            trade_id = str(obs.get("trade_id") or "").strip()
            if not trade_id:
                continue

            previous = trades.get(trade_id) if isinstance(trades.get(trade_id), dict) else {}
            max_favorable = max(
                _safe_float(previous.get("max_favorable_excursion")),
                _safe_float(obs.get("current_favorable_excursion")),
            )
            max_adverse = max(
                _safe_float(previous.get("max_adverse_excursion")),
                _safe_float(obs.get("current_adverse_excursion")),
            )

            trades[trade_id] = {
                **previous,
                **obs,
                "first_observed_at": previous.get("first_observed_at") or obs.get("observed_at"),
                "last_observed_at": obs.get("observed_at"),
                "max_favorable_excursion": round(max_favorable, 4),
                "max_adverse_excursion": round(max_adverse, 4),
                "observation_count": int(previous.get("observation_count") or 0) + 1,
            }

        trades = _trim_trade_records(trades)
        trade_items = list(trades.values())

        by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        by_family: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        cause_counts = Counter()

        for item in trade_items:
            by_symbol[str(item.get("symbol") or "UNKNOWN")].append(item)
            by_family[str(item.get("setup_family") or "UNKNOWN")].append(item)
            cause_counts[str(item.get("failure_cause_classification") or "unclassified_shadow")] += 1

        memory = {
            "version": STATE_VERSION,
            "last_updated": _now_text(),
            "trade_lifecycle": trades,
            "symbol_stats": {symbol: _stats_bucket(items) for symbol, items in sorted(by_symbol.items())},
            "setup_family_stats": {family: _stats_bucket(items) for family, items in sorted(by_family.items())},
            "failure_cause_counts": dict(cause_counts),
        }

        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with MEMORY_PATH.open("w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2, sort_keys=True)

        write_lifecycle_report_safely(memory)
        return {"updated": len(clean_observations), "tracked_trades": len(trades)}

    except Exception as exc:
        return {"error": str(exc)}


def _top_stats(stats: Dict[str, Any], metric: str, reverse: bool = True) -> List[tuple[str, Dict[str, Any]]]:
    items = list((stats or {}).items())
    items.sort(key=lambda item: _safe_float(item[1].get(metric)), reverse=reverse)
    return items[:MAX_REPORT_ITEMS]


def _report_throttled() -> bool:
    try:
        if not REPORT_PATH.exists():
            return False
        if "not yet refreshed" in REPORT_PATH.read_text(encoding="utf-8")[:500]:
            return False
        age = datetime.now(IST).timestamp() - REPORT_PATH.stat().st_mtime
        return age < REPORT_REFRESH_SECONDS
    except Exception:
        return False


def render_lifecycle_report(memory: Dict[str, Any]) -> str:
    trades = memory.get("trade_lifecycle") or {}
    symbol_stats = memory.get("symbol_stats") or {}
    family_stats = memory.get("setup_family_stats") or {}
    cause_counts = memory.get("failure_cause_counts") or {}

    lines = [
        "TITAN Phase 7 Trade Lifecycle Shadow Report",
        "===========================================",
        "",
        "Safety",
        "- Shadow observation only.",
        "- No Telegram, broker, TP/SL/RR, outcome, ranking, or alert-cap changes.",
        "- Uses only prices already fetched by outcome tracking.",
        "",
        f"Updated: {memory.get('last_updated')}",
        f"Tracked Trades: {len(trades)}",
        "",
        "Failure Cause Classification:",
    ]

    if cause_counts:
        for cause, count in sorted(cause_counts.items(), key=lambda item: item[1], reverse=True)[:MAX_REPORT_ITEMS]:
            lines.append(f"- {cause}: {count}")
    else:
        lines.append("- None observed")

    lines.extend(["", "Strongest Lifecycle Symbols:"])
    for symbol, bucket in _top_stats(symbol_stats, "avg_trade_health_score"):
        lines.append(
            f"- {symbol}: observations={bucket.get('observations')}, "
            f"avg_health={bucket.get('avg_trade_health_score')}, "
            f"max_favorable={bucket.get('max_favorable_excursion')}, "
            f"max_adverse={bucket.get('max_adverse_excursion')}"
        )
    if not symbol_stats:
        lines.append("- None observed")

    lines.extend(["", "Weakest Lifecycle Symbols:"])
    for symbol, bucket in _top_stats(symbol_stats, "avg_trade_health_score", reverse=False):
        lines.append(
            f"- {symbol}: observations={bucket.get('observations')}, "
            f"avg_health={bucket.get('avg_trade_health_score')}, "
            f"avg_drift={bucket.get('avg_confidence_drift')}"
        )
    if not symbol_stats:
        lines.append("- None observed")

    lines.extend(["", "Setup Family Lifecycle Stats:"])
    for family, bucket in _top_stats(family_stats, "observations"):
        lines.append(
            f"- {family}: observations={bucket.get('observations')}, "
            f"avg_health={bucket.get('avg_trade_health_score')}, "
            f"failure_causes={bucket.get('failure_causes')}"
        )
    if not family_stats:
        lines.append("- None observed")

    return "\n".join(lines) + "\n"


def write_lifecycle_report_safely(memory: Dict[str, Any] | None = None, force: bool = False) -> Dict[str, Any]:
    try:
        if not force and _report_throttled():
            return {"skipped": "CACHE_FRESH"}

        memory = memory if isinstance(memory, dict) else _load_memory()
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(render_lifecycle_report(memory), encoding="utf-8")
        return {"written": str(REPORT_PATH)}
    except Exception as exc:
        return {"error": str(exc)}
