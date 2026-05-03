from titan_brain.learning_engine import load_memory


def extract_pattern_tags(reason_text):
    reason_text = str(reason_text).lower()

    tags = []

    keywords = {
        "volume": "VOLUME",
        "spike": "VOLUME_SPIKE",
        "compression": "COMPRESSION",
        "breakout": "BREAKOUT",
        "relative strength": "RELATIVE_STRENGTH",
        "trend aligned": "TREND_ALIGNED",
        "rejection": "REJECTION",
        "fakeout": "FAKEOUT",
        "trap": "TRAP"
    }

    for keyword, tag in keywords.items():
        if keyword in reason_text:
            tags.append(tag)

    return tags


def calculate_adaptive_learning(stock_data):
    memory = load_memory()

    current_tags = extract_pattern_tags(stock_data.get("reason", ""))
    current_side = str(stock_data.get("side", "")).upper()

    completed_trades = [
        trade for trade in memory
        if trade.get("outcome") in ["T1_HIT", "T2_HIT", "SL_HIT"]
    ]

    if len(completed_trades) < 5:
        return {
            "adjustment": 0,
            "status": "COLLECTING_DATA",
            "reason": "Not enough completed trades for adaptive learning",
            "matched_trades": 0,
            "win_rate": None,
            "loss_rate": None,
            "lessons": []
        }

    matched = []

    for trade in completed_trades:
        past_tags = extract_pattern_tags(trade.get("setup_reason", ""))
        past_side = str(trade.get("side", "")).upper()

        if past_side != current_side:
            continue

        common_tags = set(current_tags).intersection(set(past_tags))

        if len(common_tags) >= 2:
            matched.append(trade)

    if len(matched) < 3:
        return {
            "adjustment": 0,
            "status": "NO_RELIABLE_PATTERN",
            "reason": "Not enough similar completed trades",
            "matched_trades": len(matched),
            "win_rate": None,
            "loss_rate": None,
            "lessons": []
        }

    wins = 0
    losses = 0
    lessons = []

    for trade in matched:
        outcome = trade.get("outcome")

        if outcome in ["T1_HIT", "T2_HIT"]:
            wins += 1
        elif outcome == "SL_HIT":
            losses += 1

        outcome_analysis = trade.get("outcome_analysis") or {}
        for lesson in outcome_analysis.get("lessons", []):
            if lesson not in lessons:
                lessons.append(lesson)

    total = wins + losses

    if total == 0:
        return {
            "adjustment": 0,
            "status": "INSUFFICIENT_OUTCOME_DATA",
            "reason": "Similar trades exist but outcomes are incomplete",
            "matched_trades": len(matched),
            "win_rate": None,
            "loss_rate": None,
            "lessons": lessons[:3]
        }

    win_rate = wins / total
    loss_rate = losses / total

    adjustment = 0
    reason = "Neutral adaptive learning impact"

    if win_rate >= 0.75:
        adjustment = 15
        reason = "This pattern has strong historical success"
    elif win_rate >= 0.60:
        adjustment = 8
        reason = "This pattern has positive historical edge"
    elif loss_rate >= 0.60:
        adjustment = -15
        reason = "This pattern has poor historical performance"
    elif loss_rate >= 0.50:
        adjustment = -8
        reason = "This pattern is slightly weak historically"

    return {
        "adjustment": adjustment,
        "status": "ACTIVE",
        "reason": reason,
        "matched_trades": len(matched),
        "win_rate": round(win_rate * 100, 2),
        "loss_rate": round(loss_rate * 100, 2),
        "lessons": lessons[:3]
    }