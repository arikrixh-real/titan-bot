"""
TITAN MASTER BRAIN - DAILY ALERT MANAGER
STEP 7C SMART QUALITY CONTROL

Goal:
- Exactly 3 Telegram signal candidates per trading day.
- Not first 3 setups.
- Select best available candidates using smart quality tiers.
- If high-quality exists, prefer high-quality.
- If only medium/low exists, still fill remaining daily quota with best available.
- All non-selected setups become internal learning trades.

IMPORTANT:
This file does NOT send Telegram messages yet.
It only decides:
- selected_for_alert
- internal_learning_trades
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, List


IST = ZoneInfo("Asia/Kolkata")

STATE_DIR = Path("state")
STATE_FILE = STATE_DIR / "daily_alert_state.json"

MAX_DAILY_ALERTS = 3


def _today_key() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _confidence_points(confidence: str) -> float:
    confidence = str(confidence or "").upper()

    if confidence == "HIGH":
        return 3.0
    if confidence == "MEDIUM":
        return 2.0
    if confidence == "LOW":
        return 1.0

    return 0.0


def _decision_points(decision: str) -> float:
    decision = str(decision or "").upper()

    if decision == "TRUST":
        return 3.0
    if decision == "DOWNGRADE":
        return 2.0
    if decision == "REJECT":
        return 0.5

    return 0.0


def _extract_raw(candidate: Dict[str, Any]) -> Dict[str, Any]:
    raw = candidate.get("raw")
    return raw if isinstance(raw, dict) else candidate


def _extract_confirmations(candidate: Dict[str, Any]) -> int:
    raw = _extract_raw(candidate)

    setup_context = raw.get("setup_context", {})
    if isinstance(setup_context, dict):
        return _safe_int(setup_context.get("confirmations"), 0)

    return _safe_int(raw.get("confirmations"), 0)


def _trend_alignment_points(candidate: Dict[str, Any]) -> float:
    raw = _extract_raw(candidate)

    side = str(candidate.get("side") or raw.get("side") or "").upper()
    trend = ""

    market_context = raw.get("market_context", {})
    if isinstance(market_context, dict):
        trend = str(market_context.get("trend") or "").upper()

    if not trend:
        trend = str(raw.get("trend") or "").upper()

    if side == "LONG" and trend == "BULLISH":
        return 2.0

    if side == "SHORT" and trend == "BEARISH":
        return 2.0

    return 0.0


def calculate_daily_alert_rank(candidate: Dict[str, Any]) -> float:
    """
    Multi-factor ranking.
    Higher rank = better alert priority.
    """

    score = _safe_float(candidate.get("score"), 0.0)
    rr = _safe_float(candidate.get("rr"), 0.0)
    confirmations = _extract_confirmations(candidate)

    rank = 0.0

    rank += score * 10.0
    rank += rr * 5.0
    rank += _decision_points(candidate.get("decision")) * 8.0
    rank += _confidence_points(candidate.get("confidence")) * 5.0
    rank += confirmations * 3.0
    rank += _trend_alignment_points(candidate) * 5.0

    return round(rank, 4)


def classify_quality_tier(candidate: Dict[str, Any]) -> str:
    """
    Human-like quality classification.

    Tier order:
    ELITE > STRONG > GOOD > FALLBACK
    """

    decision = str(candidate.get("decision") or "").upper()
    confidence = str(candidate.get("confidence") or "").upper()
    score = _safe_float(candidate.get("score"), 0.0)
    rr = _safe_float(candidate.get("rr"), 0.0)
    confirmations = _extract_confirmations(candidate)
    trend_points = _trend_alignment_points(candidate)

    if decision == "TRUST" and confidence == "HIGH" and score >= 3.2 and rr >= 2.0 and confirmations >= 5:
        return "ELITE"

    if decision in {"TRUST", "DOWNGRADE"} and confidence in {"HIGH", "MEDIUM"} and score >= 3.0 and rr >= 2.0 and confirmations >= 5:
        return "STRONG"

    if decision in {"TRUST", "DOWNGRADE"} and confidence in {"HIGH", "MEDIUM"} and score >= 2.5 and rr >= 1.8:
        return "GOOD"

    # User rule: if only low probability setups exist, still choose best available.
    # So weak candidates are fallback, not ignored completely.
    if score > 0 and rr >= 1.5:
        return "FALLBACK"

    return "IGNORE"


def _quality_tier_rank(tier: str) -> int:
    tier = str(tier or "").upper()

    if tier == "ELITE":
        return 4
    if tier == "STRONG":
        return 3
    if tier == "GOOD":
        return 2
    if tier == "FALLBACK":
        return 1

    return 0


def _candidate_key(candidate: Dict[str, Any]) -> str:
    """
    FINAL DUPLICATE ALERT FIX:
    Only ONE Telegram alert per symbol + side per trading day.

    Earlier key used entry/sl/target, so tiny level changes created new keys
    and caused repeated Telegram alerts every 5 minutes.
    """

    raw = _extract_raw(candidate)

    symbol = str(
        candidate.get("symbol")
        or raw.get("symbol")
        or "UNKNOWN"
    ).strip().upper()

    side = str(
        candidate.get("side")
        or raw.get("side")
        or raw.get("direction")
        or raw.get("trade_side")
        or ""
    ).strip().upper()

    return f"{_today_key()}|{symbol}|{side}"


def _load_state() -> Dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    today = _today_key()

    if not STATE_FILE.exists():
        return {
            "date": today,
            "alerts_sent": 0,
            "alerted_keys": []
        }

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)

        if state.get("date") != today:
            return {
                "date": today,
                "alerts_sent": 0,
                "alerted_keys": []
            }

        state.setdefault("alerts_sent", 0)
        state.setdefault("alerted_keys", [])
        return state

    except Exception:
        return {
            "date": today,
            "alerts_sent": 0,
            "alerted_keys": []
        }


def _save_state(state: Dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _collect_candidate_pool(alert_filter_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Collect all possible candidates.

    Priority:
    1. approved_for_alert
    2. selected
    3. fallback: rejected/blocked if needed
    """

    pool = []

    for key in ["approved_for_alert", "selected", "blocked", "rejected"]:
        items = alert_filter_result.get(key, []) or []
        if isinstance(items, list):
            pool.extend(items)

    # Deduplicate by key
    seen = set()
    deduped = []

    for candidate in pool:
        if not isinstance(candidate, dict):
            continue

        key = _candidate_key(candidate)
        if key in seen:
            continue

        seen.add(key)
        deduped.append(candidate)

    return deduped


def select_daily_alerts(alert_filter_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Select exactly up to remaining daily alert slots.

    Important:
    - If enough candidates exist, selects remaining_slots count.
    - If fewer candidates exist, selects only available candidates.
    - Remaining candidates become internal learning trades.
    """

    state = _load_state()

    already_sent = _safe_int(state.get("alerts_sent"), 0)
    remaining_slots = max(0, MAX_DAILY_ALERTS - already_sent)

    candidate_pool = _collect_candidate_pool(alert_filter_result)
    alerted_keys = set(state.get("alerted_keys", []))

    ranked = []
    internal_learning = []

    for candidate in candidate_pool:
        key = _candidate_key(candidate)

        enriched = dict(candidate)
        enriched["daily_alert_rank"] = calculate_daily_alert_rank(candidate)
        enriched["quality_tier"] = classify_quality_tier(candidate)
        enriched["daily_alert_key"] = key

        if key in alerted_keys:
            enriched["daily_alert_status"] = "ALREADY_ALERTED_TODAY"
            internal_learning.append(enriched)
            continue

        if enriched["quality_tier"] == "IGNORE":
            enriched["daily_alert_status"] = "INTERNAL_LEARNING_ONLY_IGNORE_TIER"
            internal_learning.append(enriched)
            continue

        ranked.append(enriched)

    # Smart quality sorting:
    # tier first, then rank score
    ranked.sort(
        key=lambda x: (
            _quality_tier_rank(x.get("quality_tier")),
            x.get("daily_alert_rank", 0),
        ),
        reverse=True
    )

    selected_for_alert = ranked[:remaining_slots]
    not_alerted = ranked[remaining_slots:]

    for item in not_alerted:
        internal_learning.append({
            **item,
            "daily_alert_status": "INTERNAL_LEARNING_ONLY_NOT_TOP_3"
        })

    selected_tiers = {}
    for item in selected_for_alert:
        tier = item.get("quality_tier", "UNKNOWN")
        selected_tiers[tier] = selected_tiers.get(tier, 0) + 1

    return {
        "date": state.get("date"),
        "daily_limit": MAX_DAILY_ALERTS,
        "already_sent": already_sent,
        "remaining_slots": remaining_slots,
        "selected_for_alert": selected_for_alert,
        "internal_learning_trades": internal_learning,
        "quality_summary": selected_tiers,
        "summary": [
            f"Daily alert rule active: exactly {MAX_DAILY_ALERTS} signals per trading day target.",
            f"Already sent today: {already_sent}",
            f"Remaining slots today: {remaining_slots}",
            f"Candidate pool studied: {len(candidate_pool)}",
            f"Selected now: {len(selected_for_alert)}",
            f"Internal learning trades: {len(internal_learning)}",
            f"Selected quality tiers: {selected_tiers}",
        ]
    }


def mark_alerts_sent(sent_candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Call this AFTER Telegram alert is actually sent.
    """

    state = _load_state()
    alerted_keys = set(state.get("alerted_keys", []))

    sent_count = 0

    for candidate in sent_candidates or []:
        key = candidate.get("daily_alert_key") or _candidate_key(candidate)
        if key not in alerted_keys:
            alerted_keys.add(key)
            sent_count += 1

    state["alerted_keys"] = list(alerted_keys)
    state["alerts_sent"] = min(MAX_DAILY_ALERTS, _safe_int(state.get("alerts_sent"), 0) + sent_count)

    _save_state(state)

    return state


def print_daily_alert_selection(result: Dict[str, Any]) -> None:
    print("\n[MasterBrain] Daily Alert Manager:\n")

    for line in result.get("summary", []):
        print(f"[DailyAlert] {line}")

    selected = result.get("selected_for_alert", [])

    if selected:
        print("\n[DailyAlert] Selected for Telegram alert:")
        for idx, c in enumerate(selected, start=1):
            print(
                f"{idx}. {c.get('symbol', 'UNKNOWN')} | "
                f"Tier: {c.get('quality_tier')} | "
                f"Rank: {c.get('daily_alert_rank')} | "
                f"Decision: {c.get('decision')} | Confidence: {c.get('confidence')} | "
                f"Score: {c.get('score')} | RR: {c.get('rr')}"
            )
    else:
        print("[DailyAlert] No alert slots selected this cycle.")