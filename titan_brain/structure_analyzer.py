def analyze_market_structure(stock_data):
    adjustment = 0
    warnings = []
    confirmations = []

    reason_text = str(stock_data.get("reason", "")).lower()
    side = str(stock_data.get("side", "")).upper()
    rr = float(stock_data.get("rr", 0))

    # 1. Breakout structure confirmation
    if "breakout" in reason_text and "relative strength" in reason_text:
        adjustment += 15
        confirmations.append("Breakout supported by relative strength")

    # 2. Compression breakout structure
    if "compression" in reason_text and "breakout" in reason_text:
        adjustment += 10
        confirmations.append("Compression-to-breakout structure detected")

    # 3. Liquidity trap warning
    if "breakout" in reason_text and (
        "rejection" in reason_text or "fakeout" in reason_text or "trap" in reason_text
    ):
        adjustment -= 30
        warnings.append("Breakout rejection detected → possible liquidity trap")

    # 4. Weak structure warning
    if "weak" in reason_text or "no follow-through" in reason_text:
        adjustment -= 20
        warnings.append("Weak follow-through structure detected")

    # 5. Poor RR means bad structure placement
    if rr < 1.5:
        adjustment -= 10
        warnings.append("Poor structure placement: RR below 1.5")

    # 6. Direction label
    if side == "LONG":
        structure_bias = "BULLISH_STRUCTURE"
    elif side == "SHORT":
        structure_bias = "BEARISH_STRUCTURE"
    else:
        structure_bias = "NEUTRAL_STRUCTURE"

    adjustment = max(-40, min(adjustment, 40))

    return {
        "adjustment": adjustment,
        "bias": structure_bias,
        "warnings": warnings,
        "confirmations": confirmations
    }