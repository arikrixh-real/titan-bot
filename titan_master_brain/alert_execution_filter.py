"""
TITAN MASTER BRAIN - ALERT / EXECUTION FILTER
STEP 6

Purpose:
- Take final selected candidates from Final Decision Engine.
- Decide which ones are allowed to move forward for Telegram alert / execution layer.
- Enforce safety:
  - Max alerts per cycle
  - Only selected candidates
  - Avoid rejected setups
  - Avoid low-confidence weak setups
  - Keep decision explainable

This file does NOT send Telegram alerts yet.
It only prepares "approved_for_alert" candidates safely.
"""

from typing import List, Dict, Any


MAX_ALERTS_PER_CYCLE = 3


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _is_alert_allowed(candidate: Dict[str, Any]) -> tuple[bool, str]:
    """
    Decide if one candidate can move forward to alert/execution.
    """

    trade_permission = str(candidate.get("trade_permission", "")).upper()
    low_edge_day = candidate.get("low_edge_day") if isinstance(candidate.get("low_edge_day"), dict) else {}

    if candidate.get("no_trade_block_alert") or trade_permission == "BLOCK" or low_edge_day.get("is_low_edge_day"):
        return False, "Blocked by Phase 35 no-trade intelligence"

    if trade_permission == "WAIT":
        return False, "Wait mode from Phase 35 no-trade intelligence"

    decision = str(candidate.get("decision", "")).upper()
    confidence = str(candidate.get("confidence", "")).upper()
    score = _safe_float(candidate.get("score"))
    rr = _safe_float(candidate.get("rr"))

    # Never alert rejected setup
    if decision == "REJECT":
        return False, "Rejected by setup reasoning"

    # TRUST can pass if RR is acceptable
    if decision == "TRUST" and rr >= 1.5:
        return True, "Trusted setup with acceptable RR"

    # DOWNGRADE can pass only if score and RR are strong
    if decision == "DOWNGRADE":
        if confidence in {"MEDIUM", "HIGH"} and score >= 3.0 and rr >= 2.0:
            return True, "Downgraded but strong enough for watch/alert candidate"
        return False, "Downgraded setup not strong enough"

    return False, "Unknown or weak decision state"


def filter_alert_candidates(final_decisions: Dict[str, Any]) -> Dict[str, Any]:
    """
    Filters final selected candidates into alert-approved candidates.
    """

    selected = final_decisions.get("selected", []) or []

    approved = []
    blocked = []
    summary = []

    if not selected:
        return {
            "approved_for_alert": [],
            "blocked": [],
            "summary": [
                "No final selected candidates available.",
                "No alert should be sent this cycle."
            ],
            "alert_mode": "NO_ALERT"
        }

    for candidate in selected:
        allowed, reason = _is_alert_allowed(candidate)

        record = dict(candidate)
        record["alert_filter_reason"] = reason

        if allowed:
            approved.append(record)
        else:
            blocked.append(record)

    # Limit alerts per cycle
    approved = approved[:MAX_ALERTS_PER_CYCLE]

    if approved:
        summary.append(f"{len(approved)} candidate(s) approved for alert/execution layer.")
        summary.append("Only these should move forward. Others remain internal learning data.")
        alert_mode = "ALERT_CANDIDATES_READY"
    else:
        summary.append("No candidates passed alert/execution filter.")
        summary.append("Best action: observe only.")
        alert_mode = "NO_ALERT"

    return {
        "approved_for_alert": approved,
        "blocked": blocked,
        "summary": summary,
        "alert_mode": alert_mode
    }


def print_alert_filter_result(result: Dict[str, Any]) -> None:
    print("\n[MasterBrain] Alert / Execution Filter:\n")

    for line in result.get("summary", []):
        print(f"[AlertFilter] {line}")

    approved = result.get("approved_for_alert", [])

    if approved:
        print("\n[AlertFilter] Approved candidates:")
        for idx, c in enumerate(approved, start=1):
            print(
                f"{idx}. {c.get('symbol', 'UNKNOWN')} → "
                f"{c.get('decision')} | {c.get('confidence')} | "
                f"Score: {c.get('score')} | RR: {c.get('rr')} | "
                f"{c.get('alert_filter_reason')}"
            )
    else:
        print("[AlertFilter] No approved alert candidates.")
