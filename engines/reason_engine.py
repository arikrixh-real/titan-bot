def build_reason(
    symbol=None,
    side=None,
    trend=None,
    score=None,
    rr=None,
    market_status=None,
    momentum_ok=None,
    trap_ok=None,
    relative_strength_ok=None,
    entry_ok=None,
    structure_ok=None,
    **kwargs
):
    """
    TITAN reason builder.

    Compatible with setup_engine.py keyword calls.
    Extra arguments are accepted safely through **kwargs.
    """

    try:
        reasons = []

        if symbol:
            reasons.append(f"{symbol} passed TITAN setup scan")

        if side:
            reasons.append(f"Side: {side}")

        if trend:
            reasons.append(f"Trend: {trend}")

        if score is not None:
            reasons.append(f"Final Score: {score}")

        if rr is not None:
            reasons.append(f"RR: {rr}")

        if market_status:
            reasons.append(f"Market Status: {market_status}")

        if momentum_ok is True:
            reasons.append("Momentum confirmation passed")
        elif momentum_ok is False:
            reasons.append("Momentum confirmation weak")

        if trap_ok is True:
            reasons.append("Fake breakout trap filter passed")
        elif trap_ok is False:
            reasons.append("Trap risk detected or weak")

        if relative_strength_ok is True:
            reasons.append("Relative strength confirmation passed")
        elif relative_strength_ok is False:
            reasons.append("Relative strength weak")

        if entry_ok is True:
            reasons.append("Entry breakout condition passed")
        elif entry_ok is False:
            reasons.append("Entry condition not strong")

        if structure_ok is True:
            reasons.append("Market structure confirmation passed")
        elif structure_ok is False:
            reasons.append("Structure confirmation weak")

        if not reasons:
            return "TITAN setup passed based on available confluences."

        return " | ".join(reasons)

    except Exception as e:
        return f"TITAN reason generation fallback. Error: {e}"