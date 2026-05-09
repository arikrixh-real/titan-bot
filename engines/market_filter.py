try:
    from engines.data_advantage_engine import market_status_from_context
except Exception:
    market_status_from_context = None


def market_regime_status():
    """
    Phase 4 market filter.

    Uses cached/local market breadth context when available and always
    fails open. This layer adds market metadata only; it never blocks scans.
    """
    if market_status_from_context is None:
        return {
            "market_ok": True,
            "reason": "Phase 4 data advantage unavailable; fail-open",
            "direction": "NEUTRAL",
            "regime": "UNKNOWN",
            "status": "UNKNOWN",
            "volatility": "UNKNOWN",
        }

    return market_status_from_context()
