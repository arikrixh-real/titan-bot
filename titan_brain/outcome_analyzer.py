def analyze_trade_outcome(trade_record, outcome):
    """
    outcome should be one of:
    T1_HIT, T2_HIT, SL_HIT, EXPIRED, UNKNOWN
    """

    reasons = []
    lessons = []
    mistake_category = "NONE"
    quality_adjustment = 0

    setup_reason = str(trade_record.get("setup_reason", "")).lower()
    conviction = str(trade_record.get("conviction", "")).upper()
    brain_score = float(trade_record.get("brain_score", 0))
    rr = float(trade_record.get("rr", 0))

    if outcome in ["T1_HIT", "T2_HIT"]:
        quality_adjustment += 10
        reasons.append("Trade followed expected direction.")

        if "volume" in setup_reason:
            lessons.append("Volume confirmation supported successful follow-through.")

        if "relative strength" in setup_reason:
            lessons.append("Relative strength improved trade quality.")

        if conviction == "HIGH":
            lessons.append("High brain conviction aligned with winning outcome.")

    elif outcome == "SL_HIT":
        quality_adjustment -= 15
        reasons.append("Trade invalidated and stop-loss was hit.")

        if "breakout" in setup_reason and "volume" in setup_reason:
            mistake_category = "POSSIBLE_FALSE_BREAKOUT"
            lessons.append("Breakout with volume may still fail if follow-through is weak.")

        if "compression" in setup_reason:
            mistake_category = "COMPRESSION_FAILURE"
            lessons.append("Compression breakout failed; future trades need stronger confirmation after breakout.")

        if rr < 1.5:
            mistake_category = "WEAK_RISK_REWARD"
            lessons.append("Weak risk-reward reduces trade quality.")

        if brain_score >= 80:
            lessons.append("High conviction trade failed; future similar setups need stricter confirmation.")

    elif outcome == "EXPIRED":
        quality_adjustment -= 5
        reasons.append("Trade did not trigger or did not reach targets in expected time.")
        mistake_category = "LOW_MOMENTUM"
        lessons.append("Setup may have lacked momentum or timing.")

    else:
        reasons.append("Outcome unknown. No learning adjustment applied.")

    return {
        "outcome": outcome,
        "mistake_category": mistake_category,
        "quality_adjustment": quality_adjustment,
        "outcome_reason": " ".join(reasons),
        "lessons": lessons
    }