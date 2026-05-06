"""
TITAN MASTER BRAIN - FINAL DECISION ENGINE
STEP 5

Purpose:
- Take evaluated setups from setup_reasoning_engine
- Select only the best candidates
- Reject weak/noisy setups
- Prepare final action list for Master Brain

This does NOT send Telegram alerts yet.
This does NOT execute trades yet.
It only makes final decision recommendations safely.
"""

from typing import List, Dict, Any


MAX_FINAL_CANDIDATES = 3


def _decision_rank(decision: str) -> int:
    decision = str(decision or "").upper()

    if decision == "TRUST":
        return 3
    if decision == "DOWNGRADE":
        return 2
    if decision == "REJECT":
        return 1

    return 0


def _confidence_rank(confidence: str) -> int:
    confidence = str(confidence or "").upper()

    if confidence == "HIGH":
        return 3
    if confidence == "MEDIUM":
        return 2
    if confidence == "LOW":
        return 1

    return 0


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def make_final_decisions(
    evaluated_setups: List[Dict[str, Any]],
    context: Dict[str, Any],
    max_candidates: int = MAX_FINAL_CANDIDATES,
) -> Dict[str, Any]:
    """
    Produces final Master Brain decision.

    Returns:
    {
        "action_mode": "TRADE_CANDIDATES_FOUND" / "OBSERVE_ONLY",
        "selected": [...],
        "rejected": [...],
        "summary": [...]
    }
    """

    evaluated_setups = evaluated_setups or []

    selected_pool = []
    rejected = []
    summary = []

    trading_mode = context.get("trading_mode", "OBSERVATION")
    risk_level = context.get("risk_level", "UNKNOWN")
    learning_env = context.get("learning_environment", "UNKNOWN")

    summary.append(f"Trading mode: {trading_mode}")
    summary.append(f"Risk level: {risk_level}")
    summary.append(f"Learning environment: {learning_env}")

    if not evaluated_setups:
        return {
            "action_mode": "OBSERVE_ONLY",
            "selected": [],
            "rejected": [],
            "summary": summary + [
                "No evaluated setups available.",
                "Best action: observe and wait."
            ],
        }

    for setup in evaluated_setups:
        decision = str(setup.get("decision", "REJECT")).upper()
        confidence = str(setup.get("confidence", "LOW")).upper()

        if decision == "TRUST":
            selected_pool.append(setup)

        elif decision == "DOWNGRADE":
            # Downgraded setups are allowed only if market is selective/allowed.
            if trading_mode in ["SELECTIVE", "AGGRESSIVE"] and risk_level != "HIGH":
                selected_pool.append(setup)
            else:
                rejected.append(setup)

        else:
            rejected.append(setup)

    # Sort best first
    selected_pool.sort(
        key=lambda s: (
            _decision_rank(s.get("decision")),
            _confidence_rank(s.get("confidence")),
            _safe_float(s.get("score")),
            _safe_float(s.get("rr")),
        ),
        reverse=True
    )

    selected = selected_pool[:max_candidates]
    overflow_rejected = selected_pool[max_candidates:]
    rejected.extend(overflow_rejected)

    if selected:
        summary.append(f"{len(selected)} final candidate(s) selected.")
        summary.append("Only the strongest setups should move forward.")
        action_mode = "TRADE_CANDIDATES_FOUND"
    else:
        summary.append("No final candidates passed the Master Brain decision layer.")
        summary.append("Best action: observe only.")
        action_mode = "OBSERVE_ONLY"

    return {
        "action_mode": action_mode,
        "selected": selected,
        "rejected": rejected,
        "summary": summary,
    }


def print_final_decisions(decisions: Dict[str, Any]) -> None:
    print("\n[MasterBrain] Final Decision Engine:\n")

    for line in decisions.get("summary", []):
        print(f"[FinalDecision] {line}")

    selected = decisions.get("selected", [])

    if selected:
        print("\n[FinalDecision] Selected candidates:")
        for idx, setup in enumerate(selected, start=1):
            symbol = setup.get("symbol", "UNKNOWN")
            decision = setup.get("decision", "UNKNOWN")
            confidence = setup.get("confidence", "UNKNOWN")
            score = setup.get("score", "NA")
            rr = setup.get("rr", "NA")
            print(f"{idx}. {symbol} → {decision} | {confidence} | Score: {score} | RR: {rr}")
    else:
        print("[FinalDecision] No selected candidates.")