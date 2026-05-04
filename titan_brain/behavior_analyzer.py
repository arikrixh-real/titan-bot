def analyze_market_behavior(stock_data):
    score = 0
    warnings = []
    confidence_boost = []

    reason_text = str(stock_data.get("reason", "")).lower()
    rr = float(stock_data.get("rr", 0))

    # 1. Fake breakout risk
    if "breakout" in reason_text and "volume" not in reason_text:
        score -= 15
        warnings.append("Breakout without strong volume → trap risk")

    # 2. Overextended move (late entry risk)
    if "high score" in reason_text and rr < 1.5:
        score -= 10
        warnings.append("Possible late entry → reduced edge")

    # 3. Weak momentum detection
    if "compression" in reason_text and "breakout" not in reason_text:
        score -= 10
        warnings.append("Compression without breakout → momentum not confirmed")

    # 4. Strong confirmation
    if "volume" in reason_text and "breakout" in reason_text:
        score += 15
        confidence_boost.append("Strong volume-backed breakout")

    # 5. Trend + strength combo (high probability)
    if "trend aligned" in reason_text and "relative strength" in reason_text:
        score += 15
        confidence_boost.append("Trend + relative strength alignment")

    return {
        "adjustment": score,
        "warnings": warnings,
        "confidence": confidence_boost
    }