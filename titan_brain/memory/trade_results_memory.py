def save_trade_result(
    symbol,
    side,
    entry,
    sl,
    tp,
    status="LIVE",
    result=None,
    pnl=0,
    exit_price=None,
):
    """
    Deprecated compatibility helper.

    trade_results final outcome ownership belongs to journal.outcome_tracker.
    Memory code may read/cache/summarize results, but must not insert rows.
    """
    print(f"Trade result memory write skipped for {symbol}; OutcomeTracker owns final outcomes.")
    return False
