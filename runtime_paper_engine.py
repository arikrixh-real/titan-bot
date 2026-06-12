import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from utils.market_hours import as_ist_datetime, is_trade_window
from runtime_execution_mode import active_execution_mode
from runtime_mode_switch import read_mode_switch_status, signal_allowed, switch_in_progress
from runtime_signal_manager import approved_signals_for_mode


IST = timezone(timedelta(hours=5, minutes=30))
MASTER_BRAIN_STATUS_PATH = Path("data") / "runtime" / "master_brain_status.json"
HFT_SCANNER_STATUS_PATH = Path("data") / "runtime" / "hft_mode_scanner_status.json"
LIVE_PRICE_CACHE_PATH = Path("data") / "live_price_cache.json"
PAPER_ENGINE_STATUS_PATH = Path("data") / "runtime" / "paper_engine_status.json"
PAPER_TRADE_REGISTRY_PATH = Path("data") / "runtime" / "paper_trade_registry.json"
PAPER_ACCOUNT_PATH = Path("data") / "paper_trading" / "paper_account.json"
MAX_NEW_POSITIONS_PER_RUN = 5
MAX_OPEN_POSITIONS = 5
MAX_PRICE_AGE_SECONDS = 120
PAPER_STARTING_CAPITAL = 1000.0
PRICE_TIMESTAMP_FIELDS = (
    "timestamp",
    "timestamp_ist",
    "updated_at",
    "updated_at_ist",
    "fetched_at",
    "fetched_at_ist",
    "last_updated",
    "last_updated_ist",
    "as_of",
    "time",
)
PRICE_VALUE_FIELDS = ("price", "ltp", "last_price", "close")
DEFAULT_PAPER_ACCOUNT = {
    "starting_balance": PAPER_STARTING_CAPITAL,
    "current_balance": PAPER_STARTING_CAPITAL,
    "equity": PAPER_STARTING_CAPITAL,
    "realized_pnl": 0.0,
    "unrealized_pnl": 0.0,
}


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
            str(setup.get("mode") or ""),
        ]
    )


def _default_registry():
    return {
        "open_positions": [],
        "closed_positions": [],
        "seen_keys": [],
        "paper_account": dict(DEFAULT_PAPER_ACCOUNT),
    }


def _normalize_account(account):
    normalized = dict(DEFAULT_PAPER_ACCOUNT)
    if isinstance(account, dict):
        starting_balance = _safe_float(account.get("starting_balance"))
        if starting_balance is not None and round(starting_balance, 4) != PAPER_STARTING_CAPITAL:
            return normalized
        for key in DEFAULT_PAPER_ACCOUNT:
            value = _safe_float(account.get(key))
            if value is not None:
                normalized[key] = value

    normalized["equity"] = round(normalized["current_balance"] + normalized["unrealized_pnl"], 4)
    return normalized


def _load_registry():
    if not PAPER_TRADE_REGISTRY_PATH.exists():
        return _default_registry()

    registry = _read_json(PAPER_TRADE_REGISTRY_PATH)
    if not isinstance(registry, dict):
        return _default_registry()
    raw_account = registry.get("paper_account") if isinstance(registry.get("paper_account"), dict) else {}
    raw_starting_balance = _safe_float(raw_account.get("starting_balance"))
    if raw_starting_balance is not None and round(raw_starting_balance, 4) != PAPER_STARTING_CAPITAL:
        return _default_registry()

    return {
        "open_positions": registry.get("open_positions") if isinstance(registry.get("open_positions"), list) else [],
        "closed_positions": registry.get("closed_positions") if isinstance(registry.get("closed_positions"), list) else [],
        "seen_keys": registry.get("seen_keys") if isinstance(registry.get("seen_keys"), list) else [],
        "paper_account": _normalize_account(registry.get("paper_account")),
    }


def _load_price_cache():
    if not LIVE_PRICE_CACHE_PATH.exists():
        return {}

    cache = _read_json(LIVE_PRICE_CACHE_PATH)
    return cache if isinstance(cache, dict) else {}


def _parse_cache_timestamp(value):
    if value is None:
        return None

    if isinstance(value, (int, float)) and math.isfinite(value):
        timestamp = value / 1000 if value > 9999999999 else value
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None

    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed


def _timestamp_from_mapping(mapping):
    if not isinstance(mapping, dict):
        return None, False

    for field in PRICE_TIMESTAMP_FIELDS:
        if field in mapping:
            return _parse_cache_timestamp(mapping.get(field)), True
    return None, False


def _is_fresh_timestamp(timestamp, now):
    if timestamp is None:
        return False

    age_seconds = (now - timestamp.astimezone(now.tzinfo)).total_seconds()
    return age_seconds <= MAX_PRICE_AGE_SECONDS


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
    journal_writes=False,
    stale_or_missing_prices=0,
    paper_account_summary=None,
    error_type=None,
    error_message=None,
):
    setup_symbols = setup_symbols or []
    paper_performance_summary = paper_performance_summary or _paper_performance_summary(_default_registry())
    paper_account_summary = paper_account_summary or _paper_account_summary(_default_registry())
    current_balance = paper_account_summary.get("current_balance")
    open_pnl = paper_account_summary.get("unrealized_pnl")
    daily_pnl = paper_performance_summary.get("total_realized_pnl", paper_account_summary.get("realized_pnl"))
    equity = paper_account_summary.get("equity")
    mode = active_execution_mode()
    return {
        "timestamp_ist": _timestamp_ist(),
        "mode": mode,
        "active_execution_mode": mode,
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
        "stale_or_missing_prices": int(stale_or_missing_prices or 0),
        "price_freshness_guard": True,
        "max_price_age_seconds": MAX_PRICE_AGE_SECONDS,
        "paper_performance_summary": paper_performance_summary,
        "paper_account_summary": paper_account_summary,
        "account_status": "ACTIVE",
        "current_balance": current_balance,
        "current_pnl": open_pnl,
        "open_pnl": open_pnl,
        "daily_pnl": daily_pnl,
        "equity": equity,
        "setup_symbols": setup_symbols,
        "reason": reason,
        "error_type": error_type,
        "error_message": error_message,
        "trade_creation": False,
        "broker_orders": False,
        "live_order_placement": False,
        "live_execution_enabled": False,
        "telegram_alerts": False,
        "supabase_writes": False,
        "journal_writes": bool(journal_writes),
    }


def _write_status(payload, path=PAPER_ENGINE_STATUS_PATH):
    _write_json(path, payload)


def _write_paper_account_snapshot(registry, status):
    account = _paper_account_summary(registry)
    performance = _paper_performance_summary(registry)
    payload = {
        "timestamp_ist": _timestamp_ist(),
        "status": "ACTIVE",
        "engine_status": status,
        "current_balance": account.get("current_balance"),
        "current_pnl": account.get("unrealized_pnl"),
        "open_pnl": account.get("unrealized_pnl"),
        "unrealized_pnl": account.get("unrealized_pnl"),
        "daily_pnl": performance.get("total_realized_pnl"),
        "realized_pnl": account.get("realized_pnl"),
        "equity": account.get("equity"),
        "open_positions_count": performance.get("open_positions_count"),
        "closed_positions_count": performance.get("closed_positions_count"),
        "source": "runtime_paper_engine",
    }
    _write_json(PAPER_ACCOUNT_PATH, payload)
    return payload


def _write_runtime_status(payload, registry):
    _write_paper_account_snapshot(registry, payload.get("status") or "PAPER_ENGINE_UPDATED")
    _write_status(payload)


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
            normalized.update(
                {
                    "symbol": symbol,
                    "side": side,
                    "entry": entry,
                    "sl": sl,
                    "target": target,
                    "mode": "CLASSIC",
                    "source": setup.get("source") or "classic_master_brain_status",
                }
            )
            valid_setups.append(normalized)
    return valid_setups


def _valid_hft_setups(hft_scanner_status):
    if not isinstance(hft_scanner_status, dict):
        return []
    if str(hft_scanner_status.get("mode") or "").upper() != "HFT":
        return []
    if str(hft_scanner_status.get("status") or "").upper() not in {"ACTIVE", "LIVE"}:
        return []
    candidates = hft_scanner_status.get("paper_trade_candidates")
    if not isinstance(candidates, list):
        return []

    valid_setups = []
    for setup in candidates:
        if not isinstance(setup, dict):
            continue
        symbol = _normalize_symbol(setup.get("symbol"))
        side = _normalize_side(setup.get("side") or "LONG")
        entry = _safe_float(setup.get("entry") or setup.get("entry_price"))
        sl = _safe_float(setup.get("sl") or setup.get("stop_loss") or setup.get("stop_loss_price"))
        target = _safe_float(setup.get("target") or setup.get("tp") or setup.get("take_profit_price"))
        if symbol and side and entry is not None and sl is not None and target is not None:
            normalized = dict(setup)
            normalized.update(
                {
                    "symbol": symbol,
                    "side": side,
                    "entry": entry,
                    "sl": sl,
                    "target": target,
                    "mode": "HFT",
                    "source": setup.get("source") or "hft_mode_scanner_status",
                }
            )
            valid_setups.append(normalized)
    return valid_setups


def _valid_approved_signal_setups(signals, mode):
    if not isinstance(signals, list):
        return []
    mode = str(mode or "").upper()
    valid_setups = []
    for setup in signals:
        if not isinstance(setup, dict):
            continue
        if str(setup.get("status") or "").upper() != "APPROVED":
            continue
        if str(setup.get("mode") or "").upper() != mode:
            continue
        symbol = _normalize_symbol(setup.get("symbol"))
        side = _normalize_side(setup.get("side") or "LONG")
        entry = _safe_float(setup.get("entry") or setup.get("entry_price"))
        sl = _safe_float(setup.get("sl") or setup.get("stop_loss") or setup.get("stop_loss_price"))
        target = _safe_float(setup.get("target") or setup.get("tp") or setup.get("take_profit_price"))
        if mode == "HFT":
            bid = _safe_float(setup.get("bid"))
            ask = _safe_float(setup.get("ask"))
            spread = _safe_float(setup.get("spread"))
            spread_pct = _safe_float(setup.get("spread_pct"))
            if bid is None or ask is None or bid <= 0 or ask <= 0 or bid > ask:
                continue
            if spread is None or spread <= 0:
                continue
            if spread_pct is None or spread_pct > 0.75:
                continue
        if symbol and side and entry is not None and sl is not None and target is not None:
            normalized = dict(setup)
            normalized.update(
                {
                    "symbol": symbol,
                    "side": side,
                    "entry": entry,
                    "sl": sl,
                    "target": target,
                    "mode": mode,
                    "source": setup.get("source") or "runtime_signal_manager",
                    "paper_only": True,
                    "broker_orders": False,
                    "live_order_placement": False,
                }
            )
            valid_setups.append(normalized)
    return valid_setups


def _cached_price(price_cache, symbol, now):
    if not isinstance(price_cache, dict):
        return None, False

    normalized_symbol = _normalize_symbol(symbol)
    cache_timestamp, cache_has_timestamp = _timestamp_from_mapping(price_cache)
    for key, value in price_cache.items():
        if _normalize_symbol(key) == normalized_symbol:
            if isinstance(value, dict):
                price = None
                for field in PRICE_VALUE_FIELDS:
                    if field in value:
                        price = _safe_float(value.get(field))
                        break

                timestamp, has_timestamp = _timestamp_from_mapping(value)
                if not has_timestamp and cache_has_timestamp:
                    timestamp = cache_timestamp
                    has_timestamp = True

                if price is None:
                    return None, False
                if has_timestamp and not _is_fresh_timestamp(timestamp, now):
                    return None, True
                return price, False

            price = _safe_float(value)
            if price is None:
                return None, False
            if cache_has_timestamp and not _is_fresh_timestamp(cache_timestamp, now):
                return None, True
            return price, False
    return None, False


def _realized_pnl(position, exit_price):
    entry = _safe_float(position.get("entry"))
    if entry is None or exit_price is None:
        return 0.0
    quantity = _safe_float(position.get("quantity"))
    if quantity is None:
        quantity = 1.0
    if position.get("side") == "SHORT":
        return round((entry - exit_price) * quantity, 4)
    return round((exit_price - entry) * quantity, 4)


def _paper_account_summary(registry):
    account = _normalize_account(registry.get("paper_account") if isinstance(registry, dict) else None)
    if isinstance(registry, dict):
        account["unrealized_pnl"] = round(_open_unrealized_pnl(registry), 4)
    account["equity"] = round(account["current_balance"] + account["unrealized_pnl"], 4)
    return account


def _open_unrealized_pnl(registry):
    open_positions = registry.get("open_positions", []) if isinstance(registry, dict) else []
    open_positions = open_positions if isinstance(open_positions, list) else []

    total_unrealized_pnl = 0.0
    for position in open_positions:
        if not isinstance(position, dict):
            continue

        entry = _safe_float(position.get("entry"))
        last_price = _safe_float(position.get("last_price"))
        if entry is None or last_price is None:
            continue

        total_unrealized_pnl += _realized_pnl(position, last_price)

    return total_unrealized_pnl


def _refresh_paper_account(registry):
    account = _paper_account_summary(registry)
    registry["paper_account"] = account
    return account


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
    account = _normalize_account(registry.get("paper_account"))
    realized_this_run = 0.0
    closed_this_run = 0
    stale_or_missing_prices = 0
    now = datetime.now(timezone.utc)

    for position in registry.get("open_positions", []):
        if not isinstance(position, dict):
            continue

        price, stale = _cached_price(price_cache, position.get("symbol"), now)
        if price is None:
            stale_or_missing_prices += 1
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
            updated["quantity"] = 1
            updated["last_price"] = price
            updated["unrealized_pnl"] = 0.0 if entry is None else _realized_pnl(updated, price)
            open_positions.append(updated)
            continue

        closed = dict(position)
        closed["quantity"] = 1
        realized_pnl = _realized_pnl(closed, exit_price)
        closed.update(
            {
                "status": outcome,
                "closed_at_ist": _timestamp_ist(),
                "exit_price": exit_price,
                "last_price": price,
                "realized_pnl": realized_pnl,
            }
        )
        closed_positions.append(closed)
        realized_this_run += realized_pnl
        closed_this_run += 1

    registry["open_positions"] = open_positions
    registry["closed_positions"] = closed_positions
    account["current_balance"] = round(account["current_balance"] + realized_this_run, 4)
    account["realized_pnl"] = round(account["realized_pnl"] + realized_this_run, 4)
    registry["paper_account"] = account
    _refresh_paper_account(registry)
    return closed_this_run, stale_or_missing_prices


def _open_new_positions(registry, setups):
    seen_keys = {str(key) for key in registry.get("seen_keys", [])}
    for position in registry.get("open_positions", []):
        if isinstance(position, dict) and position.get("key"):
            seen_keys.add(str(position.get("key")))
    for position in registry.get("closed_positions", []):
        if isinstance(position, dict) and position.get("key"):
            seen_keys.add(str(position.get("key")))

    opened = 0
    opened_setups = []
    for setup in setups:
        if opened >= MAX_NEW_POSITIONS_PER_RUN:
            break
        if len(registry.get("open_positions", [])) >= MAX_OPEN_POSITIONS:
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
            "quantity": 1,
            "rr": _safe_float(setup.get("rr")),
            "mode": setup.get("mode") or active_execution_mode(),
            "source": setup.get("source") or "",
            "strategy": setup.get("strategy") or setup.get("strategy_name") or setup.get("source") or "",
            "paper_only": True,
            "live_order": False,
            "status": "OPEN",
            "opened_at_ist": _timestamp_ist(),
            "last_price": None,
            "unrealized_pnl": 0.0,
        }
        registry["open_positions"].append(position)
        opened_setups.append(dict(setup))
        seen_keys.add(key)
        opened += 1

    registry["seen_keys"] = sorted(seen_keys)
    return opened, opened_setups


def _journal_opened_setups(opened_setups, mode):
    if not opened_setups:
        return 0
    try:
        from journal.trade_journal import journal_eligible_setups

        return int(
            journal_eligible_setups(
                opened_setups,
                scan_id=f"runtime_paper_engine_{mode.lower()}_{_timestamp_ist()}",
                market_status={"mode": mode, "paper_only": True, "broker_orders": False},
            )
            or 0
        )
    except Exception:
        return 0


def run_paper_engine():
    master_brain_status = {}
    registry = _default_registry()
    now = as_ist_datetime()
    trade_window_open = is_trade_window(now)
    new_entries_allowed = False
    stale_or_missing_prices = 0

    try:
        registry = _load_registry()
        price_cache = _load_price_cache()
        closed_this_run, stale_or_missing_prices = _update_open_positions(registry, price_cache)
        _write_json(PAPER_TRADE_REGISTRY_PATH, registry)
        mode = active_execution_mode()
        switch_status = read_mode_switch_status()

        approved_signals = approved_signals_for_mode(mode)
        input_candidates = len(approved_signals)
        setup_symbols = [
            _normalize_symbol(setup.get("symbol"))
            for setup in approved_signals
            if isinstance(setup, dict) and setup.get("symbol")
        ]

        if switch_in_progress() or not signal_allowed():
            payload = _base_payload(
                "PAPER_ENGINE_BLOCKED_MODE_SWITCH",
                False,
                input_candidates,
                f"Mode switch lock active: {switch_status.get('state')}",
                setup_symbols,
                new_paper_positions=0,
                open_positions_count=len(registry.get("open_positions", [])),
                closed_positions_count=len(registry.get("closed_positions", [])),
                closed_this_run=closed_this_run,
                stale_or_missing_prices=stale_or_missing_prices,
                paper_performance_summary=_paper_performance_summary(registry),
                paper_account_summary=_paper_account_summary(registry),
                trade_window=trade_window_open,
                new_entries_allowed=False,
                paper_trade_creation=False,
            )
            payload["mode_switch_status"] = switch_status
            _write_runtime_status(payload, registry)
            return payload

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
                stale_or_missing_prices=stale_or_missing_prices,
                paper_performance_summary=_paper_performance_summary(registry),
                paper_account_summary=_paper_account_summary(registry),
                trade_window=trade_window_open,
                new_entries_allowed=new_entries_allowed,
                paper_trade_creation=False,
            )
            _write_runtime_status(payload, registry)
            return payload

        new_entries_allowed = True
        valid_setups = _valid_approved_signal_setups(approved_signals, mode)
        new_positions, opened_setups = _open_new_positions(registry, valid_setups)
        journaled = _journal_opened_setups(opened_setups, mode)
        _refresh_paper_account(registry)
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
            stale_or_missing_prices=stale_or_missing_prices,
            paper_performance_summary=_paper_performance_summary(registry),
            paper_account_summary=_paper_account_summary(registry),
            trade_window=trade_window_open,
            new_entries_allowed=new_entries_allowed,
            journal_writes=journaled > 0,
        )
        _write_runtime_status(payload, registry)
        return payload

    except Exception as exc:
        payload = _base_payload(
            "PAPER_ENGINE_ERROR",
            False,
            master_brain_status.get("input_candidates", 0) if isinstance(master_brain_status, dict) else 0,
            "Paper engine failed safely",
            stale_or_missing_prices=stale_or_missing_prices,
            paper_performance_summary=_paper_performance_summary(registry),
            paper_account_summary=_paper_account_summary(registry),
            trade_window=trade_window_open,
            new_entries_allowed=False,
            paper_trade_creation=False,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        _write_runtime_status(payload, registry)
        return payload


if __name__ == "__main__":
    print(json.dumps(run_paper_engine(), indent=2, sort_keys=True))
