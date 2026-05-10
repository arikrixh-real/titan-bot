"""
TITAN Phase 8 - Market Narrative & Cross-Asset Intelligence.

Shadow-only narrative layer. It reads already-available TITAN market/context
metadata and local memory files, then writes compact advisory artifacts.

Safety:
- No network/API calls.
- No live-price calls.
- No Telegram, broker, Supabase, ranking, execution, alert-cap, or duplicate
  prevention integration.
- Does not mutate evaluated_setups or context.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "reports" / "market_narrative_report.txt"
MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "market_narrative_memory.json"
NEWS_MEMORY_PATH = PROJECT_ROOT / "titan_brain" / "memory" / "news_batch_state.json"
LIFECYCLE_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "lifecycle_memory.json"

STATE_VERSION = "8.0"
PHASE8_SHADOW_MODE = True
REPORT_REFRESH_SECONDS = 3600
MAX_HISTORY = 50
MAX_SETUPS_TO_ANALYZE = 30
MAX_REPORT_ITEMS = 8


def _now() -> str:
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


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _market_data(master_input: Dict[str, Any]) -> Dict[str, Any]:
    packet = master_input.get("market") if isinstance(master_input, dict) else {}
    data = packet.get("data") if isinstance(packet, dict) else {}
    return data if isinstance(data, dict) else {}


def _trend_from_market(market: Dict[str, Any]) -> str:
    for key in ("direction", "nifty_trend", "status", "regime"):
        value = _safe_upper(market.get(key))
        if value in {"BULLISH", "BEARISH", "NEUTRAL", "RISK_ON", "RISK_OFF"}:
            return value
    return "UNKNOWN"


def _risk_state(score: float, tone: str) -> str:
    tone = _safe_upper(tone)
    if score >= 62 or tone in {"RISK_ON", "BULLISH"}:
        return "RISK_ON"
    if score <= 38 or tone in {"RISK_OFF", "BEARISH"}:
        return "RISK_OFF"
    return "NEUTRAL"


def _event_pressure(market: Dict[str, Any], news_memory: Dict[str, Any]) -> Dict[str, Any]:
    proxy = market.get("event_calendar_proxy")
    proxy = proxy if isinstance(proxy, dict) else {}
    keywords = proxy.get("event_keywords") if isinstance(proxy.get("event_keywords"), list) else []
    score = _safe_float(proxy.get("event_pressure_score"), 0.0)

    items = news_memory.get("news") if isinstance(news_memory, dict) else []
    if isinstance(items, list):
        event_terms = {"rbi", "fed", "fomc", "cpi", "inflation", "policy", "geopolitical", "election"}
        hits = []
        for item in items[:100]:
            if not isinstance(item, dict):
                continue
            text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
            for term in event_terms:
                if term in text:
                    hits.append(term)
        if hits:
            keywords = sorted(set([*keywords, *hits]))[:MAX_REPORT_ITEMS]
            score = max(score, min(100.0, len(set(hits)) * 12.0))

    if score >= 55 or proxy.get("event_caution"):
        state = "HIGH"
    elif score >= 25:
        state = "MEDIUM"
    else:
        state = "LOW"

    return {"state": state, "score": round(score, 2), "keywords": keywords[:MAX_REPORT_ITEMS]}


def _sector_lists(market: Dict[str, Any]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rankings = market.get("sector_rankings")
    if not isinstance(rankings, list):
        rankings = []

    clean = [item for item in rankings if isinstance(item, dict)]
    if clean:
        leaders = clean[:MAX_REPORT_ITEMS]
        weak = list(reversed(clean[-MAX_REPORT_ITEMS:]))
        return leaders, weak

    strength = market.get("sector_strength")
    if not isinstance(strength, dict):
        return [], []

    items = []
    for sector, data in strength.items():
        if isinstance(data, dict):
            score = _safe_float(
                data.get("strength_score")
                or data.get("score")
                or data.get("sector_score"),
                50.0,
            )
        else:
            score = _safe_float(data, 50.0)
        items.append({"sector": str(sector), "strength_score": round(score, 2)})

    items.sort(key=lambda item: _safe_float(item.get("strength_score")), reverse=True)
    return items[:MAX_REPORT_ITEMS], list(reversed(items[-MAX_REPORT_ITEMS:]))


def _breadth_state(market: Dict[str, Any]) -> Dict[str, Any]:
    breadth = market.get("index_breadth")
    breadth = breadth if isinstance(breadth, dict) else {}
    score = _safe_float(
        breadth.get("breadth_score")
        or breadth.get("participation_score")
        or market.get("breadth_score"),
        50.0,
    )

    if score >= 62:
        state = "BROAD_PARTICIPATION"
    elif score <= 38:
        state = "BREADTH_WEAKNESS"
    else:
        state = "MIXED_BREADTH"

    return {"state": state, "score": round(score, 2), "raw": breadth}


def _volatility_state(market: Dict[str, Any]) -> Dict[str, Any]:
    volatility = _safe_upper(market.get("volatility"))
    score = _safe_float(
        market.get("volatility_pressure_score")
        or market.get("panic_score")
        or market.get("risk_tone_volatility_score"),
        50.0,
    )

    if volatility in {"HIGH", "ELEVATED"} or score >= 65:
        state = "ELEVATED"
    elif volatility in {"LOW", "CALM"} or score <= 35:
        state = "CALM"
    else:
        state = "NORMAL"

    return {"state": state, "score": round(score, 2)}


def _setup_alignment(evaluated_setups: List[Dict[str, Any]], narrative_state: str, leaders: List[Dict[str, Any]], weak: List[Dict[str, Any]]) -> Dict[str, Any]:
    setups = [item for item in (evaluated_setups or [])[:MAX_SETUPS_TO_ANALYZE] if isinstance(item, dict)]
    leader_names = {str(item.get("sector") or item.get("name") or "").upper() for item in leaders}
    weak_names = {str(item.get("sector") or item.get("name") or "").upper() for item in weak}

    aligned = conflicting = neutral = 0
    scores = []
    contradictions = []

    for setup in setups:
        side = _safe_upper(setup.get("side"))
        raw = setup.get("raw") if isinstance(setup.get("raw"), dict) else setup
        sector = _safe_upper(raw.get("sector") or raw.get("stock_sector") or raw.get("sector_name"))
        score = 50.0

        if narrative_state == "RISK_ON" and side == "LONG":
            score += 18.0
        elif narrative_state == "RISK_ON" and side == "SHORT":
            score -= 18.0
            contradictions.append(f"{setup.get('symbol', 'UNKNOWN')} SHORT conflicts with risk-on narrative")
        elif narrative_state == "RISK_OFF" and side == "SHORT":
            score += 18.0
        elif narrative_state == "RISK_OFF" and side == "LONG":
            score -= 18.0
            contradictions.append(f"{setup.get('symbol', 'UNKNOWN')} LONG conflicts with risk-off narrative")

        if sector and sector in leader_names:
            score += 8.0
        if sector and sector in weak_names:
            score -= 8.0

        if setup.get("contradictions"):
            score -= min(15.0, len(setup.get("contradictions") or []) * 5.0)

        score = _clamp(score)
        scores.append(score)
        if score >= 58:
            aligned += 1
        elif score <= 42:
            conflicting += 1
        else:
            neutral += 1

    average = round(sum(scores) / len(scores), 2) if scores else 50.0
    return {
        "observed_setups": len(setups),
        "aligned_setups": aligned,
        "conflicting_setups": conflicting,
        "neutral_setups": neutral,
        "average_alignment_score": average,
        "contradiction_flags": contradictions[:MAX_REPORT_ITEMS],
    }


def _regime_transition(memory: Dict[str, Any], current_type: str) -> Dict[str, Any]:
    history = memory.get("history") if isinstance(memory, dict) else []
    if not isinstance(history, list) or not history:
        return {"changed": False, "from": None, "to": current_type}

    previous = history[-1] if isinstance(history[-1], dict) else {}
    prior_type = previous.get("narrative_type")
    return {"changed": bool(prior_type and prior_type != current_type), "from": prior_type, "to": current_type}


def _classify_narrative(risk_state: str, breadth: Dict[str, Any], volatility: Dict[str, Any], event: Dict[str, Any], leaders: List[Dict[str, Any]]) -> str:
    if event.get("state") == "HIGH":
        return "EVENT_CAUTION"
    if volatility.get("state") == "ELEVATED":
        return "VOLATILITY_EXPANSION"
    if breadth.get("state") == "BREADTH_WEAKNESS" and risk_state == "RISK_OFF":
        return "RISK_OFF_PRESSURE"
    if breadth.get("state") == "BROAD_PARTICIPATION" and risk_state == "RISK_ON":
        return "RISK_ON_TREND"
    if leaders:
        return "SECTOR_ROTATION_DAY"
    if risk_state == "NEUTRAL":
        return "CHOPPY_NEUTRAL"
    return "DATA_INSUFFICIENT_NEUTRAL"


def build_market_narrative_shadow(master_input: Dict[str, Any], context: Dict[str, Any], evaluated_setups: List[Dict[str, Any]]) -> Dict[str, Any]:
    market = deepcopy(_market_data(master_input if isinstance(master_input, dict) else {}))
    context_snapshot = deepcopy(context if isinstance(context, dict) else {})
    setup_snapshot = deepcopy(evaluated_setups if isinstance(evaluated_setups, list) else [])
    news_memory = _read_json(NEWS_MEMORY_PATH)
    lifecycle_memory = _read_json(LIFECYCLE_MEMORY_PATH)
    previous_memory = _read_json(MEMORY_PATH)

    risk_score = _safe_float(market.get("risk_tone_score"), 50.0)
    risk_tone = str(market.get("risk_tone") or market.get("direction") or "NEUTRAL")
    risk_state = _risk_state(risk_score, risk_tone)
    trend = _trend_from_market(market)
    breadth = _breadth_state(market)
    volatility = _volatility_state(market)
    event = _event_pressure(market, news_memory)
    leaders, weak = _sector_lists(market)
    narrative_type = _classify_narrative(risk_state, breadth, volatility, event, leaders)
    transition = _regime_transition(previous_memory, narrative_type)
    alignment = _setup_alignment(setup_snapshot, risk_state, leaders, weak)

    confidence = 45.0
    if market:
        confidence += 18.0
    if leaders:
        confidence += 10.0
    if breadth.get("raw"):
        confidence += 8.0
    if news_memory:
        confidence += 6.0
    if lifecycle_memory:
        confidence += 3.0
    if narrative_type == "DATA_INSUFFICIENT_NEUTRAL":
        confidence -= 15.0

    warnings = []
    contradiction_flags = list(alignment.get("contradiction_flags") or [])
    if transition.get("changed"):
        contradiction_flags.append(f"regime transition from {transition.get('from')} to {transition.get('to')}")
    if risk_state == "RISK_ON" and breadth.get("state") == "BREADTH_WEAKNESS":
        contradiction_flags.append("risk-on tone conflicts with weak breadth")
    if risk_state == "RISK_OFF" and breadth.get("state") == "BROAD_PARTICIPATION":
        contradiction_flags.append("risk-off tone conflicts with broad participation")
    if not market:
        warnings.append("market narrative source unavailable")

    return {
        "version": STATE_VERSION,
        "phase8_shadow_mode": PHASE8_SHADOW_MODE,
        "phase8_applied": True,
        "generated_at": _now(),
        "narrative_type": narrative_type,
        "risk_on_risk_off_state": risk_state,
        "risk_tone_score": round(risk_score, 2),
        "market_direction": trend,
        "breadth_pressure": breadth,
        "volatility_pressure": volatility,
        "panic_euphoria_detection": {
            "panic": bool(risk_state == "RISK_OFF" and volatility.get("state") == "ELEVATED"),
            "euphoria": bool(risk_state == "RISK_ON" and breadth.get("state") == "BROAD_PARTICIPATION"),
        },
        "event_pressure": event,
        "sector_leadership": leaders[:MAX_REPORT_ITEMS],
        "sector_weakness": weak[:MAX_REPORT_ITEMS],
        "regime_transition_detection": transition,
        "setup_alignment": alignment,
        "narrative_confidence": round(_clamp(confidence) / 100.0, 4),
        "macro_narrative_memory": {
            "learning_environment": context_snapshot.get("learning_environment"),
            "setup_environment": context_snapshot.get("setup_environment"),
            "lifecycle_memory_available": bool(lifecycle_memory),
            "news_memory_available": bool(news_memory),
        },
        "contradiction_flags": contradiction_flags[:MAX_REPORT_ITEMS],
        "warnings": warnings,
        "narrative_adjustment": 0.0,
    }


def _neutral_result(error: str | None = None) -> Dict[str, Any]:
    result = {
        "version": STATE_VERSION,
        "phase8_shadow_mode": PHASE8_SHADOW_MODE,
        "phase8_applied": False,
        "generated_at": _now(),
        "narrative_type": "DATA_INSUFFICIENT_NEUTRAL",
        "risk_on_risk_off_state": "NEUTRAL",
        "risk_tone_score": 50.0,
        "narrative_confidence": 0.0,
        "contradiction_flags": [],
        "warnings": ["phase8_failed_open"],
        "narrative_adjustment": 0.0,
    }
    if error:
        result["error"] = str(error)
    return result


def _load_memory() -> Dict[str, Any]:
    data = _read_json(MEMORY_PATH)
    if data:
        return data
    return {
        "version": STATE_VERSION,
        "last_updated": None,
        "current_narrative": {},
        "history": [],
    }


def _write_memory(snapshot: Dict[str, Any]) -> None:
    memory = _load_memory()
    history = memory.get("history") if isinstance(memory.get("history"), list) else []
    compact = {
        "generated_at": snapshot.get("generated_at"),
        "narrative_type": snapshot.get("narrative_type"),
        "risk_on_risk_off_state": snapshot.get("risk_on_risk_off_state"),
        "risk_tone_score": snapshot.get("risk_tone_score"),
        "narrative_confidence": snapshot.get("narrative_confidence"),
        "contradiction_count": len(snapshot.get("contradiction_flags") or []),
    }
    history.append(compact)
    history = history[-MAX_HISTORY:]

    payload = {
        "version": STATE_VERSION,
        "last_updated": _now(),
        "current_narrative": snapshot,
        "history": history,
    }
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _top_names(items: Iterable[Dict[str, Any]]) -> List[str]:
    names = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        names.append(str(item.get("sector") or item.get("name") or item.get("label") or item)[:80])
    return names[:MAX_REPORT_ITEMS]


def render_market_narrative_report(snapshot: Dict[str, Any]) -> str:
    alignment = snapshot.get("setup_alignment") if isinstance(snapshot.get("setup_alignment"), dict) else {}
    breadth = snapshot.get("breadth_pressure") if isinstance(snapshot.get("breadth_pressure"), dict) else {}
    volatility = snapshot.get("volatility_pressure") if isinstance(snapshot.get("volatility_pressure"), dict) else {}
    event = snapshot.get("event_pressure") if isinstance(snapshot.get("event_pressure"), dict) else {}

    lines = [
        "TITAN Phase 8 Market Narrative Shadow Report",
        "============================================",
        "",
        "Safety",
        "- Shadow advisory only.",
        "- No ranking, Telegram, execution, broker, alert-cap, duplicate, or market-hours changes.",
        "- Uses existing local/cached TITAN metadata only.",
        "",
        f"Updated: {snapshot.get('generated_at')}",
        f"Narrative Type: {snapshot.get('narrative_type')}",
        f"Risk State: {snapshot.get('risk_on_risk_off_state')}",
        f"Risk Tone Score: {snapshot.get('risk_tone_score')}",
        f"Market Direction: {snapshot.get('market_direction')}",
        f"Narrative Confidence: {snapshot.get('narrative_confidence')}",
        "",
        f"Breadth: {breadth.get('state')} | Score: {breadth.get('score')}",
        f"Volatility: {volatility.get('state')} | Score: {volatility.get('score')}",
        f"Event Pressure: {event.get('state')} | Score: {event.get('score')}",
        "",
        "Sector Leadership:",
    ]

    leaders = _top_names(snapshot.get("sector_leadership") or [])
    lines.extend([f"- {item}" for item in leaders] or ["- None observed"])

    lines.append("")
    lines.append("Sector Weakness:")
    weak = _top_names(snapshot.get("sector_weakness") or [])
    lines.extend([f"- {item}" for item in weak] or ["- None observed"])

    lines.extend(
        [
            "",
            "Setup Alignment:",
            f"- Observed setups: {alignment.get('observed_setups', 0)}",
            f"- Aligned setups: {alignment.get('aligned_setups', 0)}",
            f"- Conflicting setups: {alignment.get('conflicting_setups', 0)}",
            f"- Average alignment score: {alignment.get('average_alignment_score', 50.0)}",
            "",
            "Contradiction Flags:",
        ]
    )
    flags = snapshot.get("contradiction_flags") or []
    lines.extend([f"- {flag}" for flag in flags[:MAX_REPORT_ITEMS]] or ["- None observed"])

    warnings = snapshot.get("warnings") or []
    if warnings:
        lines.extend(["", "Warnings:"])
        lines.extend([f"- {warning}" for warning in warnings[:MAX_REPORT_ITEMS]])

    return "\n".join(lines) + "\n"


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


def refresh_market_narrative_report(
    master_input: Dict[str, Any],
    context: Dict[str, Any],
    evaluated_setups: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build and persist throttled Phase 8 shadow artifacts. Never raises.
    """
    try:
        snapshot = build_market_narrative_shadow(master_input, context, evaluated_setups)
        _write_memory(snapshot)

        if _report_throttled():
            return {"skipped": "CACHE_FRESH", "snapshot": snapshot}

        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(render_market_narrative_report(snapshot), encoding="utf-8")
        return snapshot
    except Exception as exc:
        return _neutral_result(str(exc))
