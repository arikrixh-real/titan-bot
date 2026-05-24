"""
TITAN Phase 38 - Test Mode Guard

Dry-run safety module for mission-era automation checks. Phase 38 is advisory
metadata only: it never places broker orders, sends Telegram alerts, changes
Supabase, mutates production data, deploys, or changes live runtime behavior.
"""

from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List


PHASE38_TEST_MODE = True
PHASE38_LIVE_EXECUTION_ENABLED = False
PHASE38_RANK_ADJUSTMENT = 0.0
PHASE38_RUNTIME_STATUS_PATH = Path("data") / "runtime" / "phase38_test_mode_guard_status.json"

PROTECTED_RUNTIME_MODES = {
    "TEST",
    "RESEARCH_ONLY",
    "RESEARCH_MODE",
    "SHADOW",
    "PAPER",
    "READ_ONLY",
    "HEALTH",
    "HEALTH_ONLY",
    "INTELLIGENCE_MODE",
    "WEEKEND_MODE",
}
LIVE_RUNTIME_MODES = {"LIVE", "REAL"}
KNOWN_RUNTIME_MODES = PROTECTED_RUNTIME_MODES | LIVE_RUNTIME_MODES | {"MARKET_MODE", "PRE_MARKET_MODE"}
LIVE_INTENTS = {
    "broker_order",
    "live_order",
    "place_order",
    "submit_order",
    "telegram_send",
    "live_telegram_alert",
}

BLOCKED_INTENTS = (
    "broker_order",
    "live_order",
    "place_order",
    "submit_order",
    "telegram_send",
    "live_telegram_alert",
    "supabase_schema",
    "supabase_migration",
    "production_data_mutation",
    "vps_deploy",
    "daemon_restart",
    "auto_commit",
    "auto_push",
)


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_text(value: Any) -> str:
    try:
        return "" if value is None else str(value).strip()
    except Exception:
        return ""


def _safe_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    return [value]


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _safe_text(value).lower()
    return text in {"1", "true", "yes", "y", "on", "enabled"}


def _upper_text(value: Any) -> str:
    return _safe_text(value).upper()


def _lower_tokens(values: Iterable[Any]) -> List[str]:
    tokens: List[str] = []
    for value in values:
        text = _safe_text(value).lower()
        if text:
            tokens.append(text)
    return tokens


def normalize_phase38_input(candidate: Any = None, context: Any = None) -> Dict[str, Any]:
    candidate_dict = deepcopy(_as_dict(candidate))
    context_dict = deepcopy(_as_dict(context))
    requested_actions = _safe_list(context_dict.get("requested_actions"))
    requested_actions.extend(_safe_list(candidate_dict.get("requested_actions")))
    return {
        "candidate": candidate_dict,
        "context": context_dict,
        "requested_actions": requested_actions,
    }


def detect_blocked_intents(candidate: Any = None, context: Any = None) -> List[str]:
    payload = normalize_phase38_input(candidate, context)
    searchable_values = list(payload["requested_actions"])
    searchable_values.extend(
        [
            payload["context"].get("mode"),
            payload["context"].get("execution_mode"),
            payload["context"].get("deploy_mode"),
            payload["context"].get("telegram_mode"),
            payload["candidate"].get("action"),
            payload["candidate"].get("execution_action"),
            payload["candidate"].get("alert_action"),
        ]
    )

    tokens = _lower_tokens(searchable_values)
    detected = []
    for intent in BLOCKED_INTENTS:
        phrase = intent.replace("_", " ")
        if any(intent in token or phrase in token for token in tokens):
            detected.append(intent)
    return sorted(set(detected))


def evaluate_phase38_test_mode(candidate: Any = None, context: Any = None) -> Dict[str, Any]:
    payload = normalize_phase38_input(candidate, context)
    blocked_intents = detect_blocked_intents(payload["candidate"], payload["context"])
    dry_run_ready = not blocked_intents
    return {
        "phase38_applied": True,
        "phase38_test_mode": PHASE38_TEST_MODE,
        "phase38_live_execution_enabled": PHASE38_LIVE_EXECUTION_ENABLED,
        "phase38_rank_adjustment": PHASE38_RANK_ADJUSTMENT,
        "phase38_dry_run_ready": dry_run_ready,
        "phase38_blocked_intents": blocked_intents,
        "phase38_guardrails": {
            "broker_execution": "blocked",
            "telegram_live_alert_behavior": "unchanged",
            "supabase_schema": "blocked",
            "production_data_mutation": "blocked",
            "vps_deploy": "blocked",
            "auto_commit": "blocked",
            "auto_push": "blocked",
        },
        "phase38_generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "phase38_notes": [
            "Phase 38 is dry-run metadata only.",
            "No live runtime behavior is changed by this module.",
        ],
    }


def evaluate_phase38_runtime_guard(context: Any = None) -> Dict[str, Any]:
    context_dict = deepcopy(_as_dict(context))
    runtime_mode = _upper_text(
        context_dict.get("runtime_mode")
        or context_dict.get("mode")
        or os.getenv("TITAN_RUNTIME_MASTER_BRAIN_MODE")
        or "READ_ONLY"
    )
    execution_mode = _upper_text(context_dict.get("execution_mode"))
    research_mode = _upper_text(context_dict.get("research_mode"))
    scheduler_mode = _upper_text(context_dict.get("scheduler_mode") or context_dict.get("current_mode"))

    modes = {
        mode
        for mode in (runtime_mode, execution_mode, research_mode, scheduler_mode)
        if mode
    }
    protected_modes = sorted(modes & PROTECTED_RUNTIME_MODES)
    live_modes = sorted(modes & LIVE_RUNTIME_MODES)
    unknown_modes = sorted(mode for mode in modes if mode not in KNOWN_RUNTIME_MODES)

    blocked_intents = detect_blocked_intents(context=context_dict)
    live_intents = sorted(set(blocked_intents) & LIVE_INTENTS)
    live_execution_enabled = _safe_bool(context_dict.get("live_execution_enabled"))
    telegram_enabled = _safe_bool(context_dict.get("telegram_enabled"))
    broker_enabled = _safe_bool(
        context_dict.get("broker_enabled")
        or context_dict.get("broker_execution_enabled")
        or context_dict.get("live_order_allowed")
    )
    lifecycle_mutation_enabled = _safe_bool(context_dict.get("lifecycle_mutation_enabled"))
    replay_active = _safe_bool(context_dict.get("replay_active") or context_dict.get("historical_replay"))
    research_only = _safe_bool(context_dict.get("research_only")) or "RESEARCH_ONLY" in modes
    test_mode = _safe_bool(context_dict.get("test_mode")) or "TEST" in modes
    paper_mode = _safe_bool(context_dict.get("paper_mode")) or "PAPER" in modes
    shadow_mode = _safe_bool(context_dict.get("shadow_mode")) or "SHADOW" in modes

    unsafe_states: List[str] = []
    if unknown_modes:
        unsafe_states.append("UNKNOWN_RUNTIME_MODE_FAIL_CLOSED")
    if protected_modes and live_execution_enabled:
        unsafe_states.append("PROTECTED_MODE_WITH_LIVE_EXECUTION")
    if protected_modes and telegram_enabled:
        unsafe_states.append("PROTECTED_MODE_WITH_TELEGRAM")
    if protected_modes and broker_enabled:
        unsafe_states.append("PROTECTED_MODE_WITH_BROKER")
    if protected_modes and lifecycle_mutation_enabled:
        unsafe_states.append("PROTECTED_MODE_WITH_LIFECYCLE_MUTATION")
    if protected_modes and live_intents:
        unsafe_states.append("PROTECTED_MODE_WITH_LIVE_INTENT")
    if replay_active and (live_modes or live_execution_enabled or telegram_enabled or broker_enabled or live_intents):
        unsafe_states.append("REPLAY_WITH_LIVE_CAPABILITY")
    if research_only and (live_execution_enabled or telegram_enabled or broker_enabled or live_intents):
        unsafe_states.append("RESEARCH_ONLY_WITH_LIVE_CAPABILITY")
    if test_mode and (live_execution_enabled or telegram_enabled or broker_enabled or lifecycle_mutation_enabled):
        unsafe_states.append("TEST_WITH_MUTATING_CAPABILITY")
    if shadow_mode and (live_execution_enabled or telegram_enabled or broker_enabled or lifecycle_mutation_enabled):
        unsafe_states.append("SHADOW_WITH_MUTATING_CAPABILITY")
    if paper_mode and (live_execution_enabled or broker_enabled or live_intents):
        unsafe_states.append("PAPER_WITH_LIVE_CAPABILITY")
    if runtime_mode == "LIVE" and (live_execution_enabled or telegram_enabled or broker_enabled or live_intents):
        unsafe_states.append("LIVE_MODE_REQUIRES_REAL_OWNER")

    live_ready = bool(live_modes) and not protected_modes and not unsafe_states
    return {
        "phase38_runtime_guard_applied": True,
        "phase38_runtime_allowed": not unsafe_states,
        "phase38_fail_closed": bool(unsafe_states),
        "phase38_runtime_mode": runtime_mode,
        "phase38_modes_detected": sorted(modes),
        "phase38_protected_modes_detected": protected_modes,
        "phase38_live_modes_detected": live_modes,
        "phase38_unknown_modes_detected": unknown_modes,
        "phase38_live_ready": live_ready,
        "phase38_live_execution_enabled": False if unsafe_states else live_execution_enabled,
        "phase38_blocked_intents": blocked_intents,
        "phase38_unsafe_states": sorted(set(unsafe_states)),
        "phase38_runtime_guardrails": {
            "test_mode": "live, telegram, broker, and lifecycle mutation blocked",
            "research_only_mode": "live, telegram, broker, and live intents blocked",
            "shadow_mode": "live, telegram, broker, and lifecycle mutation blocked",
            "paper_mode": "broker/live execution blocked; local paper simulation remains external",
            "live_mode": "validated only; Phase 38 never enables live execution",
            "replay": "cannot carry live, telegram, or broker capability",
        },
        "phase38_generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def write_phase38_runtime_status(context: Any = None, path: Path = PHASE38_RUNTIME_STATUS_PATH) -> Dict[str, Any]:
    status = evaluate_phase38_runtime_guard(context)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, indent=2, sort_keys=True), encoding="utf-8")
    return status


def apply_phase38_test_mode(candidate: Any = None, context: Any = None) -> Dict[str, Any]:
    candidate_copy = deepcopy(_as_dict(candidate))
    candidate_copy.update(evaluate_phase38_test_mode(candidate_copy, context))
    return candidate_copy
