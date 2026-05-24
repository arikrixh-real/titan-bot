"""
TITAN Phase 38 - Test Mode Guard

Dry-run safety module for mission-era automation checks. Phase 38 is advisory
metadata only: it never places broker orders, sends Telegram alerts, changes
Supabase, mutates production data, deploys, or changes live runtime behavior.
"""

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Iterable, List


PHASE38_TEST_MODE = True
PHASE38_LIVE_EXECUTION_ENABLED = False
PHASE38_RANK_ADJUSTMENT = 0.0

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


def apply_phase38_test_mode(candidate: Any = None, context: Any = None) -> Dict[str, Any]:
    candidate_copy = deepcopy(_as_dict(candidate))
    candidate_copy.update(evaluate_phase38_test_mode(candidate_copy, context))
    return candidate_copy
