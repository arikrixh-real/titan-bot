"""
TITAN Phase 23 - Paper Trading Engine
-------------------------------------

Internal simulated trading environment. This module never places broker orders,
never calls live execution, and never changes Telegram, dashboard, or alert cap
behavior. It stores paper-only account, positions, and audit artifacts locally.
"""

from __future__ import annotations

import json
import math
import csv
import hashlib
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


PAPER_DIR = Path("data/paper_trading")
ACCOUNT_PATH = PAPER_DIR / "paper_account.json"
POSITIONS_PATH = PAPER_DIR / "paper_positions.json"
CLOSED_POSITIONS_PATH = PAPER_DIR / "paper_closed_positions.json"
AUDIT_LOG_PATH = PAPER_DIR / "paper_audit_log.json"
PROCESSED_RESULTS_PATH = PAPER_DIR / "paper_processed_results.json"
LEGACY_CLOSED_POSITIONS_ARCHIVE_PATH = PAPER_DIR / "paper_closed_positions_legacy_archive.json"
TRADE_OUTCOMES_CSV = Path("data/journals/trade_outcomes.csv")
TRADE_OUTCOMES_JSONL = Path("data/journals/trade_outcomes.jsonl")

DEFAULT_INITIAL_BALANCE = 1000.0
DEFAULT_CURRENCY = "INR"
MAX_RISK_PER_TRADE_PCT = 1.0
DAILY_LOSS_LIMIT_PCT = 3.0
MAX_DRAWDOWN_PCT = 10.0


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        result = float(value)
        if not math.isfinite(result):
            return default
        return result
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def safe_text(value: Any, default: str = "") -> str:
    try:
        if value is None:
            return default
        text = str(value).strip()
        return text if text else default
    except Exception:
        return default


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _ensure_storage() -> None:
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    for path, default in (
        (POSITIONS_PATH, []),
        (CLOSED_POSITIONS_PATH, []),
        (AUDIT_LOG_PATH, []),
        (PROCESSED_RESULTS_PATH, []),
    ):
        if not path.exists():
            path.write_text(json.dumps(default, indent=2), encoding="utf-8")


def _read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return deepcopy(default)
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except Exception:
        return deepcopy(default)


def _write_json(path: Path, data: Any) -> bool:
    try:
        _ensure_storage()
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:
        return False


def _normalize_account(account: Any) -> Dict[str, Any]:
    account = account if isinstance(account, dict) else {}
    mode = safe_text(account.get("capital_mode")).upper()
    legacy_default = (
        safe_float(account.get("initial_balance"), DEFAULT_INITIAL_BALANCE) >= 99999.0
        and mode != "ADAPTIVE_1K"
    )
    stored_initial = safe_float(account.get("initial_balance"), DEFAULT_INITIAL_BALANCE)
    stored_balance = safe_float(account.get("current_balance") or account.get("balance"), stored_initial)
    stored_closed_pnl = safe_float(account.get("closed_pnl"), 0.0)
    adaptive_inconsistent = (
        mode == "ADAPTIVE_1K"
        and stored_initial <= 5000.0
        and abs((stored_balance - stored_initial) - stored_closed_pnl) > 0.01
        and abs(stored_closed_pnl) > max(50.0, stored_initial * 0.25)
    )
    initial = DEFAULT_INITIAL_BALANCE if legacy_default else safe_float(account.get("initial_balance"), DEFAULT_INITIAL_BALANCE)
    balance = safe_float(account.get("current_balance") or account.get("balance"), initial)
    if legacy_default or adaptive_inconsistent:
        initial = DEFAULT_INITIAL_BALANCE
        balance = DEFAULT_INITIAL_BALANCE
    open_pnl = 0.0 if adaptive_inconsistent else safe_float(account.get("open_pnl"), 0.0)
    closed_pnl = 0.0 if legacy_default or adaptive_inconsistent else safe_float(account.get("closed_pnl"), 0.0)
    daily_start_balance = safe_float(account.get("daily_start_balance"), balance)
    if legacy_default or adaptive_inconsistent:
        daily_start_balance = DEFAULT_INITIAL_BALANCE
    daily_pnl = 0.0 if adaptive_inconsistent else safe_float(account.get("daily_pnl"), balance - daily_start_balance)
    status = safe_text(account.get("paper_trading_status"), "ACTIVE").upper()
    if status not in {"ACTIVE", "LOCKED"}:
        status = "ACTIVE"
    return {
        "paper_trading_status": status,
        "capital_mode": "ADAPTIVE_1K",
        "initial_balance": initial,
        "currency": safe_text(account.get("currency"), DEFAULT_CURRENCY),
        "current_balance": balance,
        "balance": balance,
        "equity": round(balance + open_pnl, 2),
        "open_pnl": open_pnl,
        "closed_pnl": closed_pnl,
        "daily_pnl": round(daily_pnl, 2),
        "created_at": _now() if adaptive_inconsistent else account.get("created_at") or _now(),
        "updated_at": _now(),
        "risk_rules": {
            "max_risk_per_trade_pct": safe_float(
                _dict(account.get("risk_rules")).get("max_risk_per_trade_pct"),
                MAX_RISK_PER_TRADE_PCT,
            ),
            "daily_loss_limit_pct": DAILY_LOSS_LIMIT_PCT,
            "max_drawdown_pct": safe_float(
                _dict(account.get("risk_rules")).get("max_drawdown_pct"),
                MAX_DRAWDOWN_PCT,
            ),
        },
        "daily_start_balance": daily_start_balance,
        "daily_start_date": account.get("daily_start_date") or _today(),
        "daily_peak_pnl": 0.0 if adaptive_inconsistent else safe_float(account.get("daily_peak_pnl"), max(0.0, daily_pnl)),
        "daily_loss_floor": safe_float(
            account.get("daily_loss_floor"),
            -round(daily_start_balance * DAILY_LOSS_LIMIT_PCT / 100.0, 2),
        ),
        "last_error": account.get("last_error"),
    }


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _is_adaptive_1k_account(account: Dict[str, Any]) -> bool:
    return safe_text(_dict(account).get("capital_mode")).upper() == "ADAPTIVE_1K"


def _position_exposure(position: Dict[str, Any]) -> float:
    entry = safe_float(position.get("entry") or position.get("entry_price"), 0.0)
    qty = safe_float(position.get("quantity") or position.get("qty"), 0.0)
    explicit = safe_float(position.get("position_size") or position.get("capital_used"), 0.0)
    return explicit if explicit > 0 else entry * qty


def _is_legacy_1l_position(account: Dict[str, Any], position: Dict[str, Any]) -> bool:
    if not _is_adaptive_1k_account(account):
        return False
    balance = max(safe_float(account.get("current_balance"), DEFAULT_INITIAL_BALANCE), DEFAULT_INITIAL_BALANCE)
    exposure = _position_exposure(position)
    risk_amount = safe_float(position.get("risk_amount"), 0.0)
    return bool(exposure > balance * 1.5 or risk_amount > balance * 0.10)


def _archive_legacy_closed_positions(legacy_positions: List[Dict[str, Any]]) -> None:
    if not legacy_positions:
        return
    archive = _list(_read_json(LEGACY_CLOSED_POSITIONS_ARCHIVE_PATH, []))
    archived_at = _now()
    for position in legacy_positions:
        row = dict(position)
        row["archived_at"] = archived_at
        row["archive_reason"] = "LEGACY_1L_POSITION_REMOVED_FROM_ADAPTIVE_1K"
        archive.append(row)
    _write_json(LEGACY_CLOSED_POSITIONS_ARCHIVE_PATH, archive[-5000:])


def sanitize_closed_positions_for_account(account: Dict[str, Any], positions: List[Any]) -> List[Dict[str, Any]]:
    valid: List[Dict[str, Any]] = []
    legacy: List[Dict[str, Any]] = []
    for item in _list(positions):
        if not isinstance(item, dict):
            continue
        position = dict(item)
        if _is_legacy_1l_position(account, position):
            legacy.append(position)
            continue
        valid.append(position)
    _archive_legacy_closed_positions(legacy)
    if legacy:
        _write_json(CLOSED_POSITIONS_PATH, valid)
    return valid


def migrate_open_positions_quantity(account: Dict[str, Any], positions: List[Any]) -> List[Dict[str, Any]]:
    migrated: List[Dict[str, Any]] = []
    changed = False
    for item in _list(positions):
        if not isinstance(item, dict):
            continue
        position = dict(item)
        entry = safe_float(position.get("entry_price") or position.get("entry"), 0.0)
        qty = safe_int(position.get("quantity") or position.get("qty"), 0)
        if qty <= 0:
            sizing = calculate_paper_trade_sizing(account, position)
            qty = safe_int(sizing.get("quantity"), 0)
            if qty > 0:
                position["quantity"] = qty
                position["qty"] = qty
                position["position_size"] = sizing.get("position_size")
                position["risk_amount"] = sizing.get("risk_amount")
                position["risk_per_trade_pct"] = sizing.get("risk_per_trade_pct")
                changed = True
        if entry > 0 and safe_float(position.get("position_size"), 0.0) <= 0 and qty > 0:
            position["position_size"] = round(entry * qty, 2)
            changed = True
        position.setdefault("entry_price", entry)
        position.setdefault("stop_loss", position.get("sl"))
        position.setdefault("tp", position.get("target"))
        position.setdefault("is_paper_trade", True)
        migrated.append(position)
    if changed:
        _write_json(POSITIONS_PATH, migrated)
    return migrated


def load_paper_account() -> Dict[str, Any]:
    _ensure_storage()
    if not ACCOUNT_PATH.exists():
        return initialize_paper_account(DEFAULT_INITIAL_BALANCE)
    account = _normalize_account(_read_json(ACCOUNT_PATH, {}))
    positions = migrate_open_positions_quantity(account, _read_json(POSITIONS_PATH, []))
    closed = sanitize_closed_positions_for_account(account, _read_json(CLOSED_POSITIONS_PATH, []))
    account["open_positions"] = [item for item in _list(positions) if isinstance(item, dict)]
    account["closed_positions"] = [item for item in _list(closed) if isinstance(item, dict)]
    if account.get("daily_start_date") != _today():
        account["daily_start_date"] = _today()
        account["daily_start_balance"] = account.get("current_balance", DEFAULT_INITIAL_BALANCE)
        account["daily_peak_pnl"] = 0.0
        account["daily_loss_floor"] = -round(safe_float(account.get("daily_start_balance"), DEFAULT_INITIAL_BALANCE) * DAILY_LOSS_LIMIT_PCT / 100.0, 2)
    account["open_pnl"] = calculate_open_pnl(account)
    account["closed_pnl"] = calculate_closed_pnl(account)
    account["balance"] = safe_float(account.get("current_balance"), DEFAULT_INITIAL_BALANCE)
    if _is_adaptive_1k_account(account) and not account["closed_positions"] and abs(account["closed_pnl"]) > 0:
        account["closed_pnl"] = 0.0
        account["current_balance"] = DEFAULT_INITIAL_BALANCE
        account["balance"] = DEFAULT_INITIAL_BALANCE
        account["daily_start_balance"] = DEFAULT_INITIAL_BALANCE
    account["equity"] = round(account["balance"] + account["open_pnl"], 2)
    today_pnl = round(sum(
        safe_float(position.get("closed_pnl"), 0.0)
        for position in account["closed_positions"]
        if safe_text(position.get("closed_at"))[:10] == _today()
    ), 2)
    if today_pnl:
        account["daily_pnl"] = today_pnl
        account["daily_start_balance"] = round(account["balance"] - today_pnl, 2)
    else:
        account["daily_pnl"] = round(account["balance"] - safe_float(account.get("daily_start_balance"), account["balance"]), 2)
    account = update_daily_trailing_protection(account)
    save_paper_account(account)
    return account


def save_paper_account(account: Dict[str, Any]) -> bool:
    source = account if isinstance(account, dict) else {}
    open_positions = source.get("open_positions")
    closed_positions = source.get("closed_positions")
    clean_account = _normalize_account(source)
    clean_account.pop("open_positions", None)
    clean_account.pop("closed_positions", None)
    ok = _write_json(ACCOUNT_PATH, clean_account)
    if open_positions is not None:
        ok = _write_json(POSITIONS_PATH, _list(open_positions)) and ok
    if closed_positions is not None:
        ok = _write_json(CLOSED_POSITIONS_PATH, _list(closed_positions)) and ok
    return ok


def initialize_paper_account(initial_balance: float = DEFAULT_INITIAL_BALANCE) -> Dict[str, Any]:
    _ensure_storage()
    account = {
        "paper_trading_status": "ACTIVE",
        "capital_mode": "ADAPTIVE_1K",
        "initial_balance": safe_float(initial_balance, DEFAULT_INITIAL_BALANCE),
        "currency": DEFAULT_CURRENCY,
        "current_balance": safe_float(initial_balance, DEFAULT_INITIAL_BALANCE),
        "created_at": _now(),
        "updated_at": _now(),
        "risk_rules": {
            "max_risk_per_trade_pct": MAX_RISK_PER_TRADE_PCT,
            "daily_loss_limit_pct": DAILY_LOSS_LIMIT_PCT,
            "max_drawdown_pct": MAX_DRAWDOWN_PCT,
        },
        "daily_start_balance": safe_float(initial_balance, DEFAULT_INITIAL_BALANCE),
        "daily_start_date": _today(),
        "daily_peak_pnl": 0.0,
        "daily_loss_floor": -round(safe_float(initial_balance, DEFAULT_INITIAL_BALANCE) * DAILY_LOSS_LIMIT_PCT / 100.0, 2),
        "open_positions": [],
        "closed_positions": [],
    }
    save_paper_account(account)
    generate_paper_audit_log({"event": "ACCOUNT_INITIALIZED", "initial_balance": account["initial_balance"]})
    return account


def _trade_symbol(trade: Dict[str, Any]) -> str:
    return safe_text(trade.get("symbol") or trade.get("stock") or trade.get("ticker"), "UNKNOWN").replace(".NS", "").upper()


def _trade_side(trade: Dict[str, Any]) -> str:
    side = safe_text(trade.get("side") or trade.get("direction"), "LONG").upper()
    if side in {"BUY", "BULLISH"}:
        return "LONG"
    if side in {"SELL", "BEARISH"}:
        return "SHORT"
    return side if side in {"LONG", "SHORT"} else "LONG"


def calculate_position_size(account: Dict[str, Any], trade: Dict[str, Any]) -> int:
    return int(calculate_paper_trade_sizing(account, trade).get("quantity", 0))


def calculate_paper_trade_sizing(account: Dict[str, Any], trade: Dict[str, Any]) -> Dict[str, Any]:
    account = _normalize_account(account)
    trade = _dict(trade)
    balance = safe_float(account.get("current_balance"), DEFAULT_INITIAL_BALANCE)
    micro_capital_mode = safe_text(account.get("capital_mode")).upper() == "ADAPTIVE_1K"
    rules = _dict(account.get("risk_rules"))
    risk_pct = safe_float(rules.get("max_risk_per_trade_pct"), MAX_RISK_PER_TRADE_PCT)
    if risk_pct <= 0 or risk_pct > 10:
        risk_pct = MAX_RISK_PER_TRADE_PCT
    risk_amount = balance * risk_pct / 100.0
    entry = safe_float(trade.get("entry") or trade.get("entry_price") or trade.get("price"), 0.0)
    stop = safe_float(trade.get("sl") or trade.get("stop_loss") or trade.get("stoploss"), 0.0)
    per_share_risk = abs(entry - stop)
    quantity = 0
    computed_qty = 0
    skip_reason = ""
    position_size = 0.0
    required_capital = 0.0
    if entry <= 0 or stop <= 0:
        skip_reason = "INVALID_ENTRY_OR_SL"
    elif micro_capital_mode and entry > balance:
        if per_share_risk > 0 and risk_amount > 0:
            computed_qty = int(math.floor(risk_amount / per_share_risk))
        required_capital = entry
        skip_reason = "MICRO_CAPITAL_PRICE_SKIP"
    elif risk_amount <= 0 or risk_amount > balance:
        skip_reason = "UNREALISTIC_RISK"
    elif per_share_risk > 0:
        risk_limited_qty = int(math.floor(risk_amount / per_share_risk))
        cash_limited_qty = int(math.floor(balance / entry))
        computed_qty = risk_limited_qty
        quantity = min(risk_limited_qty, cash_limited_qty) if micro_capital_mode else risk_limited_qty
        position_size = quantity * entry
        required_capital = position_size if quantity > 0 else entry
        if quantity <= 0:
            position_size = 0.0
            if micro_capital_mode and risk_limited_qty <= 0:
                skip_reason = "MICRO_CAPITAL_SL_TOO_WIDE"
            elif micro_capital_mode and cash_limited_qty <= 0:
                skip_reason = "MICRO_CAPITAL_PRICE_SKIP"
            else:
                skip_reason = "QTY_LESS_THAN_1"
        elif position_size > balance:
            required_capital = position_size
            quantity = 0
            position_size = 0.0
            skip_reason = "MICRO_CAPITAL_PRICE_SKIP" if micro_capital_mode else "INSUFFICIENT_CAPITAL"
    else:
        skip_reason = "MICRO_CAPITAL_QTY_INVALID" if micro_capital_mode else "INVALID_SL_DISTANCE"
    return {
        "quantity": int(quantity),
        "qty": int(quantity),
        "computed_qty": int(computed_qty),
        "position_size": round(position_size, 2),
        "capital_used": round(position_size, 2),
        "required_capital": round(required_capital, 2),
        "risk_amount": round(risk_amount, 2),
        "risk_per_trade_pct": risk_pct,
        "risk_per_share": round(per_share_risk, 4),
        "account_balance": round(balance, 2),
        "skip_reason": skip_reason,
        "rejection_reason": skip_reason,
        "sizing_valid": bool(quantity >= 1 and position_size > 0 and not skip_reason),
    }


def prepare_paper_trade_fields(trade: Dict[str, Any], account: Dict[str, Any] | None = None) -> Dict[str, Any]:
    account = load_paper_account() if account is None else account
    trade = dict(_dict(trade))
    sizing = calculate_paper_trade_sizing(account, trade)
    entry = safe_float(trade.get("entry") or trade.get("entry_price") or trade.get("price"), 0.0)
    stop = safe_float(trade.get("sl") or trade.get("stop_loss") or trade.get("stoploss"), 0.0)
    target = safe_float(trade.get("target") or trade.get("tp") or trade.get("target_price") or trade.get("t1"), 0.0)
    paper_trade_id = safe_text(trade.get("paper_trade_id") or trade.get("trade_id") or trade.get("id"))
    if not paper_trade_id:
        paper_trade_id = f"PT-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    mode = safe_text(trade.get("mode") or trade.get("execution_mode") or trade.get("trading_mode") or trade.get("active_mode")).upper()
    if mode not in {"CLASSIC", "HFT"}:
        mode = ""
    trade.update({
        "entry_price": entry,
        "entry": entry,
        "stop_loss": stop,
        "sl": stop,
        "target": target,
        "tp": target,
        "side": _trade_side(trade),
        "symbol": _trade_symbol(trade),
        "quantity": sizing["quantity"],
        "qty": sizing["qty"],
        "position_size": sizing["position_size"],
        "capital_used": sizing["capital_used"],
        "risk_amount": sizing["risk_amount"],
        "risk_per_trade_pct": sizing["risk_per_trade_pct"],
        "risk_per_share": sizing["risk_per_share"],
        "sizing_valid": sizing["sizing_valid"],
        "skip_reason": sizing["skip_reason"],
        "paper_trade_id": paper_trade_id,
        "is_paper_trade": True,
        "mode": mode,
    })
    return trade


def place_paper_order(account: Dict[str, Any], trade: Dict[str, Any]) -> Dict[str, Any]:
    account = load_paper_account() if not isinstance(account, dict) else account
    trade = _dict(trade)
    if safe_text(account.get("paper_trading_status"), "ACTIVE").upper() == "LOCKED":
        return {"accepted": False, "reason": "PAPER_ACCOUNT_LOCKED"}
    daily_limit = check_daily_loss_limit(account)
    drawdown_limit = check_max_drawdown(account)
    if daily_limit.get("limit_hit") or drawdown_limit.get("limit_hit"):
        if drawdown_limit.get("limit_hit"):
            account["paper_trading_status"] = "LOCKED"
        save_paper_account(account)
        return {"accepted": False, "reason": daily_limit.get("reason") or "RISK_LIMIT_LOCKED"}

    trade = prepare_paper_trade_fields(trade, account)
    qty = safe_int(trade.get("quantity"), 0)
    entry = safe_float(trade.get("entry_price") or trade.get("entry") or trade.get("price"), 0.0)
    if qty <= 0 or entry <= 0 or safe_float(trade.get("position_size"), 0.0) > safe_float(account.get("current_balance"), DEFAULT_INITIAL_BALANCE):
        return {"accepted": False, "reason": safe_text(trade.get("skip_reason"), "INVALID_SIZE_OR_ENTRY"), "trade": trade}

    order = {
        "paper_order_id": f"PO-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "paper_trade_id": trade.get("paper_trade_id"),
        "created_at": _now(),
        "symbol": _trade_symbol(trade),
        "side": _trade_side(trade),
        "entry": entry,
        "entry_price": entry,
        "sl": safe_float(trade.get("sl") or trade.get("stop_loss") or trade.get("stoploss"), 0.0),
        "stop_loss": safe_float(trade.get("sl") or trade.get("stop_loss") or trade.get("stoploss"), 0.0),
        "target": safe_float(trade.get("target") or trade.get("tp") or trade.get("t1"), 0.0),
        "tp": safe_float(trade.get("target") or trade.get("tp") or trade.get("t1"), 0.0),
        "quantity": qty,
        "qty": qty,
        "position_size": safe_float(trade.get("position_size"), 0.0),
        "capital_used": safe_float(trade.get("capital_used") or trade.get("position_size"), 0.0),
        "risk_amount": safe_float(trade.get("risk_amount"), 0.0),
        "risk_per_trade_pct": safe_float(trade.get("risk_per_trade_pct"), MAX_RISK_PER_TRADE_PCT),
        "status": "PENDING",
        "source": "TITAN_PAPER_ONLY",
        "accepted": True,
        "live_order": False,
        "is_paper_trade": True,
        "mode": trade.get("mode") or "",
    }
    generate_paper_audit_log({"event": "PAPER_ORDER_CREATED", "order": order})
    return order


def simulate_slippage(order: Dict[str, Any], market_context: Any = None) -> float:
    order = _dict(order)
    context = _dict(market_context)
    volatility = safe_float(context.get("volatility_score") or context.get("portfolio_heat_score"), 50.0)
    liquidity = safe_float(context.get("liquidity_score"), 50.0)
    entry = safe_float(order.get("entry"), 0.0)
    bps = max(1.0, min(30.0, 3.0 + volatility * 0.06 - liquidity * 0.025))
    return round(entry * bps / 10000.0, 4)


def simulate_brokerage(order: Dict[str, Any]) -> float:
    order = _dict(order)
    turnover = safe_float(order.get("entry"), 0.0) * safe_float(order.get("quantity"), 0.0)
    return round(min(40.0, max(2.0, turnover * 0.0003)), 2)


def simulate_fill(order: Dict[str, Any], market_context: Any = None) -> Dict[str, Any]:
    result = dict(_dict(order))
    if not result.get("accepted", True):
        result["status"] = "REJECTED"
        return result
    slippage = simulate_slippage(result, market_context)
    side = safe_text(result.get("side"), "LONG").upper()
    entry = safe_float(result.get("entry"), 0.0)
    fill_price = entry + slippage if side == "LONG" else entry - slippage
    result.update({
        "status": "FILLED",
        "filled_at": _now(),
        "fill_price": round(fill_price, 4),
        "slippage": slippage,
        "brokerage": simulate_brokerage(result),
    })
    return result


def open_paper_position(account: Dict[str, Any], order: Dict[str, Any]) -> Dict[str, Any]:
    account = load_paper_account() if not isinstance(account, dict) else account
    order = _dict(order)
    if safe_text(account.get("paper_trading_status"), "ACTIVE").upper() == "LOCKED":
        return account
    if safe_text(order.get("status"), "").upper() != "FILLED":
        return account
    positions = _list(account.get("open_positions"))
    position = {
        "paper_position_id": f"PP-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "paper_order_id": order.get("paper_order_id"),
        "paper_trade_id": order.get("paper_trade_id"),
        "opened_at": _now(),
        "symbol": order.get("symbol"),
        "side": order.get("side"),
        "entry": order.get("entry_price") or order.get("entry") or order.get("fill_price"),
        "entry_price": order.get("entry_price") or order.get("entry") or order.get("fill_price"),
        "sl": order.get("sl"),
        "stop_loss": order.get("stop_loss") or order.get("sl"),
        "target": order.get("target"),
        "tp": order.get("tp") or order.get("target"),
        "quantity": order.get("quantity"),
        "qty": order.get("qty") or order.get("quantity"),
        "position_size": order.get("position_size"),
        "capital_used": order.get("capital_used") or order.get("position_size"),
        "risk_amount": order.get("risk_amount"),
        "risk_per_trade_pct": order.get("risk_per_trade_pct"),
        "brokerage": order.get("brokerage"),
        "status": "OPEN",
        "last_price": order.get("fill_price") or order.get("entry_price"),
        "open_pnl": 0.0,
        "live_order": False,
        "is_paper_trade": True,
        "mode": order.get("mode") or "",
    }
    positions.append(position)
    account["open_positions"] = positions
    save_paper_account(account)
    generate_paper_audit_log({"event": "PAPER_POSITION_OPENED", "position": position})
    return account


def close_paper_position(account: Dict[str, Any], position: Dict[str, Any], outcome: Dict[str, Any]) -> Dict[str, Any]:
    account = load_paper_account() if not isinstance(account, dict) else account
    position = dict(_dict(position))
    outcome = _dict(outcome)
    exit_price = safe_float(outcome.get("exit_price") or outcome.get("price"), safe_float(position.get("last_price"), safe_float(position.get("entry"))))
    qty = safe_float(position.get("quantity"), 0.0)
    entry = safe_float(position.get("entry"), 0.0)
    side = safe_text(position.get("side"), "LONG").upper()
    pnl = (exit_price - entry) * qty if side == "LONG" else (entry - exit_price) * qty
    position.update({
        "closed_at": _now(),
        "exit_price": exit_price,
        "status": "CLOSED",
        "outcome": outcome.get("outcome") or outcome.get("result") or "MANUAL",
        "closed_pnl": round(pnl, 2),
        "realized_pnl": round(pnl, 2),
    })
    account["open_positions"] = [p for p in _list(account.get("open_positions")) if p.get("paper_position_id") != position.get("paper_position_id")]
    account["closed_positions"] = _list(account.get("closed_positions")) + [position]
    account = update_paper_balance(account, pnl)
    save_paper_account(account)
    generate_paper_audit_log({"event": "PAPER_POSITION_CLOSED", "position": position})
    return account


def update_paper_balance(account: Dict[str, Any], pnl: Any) -> Dict[str, Any]:
    source = account if isinstance(account, dict) else {}
    open_positions = _list(source.get("open_positions"))
    closed_positions = _list(source.get("closed_positions"))
    account = _normalize_account(source)
    account["open_positions"] = open_positions
    account["closed_positions"] = closed_positions
    account["current_balance"] = round(safe_float(account.get("current_balance"), DEFAULT_INITIAL_BALANCE) + safe_float(pnl), 2)
    account["balance"] = account["current_balance"]
    account["open_pnl"] = calculate_open_pnl(account)
    account["closed_pnl"] = calculate_closed_pnl(account)
    account["equity"] = round(account["current_balance"] + account["open_pnl"], 2)
    if not account.get("daily_start_balance"):
        account["daily_start_balance"] = account["current_balance"] - safe_float(pnl)
    account["daily_pnl"] = round(account["current_balance"] - safe_float(account.get("daily_start_balance"), account["current_balance"]), 2)
    account = update_daily_trailing_protection(account)
    if check_max_drawdown(account).get("limit_hit"):
        account["paper_trading_status"] = "LOCKED"
    return account


def update_daily_trailing_protection(account: Dict[str, Any]) -> Dict[str, Any]:
    account = account if isinstance(account, dict) else {}
    start = safe_float(account.get("daily_start_balance"), safe_float(account.get("initial_balance"), DEFAULT_INITIAL_BALANCE))
    daily_pnl = safe_float(account.get("daily_pnl"), 0.0)
    peak = max(safe_float(account.get("daily_peak_pnl"), 0.0), daily_pnl)
    base_floor = -round(start * DAILY_LOSS_LIMIT_PCT / 100.0, 2)

    if peak >= start * 0.03:
        floor_value = round(peak * 0.50, 2)
    elif peak >= start * 0.015:
        floor_value = 0.0
    elif peak > 0:
        floor_value = max(base_floor, round(peak - (start * DAILY_LOSS_LIMIT_PCT / 100.0), 2))
    else:
        floor_value = base_floor

    account["daily_peak_pnl"] = round(peak, 2)
    account["daily_loss_floor"] = round(floor_value, 2)
    account["daily_trailing_protection"] = {
        "start_balance": round(start, 2),
        "current_daily_pnl": round(daily_pnl, 2),
        "peak_daily_pnl": round(peak, 2),
        "allowed_daily_pnl_floor": round(floor_value, 2),
        "initial_max_daily_loss": round(abs(base_floor), 2),
        "trading_blocked": bool(daily_pnl <= floor_value),
    }
    return account


def calculate_open_pnl(account: Dict[str, Any]) -> float:
    total = 0.0
    for position in _list(account.get("open_positions")):
        entry = safe_float(position.get("entry"), 0.0)
        last = safe_float(position.get("last_price"), entry)
        qty = safe_float(position.get("quantity"), 0.0)
        side = safe_text(position.get("side"), "LONG").upper()
        total += (last - entry) * qty if side == "LONG" else (entry - last) * qty
    return round(total, 2)


def calculate_closed_pnl(account: Dict[str, Any]) -> float:
    return round(sum(safe_float(item.get("closed_pnl"), 0.0) for item in _list(account.get("closed_positions"))), 2)


def calculate_drawdown(account: Dict[str, Any]) -> float:
    initial = safe_float(account.get("initial_balance"), DEFAULT_INITIAL_BALANCE)
    equity = safe_float(account.get("current_balance"), initial) + calculate_open_pnl(account)
    return round(max(0.0, (initial - equity) / max(initial, 1.0) * 100.0), 2)


def check_daily_loss_limit(account: Dict[str, Any]) -> Dict[str, Any]:
    rules = _dict(account.get("risk_rules"))
    start = safe_float(account.get("daily_start_balance"), safe_float(account.get("initial_balance"), DEFAULT_INITIAL_BALANCE))
    equity = safe_float(account.get("current_balance"), start) + calculate_open_pnl(account)
    daily_pnl = round(equity - start, 2)
    account["daily_pnl"] = daily_pnl
    account = update_daily_trailing_protection(account)
    limit = safe_float(rules.get("daily_loss_limit_pct"), DAILY_LOSS_LIMIT_PCT)
    floor_value = safe_float(account.get("daily_loss_floor"), -round(start * limit / 100.0, 2))
    loss_pct = max(0.0, (start - equity) / max(start, 1.0) * 100.0)
    return {
        "daily_loss_pct": round(loss_pct, 2),
        "daily_pnl": daily_pnl,
        "limit_pct": limit,
        "allowed_daily_pnl_floor": round(floor_value, 2),
        "limit_hit": bool(daily_pnl <= floor_value),
        "reason": "DAILY_TRAILING_PROTECTION" if daily_pnl <= floor_value else "",
    }


def check_max_drawdown(account: Dict[str, Any]) -> Dict[str, Any]:
    rules = _dict(account.get("risk_rules"))
    drawdown = calculate_drawdown(account)
    limit = safe_float(rules.get("max_drawdown_pct"), MAX_DRAWDOWN_PCT)
    return {"drawdown_pct": drawdown, "limit_pct": limit, "limit_hit": bool(drawdown >= limit)}


def _closed_outcome(row: Dict[str, Any]) -> str:
    value = safe_text(
        row.get("outcome")
        or row.get("result")
        or row.get("status")
        or row.get("trade_result")
    ).upper()
    if value in {"TP", "WIN", "TARGET", "TARGET_HIT", "PROFIT"}:
        return "TP"
    if value in {"SL", "LOSS", "STOP_LOSS", "STOPLOSS", "SL_HIT"}:
        return "SL"
    return ""


def _trade_sync_key(row: Dict[str, Any]) -> str:
    paper_trade_id = safe_text(row.get("paper_trade_id"))
    if paper_trade_id:
        return paper_trade_id
    symbol = _trade_symbol(row)
    side = _trade_side(row)
    status = _closed_outcome(row) or safe_text(row.get("status")).upper()
    timestamp = safe_text(row.get("closed_at") or row.get("updated_at") or row.get("created_at") or row.get("opened_at"))
    trade_id = safe_text(row.get("trade_id") or row.get("id"))
    entry = safe_text(row.get("entry") or row.get("entry_price") or row.get("buy_price") or row.get("signal_entry"))
    exit_price = safe_text(row.get("exit") or row.get("exit_price") or row.get("close_price") or row.get("closed_price"))
    quantity = safe_text(row.get("quantity") or row.get("qty"))
    return "|".join([trade_id, symbol, side, timestamp, status, entry, exit_price, quantity])


def _paper_sync_position_id(sync_key: str) -> str:
    digest = hashlib.sha1(sync_key.encode("utf-8")).hexdigest()[:16]
    return f"PSYNC-{digest.upper()}"


def _closed_position_keys(closed_positions: List[Dict[str, Any]]) -> set:
    keys = set(safe_text(item) for item in _list(_read_json(PROCESSED_RESULTS_PATH, [])) if safe_text(item))
    for item in closed_positions:
        if not isinstance(item, dict):
            continue
        for key_name in ("paper_sync_key", "trade_id", "paper_trade_id"):
            value = safe_text(item.get(key_name))
            if value:
                keys.add(value)
        keys.add(_trade_sync_key(item))
    return keys


def _timestamp_key(value: Any) -> str:
    return safe_text(value).replace("T", " ")[:19]


def _row_is_before_account_start(account: Dict[str, Any], row: Dict[str, Any]) -> bool:
    if safe_text(account.get("capital_mode")) != "ADAPTIVE_1K":
        return False
    account_start = _timestamp_key(account.get("created_at"))
    row_time = _timestamp_key(row.get("closed_at") or row.get("opened_at") or row.get("created_at"))
    return bool(account_start and row_time and row_time < account_start)


def _read_local_trade_result_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        if TRADE_OUTCOMES_JSONL.exists():
            for line in TRADE_OUTCOMES_JSONL.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        rows.append(row)
                except Exception:
                    continue
    except Exception:
        pass

    try:
        if TRADE_OUTCOMES_CSV.exists():
            with open(TRADE_OUTCOMES_CSV, "r", newline="", encoding="utf-8") as f:
                rows.extend(dict(row) for row in csv.DictReader(f))
    except Exception:
        pass

    return rows


def _get_supabase_trade_results() -> List[Dict[str, Any]]:
    try:
        try:
            from titan_master_brain.supabase_client import supabase
        except Exception:
            supabase = None
        if supabase is None:
            try:
                from titan_brain.supabase_client import supabase
            except Exception:
                supabase = None
        if supabase is None:
            return []

        result = (
            supabase.table("trade_results")
            .select("*")
            .in_("outcome", ["TP", "SL"])
            .order("closed_at", desc=False)
            .limit(500)
            .execute()
        )
        return [row for row in (result.data or []) if isinstance(row, dict)]
    except Exception:
        return []


def _resolve_exit_price(row: Dict[str, Any], outcome: str) -> float:
    exit_price = safe_float(row.get("exit") or row.get("exit_price") or row.get("close_price") or row.get("closed_price"), 0.0)
    if exit_price > 0:
        return exit_price
    if outcome == "TP":
        return safe_float(row.get("target") or row.get("tp") or row.get("target_price") or row.get("t1"), 0.0)
    if outcome == "SL":
        return safe_float(row.get("stop_loss") or row.get("sl") or row.get("stop_price") or row.get("stoploss"), 0.0)
    return 0.0


def _estimate_quantity(account: Dict[str, Any], row: Dict[str, Any], matched_position: Dict[str, Any] | None = None) -> float:
    if matched_position:
        qty = safe_float(matched_position.get("quantity"), 0.0)
        if qty > 0:
            return qty

    for key in ("quantity", "qty", "shares"):
        qty = safe_float(row.get(key), 0.0)
        if qty > 0:
            return qty

    entry = safe_float(row.get("entry") or row.get("entry_price") or row.get("buy_price") or row.get("signal_entry"), 0.0)
    position_size = safe_float(row.get("position_size"), 0.0)
    if entry > 0 and position_size > 0:
        return position_size / entry

    row["skipped_pnl_reason"] = "MISSING_QUANTITY"
    return 0.0


def _find_matching_open_position(open_positions: List[Dict[str, Any]], row: Dict[str, Any]) -> Dict[str, Any] | None:
    symbol = _trade_symbol(row)
    side = _trade_side(row)
    entry = safe_float(row.get("entry") or row.get("entry_price") or row.get("buy_price") or row.get("signal_entry"), 0.0)

    for position in open_positions:
        if not isinstance(position, dict):
            continue
        if safe_text(position.get("status"), "OPEN").upper() not in {"OPEN", "FILLED", "PENDING"}:
            continue
        if _trade_symbol(position) != symbol or _trade_side(position) != side:
            continue
        position_entry = safe_float(position.get("entry") or position.get("fill_price"), 0.0)
        if entry <= 0 or position_entry <= 0 or abs(position_entry - entry) <= max(0.05, entry * 0.005):
            return position
    return None


def _calculate_trade_pnl(row: Dict[str, Any], quantity: float, exit_price: float) -> float:
    entry = safe_float(row.get("entry") or row.get("entry_price") or row.get("buy_price") or row.get("signal_entry"), 0.0)
    side = _trade_side(row)
    if entry <= 0 or exit_price <= 0 or quantity <= 0:
        return 0.0
    pnl = (exit_price - entry) * quantity if side == "LONG" else (entry - exit_price) * quantity
    return round(pnl, 2)


def _recalculate_account_totals(account: Dict[str, Any]) -> Dict[str, Any]:
    for position in _list(account.get("closed_positions")):
        if not isinstance(position, dict):
            continue
        sync_key = safe_text(position.get("paper_sync_key"))
        if sync_key and safe_text(position.get("source")) == "TRADE_RESULTS_SYNC":
            position["paper_position_id"] = _paper_sync_position_id(sync_key)
    account["open_pnl"] = calculate_open_pnl(account)
    account["closed_pnl"] = calculate_closed_pnl(account)
    account["balance"] = safe_float(account.get("current_balance"), DEFAULT_INITIAL_BALANCE)
    account["equity"] = round(account["balance"] + account["open_pnl"], 2)
    today_pnl = round(sum(
        safe_float(position.get("closed_pnl"), 0.0)
        for position in _list(account.get("closed_positions"))
        if safe_text(position.get("closed_at"))[:10] == _today()
    ), 2)
    account["daily_pnl"] = today_pnl
    account["daily_start_date"] = _today()
    account["daily_start_balance"] = round(account["balance"] - today_pnl, 2)
    return account


def sync_paper_account_from_trade_results(trade_rows: Any = None) -> Dict[str, Any]:
    """
    Reconciles closed TP/SL trade outcomes into paper account files exactly once.

    Sources are Supabase trade_results when available plus local journal outcomes.
    Passing trade_rows lets the outcome tracker sync the just-closed row without
    waiting for Supabase or CSV rereads.
    """
    account = load_paper_account()
    open_positions = [p for p in _list(account.get("open_positions")) if isinstance(p, dict)]
    closed_positions = [p for p in _list(account.get("closed_positions")) if isinstance(p, dict)]

    rows: List[Dict[str, Any]] = []
    if isinstance(trade_rows, dict):
        rows.append(trade_rows)
    elif isinstance(trade_rows, list):
        rows.extend(row for row in trade_rows if isinstance(row, dict))
    else:
        # Use Supabase trade_results only.
        # Do NOT fallback to old local CSV outcomes.
        # Otherwise clearing Supabase rebuilds old wins/losses/PnL from trade_outcomes.csv.
        rows.extend(_get_supabase_trade_results())

    seen_input_keys = set()
    processed_keys = _closed_position_keys(closed_positions)
    synced = 0
    skipped_duplicates = 0
    skipped_invalid = 0
    total_pnl = 0.0

    for row in rows:
        outcome = _closed_outcome(row)
        if outcome not in {"TP", "SL"}:
            continue
        if _row_is_before_account_start(account, row):
            skipped_invalid += 1
            continue

        key = _trade_sync_key(row)
        trade_id = safe_text(row.get("trade_id") or row.get("id"))
        duplicate_tokens = {key}
        if trade_id:
            duplicate_tokens.add(trade_id)

        if duplicate_tokens & processed_keys or key in seen_input_keys:
            skipped_duplicates += 1
            continue
        seen_input_keys.add(key)

        exit_price = _resolve_exit_price(row, outcome)
        entry = safe_float(row.get("entry") or row.get("entry_price") or row.get("buy_price") or row.get("signal_entry"), 0.0)
        if entry <= 0:
            row["skipped_pnl_reason"] = "MISSING_ENTRY_PRICE"
            skipped_invalid += 1
            continue
        if exit_price <= 0:
            row["skipped_pnl_reason"] = "MISSING_EXIT_PRICE"
            skipped_invalid += 1
            continue

        matched_position = _find_matching_open_position(open_positions, row)
        quantity = _estimate_quantity(account, row, matched_position)
        pnl = _calculate_trade_pnl(row, quantity, exit_price)
        if quantity <= 0:
            skipped_invalid += 1
            continue
        if _is_adaptive_1k_account(account):
            exposure = round(entry * quantity, 2)
            account_balance = max(safe_float(account.get("current_balance"), DEFAULT_INITIAL_BALANCE), DEFAULT_INITIAL_BALANCE)
            if exposure > account_balance:
                row["skipped_pnl_reason"] = "LEGACY_POSITION_SIZE_EXCEEDS_ADAPTIVE_1K_BALANCE"
                skipped_invalid += 1
                continue

        closed_position = dict(matched_position or {})
        closed_position.update({
            "paper_position_id": closed_position.get("paper_position_id") or _paper_sync_position_id(key),
            "paper_sync_key": key,
            "trade_id": trade_id,
            "paper_trade_id": row.get("paper_trade_id") or closed_position.get("paper_trade_id") or trade_id or _paper_sync_position_id(key),
            "symbol": _trade_symbol(row),
            "side": _trade_side(row),
            "entry": entry,
            "entry_price": entry,
            "sl": safe_float(row.get("sl") or row.get("stop_loss") or row.get("stoploss"), 0.0),
            "stop_loss": safe_float(row.get("sl") or row.get("stop_loss") or row.get("stoploss"), 0.0),
            "target": safe_float(row.get("target") or row.get("tp") or row.get("target_price") or row.get("t1"), 0.0),
            "tp": safe_float(row.get("target") or row.get("tp") or row.get("target_price") or row.get("t1"), 0.0),
            "quantity": quantity,
            "qty": quantity,
            "position_size": round(entry * quantity, 2),
            "capital_used": row.get("capital_used") or closed_position.get("capital_used") or round(entry * quantity, 2),
            "risk_amount": row.get("risk_amount") or closed_position.get("risk_amount"),
            "risk_per_trade_pct": row.get("risk_per_trade_pct") or closed_position.get("risk_per_trade_pct"),
            "risk_per_share": row.get("risk_per_share") or closed_position.get("risk_per_share"),
            "closed_at": row.get("closed_at") or _now(),
            "exit_price": exit_price,
            "status": "CLOSED",
            "outcome": outcome,
            "result": "WIN" if outcome == "TP" else "LOSS",
            "closed_pnl": pnl,
            "realized_pnl": pnl,
            "source": "TRADE_RESULTS_SYNC",
            "live_order": False,
            "is_paper_trade": True,
            "mode": row.get("mode") or closed_position.get("mode") or "",
        })

        match_id = safe_text(closed_position.get("paper_position_id"))
        if match_id:
            open_positions = [
                p for p in open_positions
                if safe_text(p.get("paper_position_id")) != match_id
            ]

        closed_positions.append(closed_position)
        processed_keys.update(duplicate_tokens)
        processed_keys.add(key)
        account["current_balance"] = round(safe_float(account.get("current_balance"), DEFAULT_INITIAL_BALANCE) + pnl, 2)
        total_pnl = round(total_pnl + pnl, 2)
        synced += 1

    account["open_positions"] = open_positions
    account["closed_positions"] = closed_positions
    account = _recalculate_account_totals(account)
    save_paper_account(account)
    _write_json(PROCESSED_RESULTS_PATH, sorted(processed_keys))

    if synced:
        generate_paper_audit_log({
            "event": "PAPER_ACCOUNT_SYNC_FROM_TRADE_RESULTS",
            "synced": synced,
            "pnl": total_pnl,
            "current_balance": account.get("current_balance"),
            "closed_pnl": account.get("closed_pnl"),
            "daily_pnl": account.get("daily_pnl"),
        })

    return {
        "synced": synced,
        "skipped_duplicates": skipped_duplicates,
        "skipped_invalid": skipped_invalid,
        "current_balance": account.get("current_balance"),
        "closed_pnl": account.get("closed_pnl"),
        "daily_pnl": account.get("daily_pnl"),
    }


def calculate_paper_portfolio_metrics(account: Dict[str, Any]) -> Dict[str, Any]:
    open_positions = _list(account.get("open_positions"))
    closed_positions = _list(account.get("closed_positions"))
    wins = sum(1 for item in closed_positions if safe_float(item.get("closed_pnl"), 0.0) > 0)
    losses = sum(1 for item in closed_positions if safe_float(item.get("closed_pnl"), 0.0) < 0)
    gross_win = sum(max(0.0, safe_float(item.get("closed_pnl"), 0.0)) for item in closed_positions)
    gross_loss = abs(sum(min(0.0, safe_float(item.get("closed_pnl"), 0.0)) for item in closed_positions))
    return {
        "open_position_count": len(open_positions),
        "closed_position_count": len(closed_positions),
        "win_rate": round(wins / max(1, wins + losses) * 100.0, 2),
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss > 0 else (round(gross_win, 4) if gross_win > 0 else 0.0),
        "gross_win": round(gross_win, 2),
        "gross_loss": round(gross_loss, 2),
        "exposure": round(sum(safe_float(p.get("entry"), 0.0) * safe_float(p.get("quantity"), 0.0) for p in open_positions), 2),
    }


def generate_paper_audit_log(event: Any) -> Dict[str, Any]:
    _ensure_storage()
    row = {"timestamp": _now(), **_dict(event)}
    logs = _read_json(AUDIT_LOG_PATH, [])
    logs = _list(logs)
    logs.append(row)
    _write_json(AUDIT_LOG_PATH, logs[-1000:])
    return row


def compare_paper_vs_live(paper_results: Any = None, live_results: Any = None) -> Dict[str, Any]:
    paper = _list(paper_results)
    live = _list(live_results)
    paper_pnl = sum(safe_float(item.get("closed_pnl") or item.get("pnl"), 0.0) for item in paper if isinstance(item, dict))
    live_pnl = sum(safe_float(item.get("pnl") or item.get("closed_pnl"), 0.0) for item in live if isinstance(item, dict))
    return {
        "paper_trades": len(paper),
        "live_trades": len(live),
        "paper_pnl": round(paper_pnl, 2),
        "live_pnl": round(live_pnl, 2),
        "difference": round(paper_pnl - live_pnl, 2),
        "comparison_available": bool(paper and live),
    }


def build_paper_trading_report(account: Dict[str, Any]) -> Dict[str, Any]:
    account = load_paper_account() if not isinstance(account, dict) else account
    open_pnl = calculate_open_pnl(account)
    closed_pnl = calculate_closed_pnl(account)
    equity = round(safe_float(account.get("current_balance"), DEFAULT_INITIAL_BALANCE) + open_pnl, 2)
    drawdown = check_max_drawdown(account)
    daily = check_daily_loss_limit(account)
    metrics = calculate_paper_portfolio_metrics(account)
    if drawdown.get("limit_hit"):
        account["paper_trading_status"] = "LOCKED"
        save_paper_account(account)
    status = safe_text(account.get("paper_trading_status"), "ACTIVE").upper()
    risk_status = "LOCKED_MAX_DRAWDOWN" if drawdown.get("limit_hit") else "DAILY_LOSS_LIMIT_HIT" if daily.get("limit_hit") else "OK"
    audit_log = _read_json(AUDIT_LOG_PATH, [])
    explanations = []
    explanations.append("Paper trading is simulation-only; no broker orders are placed.")
    if status == "LOCKED":
        explanations.append("Paper account is locked because a risk limit was reached.")
    if not _list(account.get("open_positions")):
        explanations.append("No open paper positions currently tracked.")
    return {
        "advisory_only": True,
        "paper_only": True,
        "shadow_mode": True,
        "live_order_allowed": False,
        "broker_orders": False,
        "telegram_changes": False,
        "supabase_writes": False,
        "live_rank_mutation_allowed": False,
        "pyramid_placement": "master_controller_paper_sidecar",
        "paper_trading_status": status,
        "initial_balance": safe_float(account.get("initial_balance"), DEFAULT_INITIAL_BALANCE),
        "current_balance": safe_float(account.get("current_balance"), DEFAULT_INITIAL_BALANCE),
        "equity": equity,
        "open_pnl": open_pnl,
        "closed_pnl": closed_pnl,
        "drawdown_pct": drawdown.get("drawdown_pct"),
        "daily_loss_pct": daily.get("daily_loss_pct"),
        "open_positions": _list(account.get("open_positions")),
        "closed_positions": _list(account.get("closed_positions")),
        "portfolio_metrics": metrics,
        "paper_vs_live": compare_paper_vs_live(account.get("closed_positions"), []),
        "risk_status": risk_status,
        "audit_log_count": len(_list(audit_log)),
        "explanations": explanations,
    }


if __name__ == "__main__":
    account = load_paper_account()
    if not account:
        account = initialize_paper_account()
    sample_trade = {
        "symbol": "TCS",
        "side": "LONG",
        "entry": 3900,
        "sl": 3860,
        "target": 3980,
    }
    order = place_paper_order(account, sample_trade)
    if order.get("accepted"):
        filled = simulate_fill(order, {"volatility_score": 40, "liquidity_score": 70})
        account = open_paper_position(load_paper_account(), filled)
    print(json.dumps(build_paper_trading_report(load_paper_account()), indent=2, sort_keys=True))
