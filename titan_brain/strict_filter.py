def apply_strict_filters(brain_result):
    block_reasons = []

    behavior = brain_result.get("behavior", {})
    structure = brain_result.get("structure", {})
    real_structure = brain_result.get("real_structure", {})
    multi_timeframe = brain_result.get("multi_timeframe", {})
    entry_timing = brain_result.get("entry_timing", {})

    # Only block late entry if structure is not extremely strong
    if entry_timing.get("adjustment", 0) <= -15:
        if real_structure.get("adjustment", 0) < 20:
            block_reasons.append("Late entry risk detected")

    if real_structure.get("adjustment", 0) <= -30:
        block_reasons.append("Fake breakout / liquidity sweep risk")

    if structure.get("adjustment", 0) <= -30:
        block_reasons.append("Structure trap/rejection risk")

    if behavior.get("adjustment", 0) <= -15:
        block_reasons.append("Weak behavior signal")

    if multi_timeframe.get("adjustment", 0) < 0:
        block_reasons.append("Higher timeframe conflict")

    passed = len(block_reasons) == 0

    return {
        "passed": passed,
        "block_reasons": block_reasons
    }