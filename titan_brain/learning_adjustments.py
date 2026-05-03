from titan_brain.learning_engine import load_memory


def compute_learning_adjustment(stock_data):
    memory = load_memory()

    if not memory:
        return 0, "No past data"

    pattern_matches = []
    setup_reason = str(stock_data.get("reason", "")).lower()

    for trade in memory:
        if trade.get("outcome") == "PENDING":
            continue

        past_reason = str(trade.get("setup_reason", "")).lower()

        match_score = 0

        if "volume" in setup_reason and "volume" in past_reason:
            match_score += 1
        if "breakout" in setup_reason and "breakout" in past_reason:
            match_score += 1
        if "compression" in setup_reason and "compression" in past_reason:
            match_score += 1

        if match_score >= 2:
            pattern_matches.append(trade)

    if not pattern_matches:
        return 0, "No similar past trades"

    wins = 0
    losses = 0

    for trade in pattern_matches:
        if trade.get("outcome") in ["T1_HIT", "T2_HIT"]:
            wins += 1
        elif trade.get("outcome") == "SL_HIT":
            losses += 1

    total = wins + losses

    if total == 0:
        return 0, "Insufficient completed trades"

    win_rate = wins / total

    if win_rate >= 0.7:
        return 10, f"Strong pattern success ({wins}/{total})"
    elif win_rate >= 0.5:
        return 5, f"Moderate pattern success ({wins}/{total})"
    elif win_rate < 0.4:
        return -10, f"Weak pattern performance ({wins}/{total})"
    else:
        return 0, f"Neutral pattern ({wins}/{total})"