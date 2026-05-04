def market_regime_status():
    """
    Level 1 placeholder market filter.
    Later this will use NIFTY + sector breadth.
    For now, it allows scanning.
    """
    return {
        "market_ok": True,
        "reason": "Level 1 market filter active"
    }