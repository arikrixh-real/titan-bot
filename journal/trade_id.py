"""
Shared trade identity helpers.

Canonical trade_id format:
scan_id|symbol|side|entry|sl|target

Stable setup_signature format:
symbol|side|entry|sl|target
"""

FALLBACK_SCAN_ID = "NO_SCAN"


def _log(message, logger=None):
    try:
        if callable(logger):
            logger(message)
        else:
            print(message)
    except Exception:
        pass


def _normalize_text(value):
    return str(value or "").strip()


def _normalize_symbol(value):
    symbol = _normalize_text(value).upper()
    if symbol.endswith(".NS"):
        symbol = symbol[:-3]
    return symbol


def _normalize_side(value):
    return _normalize_text(value).upper()


def _normalize_price(value):
    try:
        if value is None or value == "":
            return ""
        return str(round(float(value), 4))
    except Exception:
        return _normalize_text(value)


def build_canonical_trade_id(
    scan_id,
    symbol,
    side,
    entry,
    sl,
    target,
    *,
    logger=None,
    source="TradeID",
):
    safe_scan_id = _normalize_text(scan_id)
    if not safe_scan_id:
        safe_scan_id = FALLBACK_SCAN_ID
        _log(f"[{source}] Missing scan_id; using fallback {FALLBACK_SCAN_ID} for trade_id.", logger)

    safe_symbol = _normalize_symbol(symbol)
    safe_side = _normalize_side(side)
    safe_entry = _normalize_price(entry)
    safe_sl = _normalize_price(sl)
    safe_target = _normalize_price(target)

    missing = []
    if not safe_symbol:
        missing.append("symbol")
    if not safe_side:
        missing.append("side")
    if not safe_entry:
        missing.append("entry")
    if not safe_sl:
        missing.append("sl")
    if not safe_target:
        missing.append("target")

    if missing:
        _log(
            f"[{source}] Invalid canonical trade_id inputs; missing {', '.join(missing)}.",
            logger,
        )
        return ""

    return "|".join([safe_scan_id, safe_symbol, safe_side, safe_entry, safe_sl, safe_target])


def build_setup_signature(symbol, side, entry, sl, target):
    safe_symbol = _normalize_symbol(symbol)
    safe_side = _normalize_side(side)
    safe_entry = _normalize_price(entry)
    safe_sl = _normalize_price(sl)
    safe_target = _normalize_price(target)

    if not all([safe_symbol, safe_side, safe_entry, safe_sl, safe_target]):
        return ""

    return "|".join([safe_symbol, safe_side, safe_entry, safe_sl, safe_target])
