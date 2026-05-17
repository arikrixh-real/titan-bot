import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from utils.market_hours import as_ist_datetime, is_trade_window


IST = timezone(timedelta(hours=5, minutes=30))
MASTER_BRAIN_STATUS_PATH = Path("data") / "runtime" / "master_brain_status.json"
LIVE_PRICE_CACHE_PATH = Path("data") / "live_price_cache.json"
PAPER_ENGINE_STATUS_PATH = Path("data") / "runtime" / "paper_engine_status.json"
PAPER_TRADE_REGISTRY_PATH = Path("data") / "runtime" / "paper_trade_registry.json"
MAX_NEW_POSITIONS_PER_RUN = 5


def _safe_float(value):
    try:
        result = float(value)
        if not math.isfinite(result):
            return None
        return result
    except (TypeError, ValueError):
        return None


def _timestamp_ist():
    return as_ist_datetime().isoformat()


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _normalize_symbol(symbol):
    return str(symbol or "").strip().upper().replace(".NS", "")


def _normalize_side(side):
    value = str(side or "").strip().upper()
    if value in {"BUY", "BULLISH", "LONG"}:
        return "LONG"
    if value in {"SELL", "BEARISH", "SHORT"}:
        return "SHORT"
    return ""


def _format_price(value):
    number = _safe_float(value)
    if number is None:
        return ""
    return f"{number:.4f}".rstrip("0").rstrip(".")


def _paper_key(setup):
    return "|".join(
        [
            _normalize_symbol(setup.get("symbol")),
            _normalize_side(setup.get("side")),
            _format_price(setup.get("entry")),
            _format_price(setup.get("sl")),
            _format_price(setup.get("target")),
        ]
    )


def _default_registry():
    return {"open_positions": [], "closed_positions": [], "seen_keys": []}


def _load_registry():
    if not PAPER_TRADE_REGISTRY_PATH.exists():
        return _default_registry()

    registry = _read_json(PAPER_TRADE_REGISTRY_PATH)
    if not isinstance(registry, dict):
        return _default_registry()

    return {
        "open_positions": registry.get("open_positions") if isinstance(registry.get("open_positions"), list) else [],
        "closed_positions": registry.get("closed_positions") if isinstance(registry.get("closed_positions"), list) else [],
        "seen_keys": registry.get("seen_keys") if isinstance(registry.get("seen_keys"), list) else [],
    }


def _load_price_cache():
    if not LIVE_PRICE_CACHE_PATH.exists():
        return {}

    cache = _read_json(LIVE_PRICE_CACHE_PATH)
    return cache if isinstance(cache, dict) else {}


def _base_payload(
    status,
    safety_gates_passed,
    input_candidates=0,
    reason="",
    setup_symbols=None,
    new_paper_positions=0,
    open_positions_count=0,
    closed_positions_count=0,
    closed_this_run=0,
    paper_performance_summary=None,
    trade_window=False,
    new_entries_allowed=False,
    paper_trade_creation=True,
    error_type=None,
    error_message=None,
):
    setup_symbols = setup_symbols or []
    paper_performance_summary = paper_performance_summary or _paper_performance_summary(_default_registry())
    return {
        "timestamp_ist": _timestamp_ist(),
        "status": status,
        "safety_gates_passed": bool(safety_gates_passed),
        "trade_window": bool(trade_window),
        "new_entries_allowed": bool(new_entries_allowed),
        "input_candidates": int(input_candidates or 0),
        "paper_trade_creation": bool(paper_trade_creation),
        "new_paper_positions": int(new_paper_positions or 0),
        "open_positions_count": int(open_positions_count or 0),
        "closed_positions_count": int(closed_positions_count or 0),
        "closed_this_run": int(closed_this_run or 0),
        "paper_performance_summary": paper_performance_summary,
        "setup_symbols": setup_symbols,
        "reason": reason,
        "error_type": error_type,
        "error_message": error_message,
        "trade_creation": False,
        "telegram_alerts": False,
        "supabase_writes": False,
        "journal_writes": False,
    }


def _write_status(payload, path=PAPER_ENGINE_STATUS_PATH):
    _write_json(path, payload)


def _gate_failure(master_brain_status):
    gates = [
        (
            master_brain_status.get("observe_only") is True,
            "master_brain_status.observe_only must be true",
        ),
        (
            master_brain_status.get("trade_creation") is False,
            "master_brain_status.trade_creation must be false",
        ),
        (
            master_brain_status.get("telegram_alerts") is False,
            "master_brain_status.telegram_alerts must be false",
        ),
        (
            master_brain_status.get("supabase_writes") is False,
            "master_brain_status.supabase_writes must be false",
        ),
        (
            master_brain_status.get("journal_writes") is False,
            "master_brain_status.journal_writes must be false",
        ),
    ]

    failures = [message for passed, message in gates if not passed]
    return "; ".join(failures)


def _valid_setups(master_brain_status):
    setups = master_brain_status.get("evaluated_trade_setups")
    if not isinstance(setups, list):
        return []

    valid_setups = []
    for setup in setups:
        if not isinstance(setup, dict):
            continue
        symbol = _normalize_symbol(setup.get("symbol"))
        side = _normalize_side(setup.get("side"))
        entry = _safe_float(setup.get("entry"))
        sl = _safe_float(setup.get("sl"))
        target = _safe_float(setup.get("target"))
        if symbol and side and entry is not None and sl is not None and target is not None:
            normalized = dict(setup)
            normalized.update({"symbol": symbol, "side": side, "entry": entry, "sl": sl, "target": target})
            valid_setups.append(normalized)
    return valid_setups


def _cached_price(price_cache, symbol):
    if not isinstance(price_cache, dict):
        return None

    normalized_symbol = _normalize_symbol(symbol)
    for key, value in price_cache.items():
        if _normalize_symbol(key) == normalized_symbol:
            return _safe_float(value)
    return None


def _realized_pnl(position, exit_price):
    entry = _safe_float(position.get("entry"))
    if entry is None or exit_price is None:
        return 0.0
    if position.get("side") == "SHORT":
        return round(entry - exit_price, 4)
    return round(exit_price - entry, 4)


def _paper_performance_summary(registry):
    open_positions = registry.get("open_positions", []) if isinstance(registry, dict) else []
    closed_positions = registry.get("closed_positions", []) if isinstance(registry, dict) else []
    open_positions = open_positions if isinstance(open_positions, list) else []
    closed_positions = closed_positions if isinstance(closed_positions, list) else []

    total_realized_pnl = 0.0
    winning_trades = 0
    losing_trades = 0
    for position in closed_positions:
        if not isinstance(position, dict):
            continue

        realized_pnl = _safe_float(position.get("realized_pnl"))
        if realized_pnl is None:
            realized_pnl = _realized_pnl(position, _safe_float(position.get("exit_price")))

        total_realized_pnl += realized_pnl
        if realized_pnl > 0:
            winning_trades += 1
        elif realized_pnl < 0:
            losing_trades += 1

    total_unrealized_pnl = 0.0
    open_long_count = 0
    open_short_count = 0
    for position in open_positions:
        if not isinstance(position, dict):
            continue

        side = position.get("side")
        if side == "LONG":
            open_long_count += 1
        elif side == "SHORT":
            open_short_count += 1

        entry = _safe_float(position.get("entry"))
        last_price = _safe_float(position.get("last_price"))
        if entry is None or last_price is None:
            continue

        total_unrealized_pnl += _realized_pnl(position, last_price)

    closed_positions_count = len(closed_positions)
    win_rate = 0.0
    if closed_positions_count:
        win_rate = round((winning_trades / closed_positions_count) * 100, 2)

    return {
        "open_positions_count": len(open_positions),
        "closed_positions_count": closed_positions_count,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": win_rate,
        "total_realized_pnl": round(total_realized_pnl, 4),
        "total_unrealized_pnl": round(total_unrealized_pnl, 4),
        "open_long_count": open_long_count,
        "open_short_count": open_short_count,
    }


def _update_open_positions(registry, price_cache):
    open_positions = []
    closed_positions = list(registry.get("closed_positions", []))
    closed_this_run = 0

    for position in registry.get("open_positions", []):
        if not isinstance(position, dict):
            continue

        price = _cached_price(price_cache, position.get("symbol"))
        if price is None:
            open_positions.append(position)
            continue

        side = position.get("side")
        entry = _safe_float(position.get("entry"))
        sl = _safe_float(position.get("sl"))
        target = _safe_float(position.get("target"))
        outcome = None
        exit_price = None

        if side == "LONG":
            if target is not None and price >= target:
                outcome = "TP"
                exit_price = target
            elif sl is not None and price <= sl:
                outcome = "SL"
                exit_price = sl
        elif side == "SHORT":
            if target is not None and price <= target:
                outcome = "TP"
                exit_price = target
            elif sl is not None and price >= sl:
                outcome = "SL"
                exit_price = sl

        if outcome is None:
            updated = dict(position)
            updated["last_price"] = price
            updated["unrealized_pnl"] = 0.0 if entry is None else _realized_pnl(updated, price)
            open_positions.append(updated)
            continue

        closed = dict(position)
        closed.update(
            {
                "status": outcome,
                "closed_at_ist": _timestamp_ist(),
                "exit_price": exit_price,
                "last_price": price,
                "realized_pnl": _realized_pnl(closed, exit_price),
            }
        )
        closed_positions.append(closed)
        closed_this_run += 1

    registry["open_positions"] = open_positions
    registry["closed_positions"] = closed_positions
    return closed_this_run


def _open_new_positions(registry, setups):
    seen_keys = {str(key) for key in registry.get("seen_keys", [])}
    for position in registry.get("open_positions", []):
        if isinstance(position, dict) and position.get("key"):
            seen_keys.add(str(position.get("key")))
    for position in registry.get("closed_positions", []):
        if isinstance(position, dict) and position.get("key"):
            seen_keys.add(str(position.get("key")))

    opened = 0
    for setup in setups:
        if opened >= MAX_NEW_POSITIONS_PER_RUN:
            break

        key = _paper_key(setup)
        if not key or key in seen_keys:
            continue

        position = {
            "key": key,
            "symbol": setup["symbol"],
            "side": setup["side"],
            "entry": setup["entry"],
            "sl": setup["sl"],
            "target": setup["target"],
            "rr": _safe_float(setup.get("rr")),
            "status": "OPEN",
            "opened_at_ist": _timestamp_ist(),
            "last_price": None,
            "unrealized_pnl": 0.0,
        }
        registry["open_positions"].append(position)
        seen_keys.add(key)
        opened += 1

    registry["seen_keys"] = sorted(seen_keys)
    return opened


def run_paper_engine():
    master_brain_status = {}
    registry = _default_registry()
    now = as_ist_datetime()
    trade_window_open = is_trade_window(now)
    new_entries_allowed = False

    try:
        registry = _load_registry()
        price_cache = _load_price_cache()
        closed_this_run = _update_open_positions(registry, price_cache)
        _write_json(PAPER_TRADE_REGISTRY_PATH, registry)

        master_brain_status = _read_json(MASTER_BRAIN_STATUS_PATH)

        input_candidates = master_brain_status.get("input_candidates", 0)
        setup_symbols = [
            _normalize_symbol(setup.get("symbol"))
            for setup in master_brain_status.get("evaluated_trade_setups", [])
            if isinstance(setup, dict) and setup.get("symbol")
        ]

        if not trade_window_open:
            payload = _base_payload(
                "PAPER_ENGINE_MONITOR_ONLY_OUTSIDE_TRADE_WINDOW",
                True,
                input_candidates,
                "Existing paper positions monitored; new paper entries disabled outside TITAN trade window",
                setup_symbols,
                new_paper_positions=0,
                open_positions_count=len(registry.get("open_positions", [])),
                closed_positions_count=len(registry.get("closed_positions", [])),
                closed_this_run=closed_this_run,
                paper_performance_summary=_paper_performance_summary(registry),
                trade_window=trade_window_open,
                new_entries_allowed=new_entries_allowed,
                paper_trade_creation=False,
            )
            _write_status(payload)
            return payload

        failure_reason = _gate_failure(master_brain_status)
        if failure_reason:
            payload = _base_payload(
                "PAPER_ENGINE_BLOCKED_SAFETY_GATE",
                False,
                input_candidates,
                failure_reason,
                setup_symbols,
                open_positions_count=len(registry.get("open_positions", [])),
                closed_positions_count=len(registry.get("closed_positions", [])),
                closed_this_run=closed_this_run,
                paper_performance_summary=_paper_performance_summary(registry),
                trade_window=trade_window_open,
                new_entries_allowed=new_entries_allowed,
            )
            _write_status(payload)
            return payload

        new_entries_allowed = True
        valid_setups = _valid_setups(master_brain_status)
        new_positions = _open_new_positions(registry, valid_setups)
        _write_json(PAPER_TRADE_REGISTRY_PATH, registry)

        payload = _base_payload(
            "PAPER_ENGINE_RUN_COMPLETE",
            True,
            input_candidates,
            "Local paper simulation updated from evaluated trade setups",
            setup_symbols,
            new_paper_positions=new_positions,
            open_positions_count=len(registry.get("open_positions", [])),
            closed_positions_count=len(registry.get("closed_positions", [])),
            closed_this_run=closed_this_run,
            paper_performance_summary=_paper_performance_summary(registry),
            trade_window=trade_window_open,
            new_entries_allowed=new_entries_allowed,
        )
        _write_status(payload)
        return payload

    except Exception as exc:
        payload = _base_payload(
            "PAPER_ENGINE_ERROR",
            False,
            master_brain_status.get("input_candidates", 0) if isinstance(master_brain_status, dict) else 0,
            "Paper engine failed safely",
            paper_performance_summary=_paper_performance_summary(registry),
            trade_window=trade_window_open,
            new_entries_allowed=False,
            paper_trade_creation=False,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        _write_status(payload)
        return payload


if __name__ == "__main__":
    print(json.dumps(run_paper_engine(), indent=2, sort_keys=True))
