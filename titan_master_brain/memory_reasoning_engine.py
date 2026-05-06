# TITAN MASTER BRAIN - MEMORY REASONING ENGINE
# Safe memory logic: no learning from weak/no confirmed evidence.

MIN_CONFIRMED_OUTCOMES = 5

def _normalize_outcome(value):
    if value is None:
        return "OPEN"

    text = str(value).strip().upper()

    if text in ["TP", "TARGET", "TARGET_HIT", "WIN", "PROFIT", "SUCCESS"]:
        return "WIN"

    if text in ["SL", "STOPLOSS", "STOP_LOSS", "LOSS", "FAILED", "FAIL"]:
        return "LOSS"

    return "OPEN"


def analyze_memory(memory):
    wins = 0
    losses = 0
    open_or_unknown = 0

    recent = memory.get("recent", []) or []

    for trade in recent:
        outcome = (
            trade.get("outcome")
            or trade.get("result")
            or trade.get("status")
            or trade.get("trade_result")
        )

        normalized = _normalize_outcome(outcome)

        if normalized == "WIN":
            wins += 1
        elif normalized == "LOSS":
            losses += 1
        else:
            open_or_unknown += 1

    confirmed = wins + losses

    result = {
        "total_records": len(recent),
        "confirmed_outcomes": confirmed,
        "wins": wins,
        "losses": losses,
        "open_or_unknown": open_or_unknown,
        "win_rate": None,
        "bias": "INSUFFICIENT_DATA",
        "confidence": "LOW",
        "decision_effect": "OBSERVE_ONLY",
        "insights": []
    }

    if len(recent) == 0:
        result["insights"].append("No memory records found yet.")
        result["insights"].append("Collect more outcomes before changing logic.")
        return result

    if confirmed == 0:
        result["insights"].append(
            f"{len(recent)} records found, but no confirmed TP/SL outcomes."
        )
        result["insights"].append("No learning adjustment should be applied yet.")
        return result

    result["win_rate"] = round(wins / confirmed, 4)

    if confirmed < MIN_CONFIRMED_OUTCOMES:
        result["insights"].append(
            f"Only {confirmed} confirmed outcomes. Minimum needed: {MIN_CONFIRMED_OUTCOMES}."
        )
        result["insights"].append("Observe only. Do not change weights.")
        return result

    if result["win_rate"] >= 0.60:
        result["bias"] = "FAVORABLE"
        result["confidence"] = "MEDIUM"
        result["decision_effect"] = "ALLOW_STRONG_SETUPS"
        result["insights"].append("Recent confirmed performance is favorable.")
    elif result["win_rate"] <= 0.40:
        result["bias"] = "UNFAVORABLE"
        result["confidence"] = "MEDIUM"
        result["decision_effect"] = "REDUCE_CONFIDENCE"
        result["insights"].append("Recent confirmed performance is weak.")
    else:
        result["bias"] = "NEUTRAL"
        result["confidence"] = "MEDIUM"
        result["decision_effect"] = "NO_CHANGE"
        result["insights"].append("Recent confirmed performance is mixed.")

    return result