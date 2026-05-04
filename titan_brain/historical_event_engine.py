def analyze_historical_events(stock_data):
    score = 0
    bias = "NEUTRAL"
    reasons = []

    reason_text = stock_data.get("reason", "").lower()
    source = stock_data.get("source", "").lower()
    side = stock_data.get("side", "").upper()

    # 1. Live setup is stronger than old/static setup
    if source == "live":
        score += 20
        reasons.append("Live market setup detected")

    # 2. News / event related keywords
    event_keywords = [
        "news",
        "result",
        "earnings",
        "quarter",
        "order",
        "deal",
        "merger",
        "acquisition",
        "rbi",
        "policy",
        "rate",
        "inflation",
        "budget",
        "global",
        "crude",
        "dollar",
        "us market",
        "fed"
    ]

    if any(keyword in reason_text for keyword in event_keywords):
        score += 30
        reasons.append("Event/news-related catalyst detected")

    # 3. Breakout after catalyst
    if "breakout" in reason_text:
        score += 20
        reasons.append("Breakout behavior matches event reaction pattern")

    # 4. Volume spike after event
    if "volume" in reason_text or "spike" in reason_text:
        score += 20
        reasons.append("Volume confirms market reaction")

    # 5. Gap risk warning
    if "gap up" in reason_text or "gap-down" in reason_text or "gap down" in reason_text:
        score -= 20
        reasons.append("Gap risk detected")

    # 6. Dangerous event warning
    danger_keywords = [
        "fraud",
        "raid",
        "default",
        "downgrade",
        "loss",
        "penalty",
        "ban",
        "investigation"
    ]

    if any(keyword in reason_text for keyword in danger_keywords):
        score -= 40
        reasons.append("Negative historical/event risk detected")

    if side == "LONG":
        bias = "BULLISH"
    elif side == "SHORT":
        bias = "BEARISH"

    score = max(0, min(score, 100))

    return {
        "score": score,
        "bias": bias,
        "reason": ", ".join(reasons) if reasons else "No major historical/event signal"
    }