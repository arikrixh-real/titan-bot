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
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


PAPER_DIR = Path("data/paper_trading")
ACCOUNT_PATH = PAPER_DIR / "paper_account.json"
POSITIONS_PATH = PAPER_DIR / "paper_positions.json"
CLOSED_POSITIONS_PATH = PAPER_DIR / "paper_closed_positions.json"
AUDIT_LOG_PATH = PAPER_DIR / "paper_audit_log.json"

DEFAULT_INITIAL_BALANCE = 100000.0
DEFAULT_CURRENCY = "INR"
MAX_RISK_PER_TRADE_PCT = 1.0
DAILY_LOSS_LIMIT_PCT = 2.0
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
    initial = safe_float(account.get("initial_balance"), DEFAULT_INITIAL_BALANCE)
    balance = safe_float(account.get("current_balance"), initial)
    status = safe_text(account.get("paper_trading_status"), "ACTIVE").upper()
    if status not in {"ACTIVE", "LOCKED"}:
        status = "ACTIVE"
    return {
        "paper_trading_status": status,
        "initial_balance": initial,
        "currency": safe_text(account.get("currency"), DEFAULT_CURRENCY),
        "current_balance": balance,
        "created_at": account.get("created_at") or _now(),
        "updated_at": _now(),
        "risk_rules": {
            "max_risk_per_trade_pct": safe_float(
                _dict(account.get("risk_rules")).get("max_risk_per_trade_pct"),
                MAX_RISK_PER_TRADE_PCT,
            ),
            "daily_loss_limit_pct": safe_float(
                _dict(account.get("risk_rules")).get("daily_loss_limit_pct"),
                DAILY_LOSS_LIMIT_PCT,
            ),
            "max_drawdown_pct": safe_float(
                _dict(account.get("risk_rules")).get("max_drawdown_pct"),
                MAX_DRAWDOWN_PCT,
            ),
        },
        "daily_start_balance": safe_float(account.get("daily_start_balance"), balance),
        "daily_start_date": account.get("daily_start_date") or _today(),
        "last_error": account.get("last_error"),
    }


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def load_paper_account() -> Dict[str, Any]:
    _ensure_storage()
    if not ACCOUNT_PATH.exists():
        return initialize_paper_account(DEFAULT_INITIAL_BALANCE)
    account = _normalize_account(_read_json(ACCOUNT_PATH, {}))
    positions = _read_json(POSITIONS_PATH, [])
    closed = _read_json(CLOSED_POSITIONS_PATH, [])
    account["open_positions"] = [item for item in _list(positions) if isinstance(item, dict)]
    account["closed_positions"] = [item for item in _list(closed) if isinstance(item, dict)]
    if account.get("daily_start_date") != _today():
        account["daily_start_date"] = _today()
        account["daily_start_balance"] = account.get("current_balance", DEFAULT_INITIAL_BALANCE)
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


def initialize_paper_account(initial_balance: float = 100000) -> Dict[str, Any]:
    _ensure_storage()
    account = {
        "paper_trading_status": "ACTIVE",
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
    account = _normalize_account(account)
    trade = _dict(trade)
    balance = safe_float(account.get("current_balance"), DEFAULT_INITIAL_BALANCE)
    rules = _dict(account.get("risk_rules"))
    risk_pct = safe_float(rules.get("max_risk_per_trade_pct"), MAX_RISK_PER_TRADE_PCT)
    risk_amount = balance * risk_pct / 100.0
    entry = safe_float(trade.get("entry") or trade.get("entry_price") or trade.get("price"), 0.0)
    stop = safe_float(trade.get("sl") or trade.get("stop_loss") or trade.get("stoploss"), 0.0)
    per_share_risk = abs(entry - stop)
    if entry <= 0:
        return 0
    if per_share_risk <= 0:
        return max(1, int(risk_amount / max(entry * 0.01, 1.0)))
    return max(0, int(risk_amount / per_share_risk))


def place_paper_order(account: Dict[str, Any], trade: Dict[str, Any]) -> Dict[str, Any]:
    account = load_paper_account() if not isinstance(account, dict) else account
    trade = _dict(trade)
    if safe_text(account.get("paper_trading_status"), "ACTIVE").upper() == "LOCKED":
        return {"accepted": False, "reason": "PAPER_ACCOUNT_LOCKED"}
    if check_daily_loss_limit(account).get("limit_hit") or check_max_drawdown(account).get("limit_hit"):
        account["paper_trading_status"] = "LOCKED"
        save_paper_account(account)
        return {"accepted": False, "reason": "RISK_LIMIT_LOCKED"}

    qty = calculate_position_size(account, trade)
    entry = safe_float(trade.get("entry") or trade.get("entry_price") or trade.get("price"), 0.0)
    if qty <= 0 or entry <= 0:
        return {"accepted": False, "reason": "INVALID_SIZE_OR_ENTRY"}

    order = {
        "paper_order_id": f"PO-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "created_at": _now(),
        "symbol": _trade_symbol(trade),
        "side": _trade_side(trade),
        "entry": entry,
        "sl": safe_float(trade.get("sl") or trade.get("stop_loss") or trade.get("stoploss"), 0.0),
        "target": safe_float(trade.get("target") or trade.get("tp") or trade.get("t1"), 0.0),
        "quantity": qty,
        "status": "PENDING",
        "source": "TITAN_PAPER_ONLY",
        "accepted": True,
        "live_order": False,
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
        "opened_at": _now(),
        "symbol": order.get("symbol"),
        "side": order.get("side"),
        "entry": order.get("fill_price"),
        "sl": order.get("sl"),
        "target": order.get("target"),
        "quantity": order.get("quantity"),
        "brokerage": order.get("brokerage"),
        "status": "OPEN",
        "last_price": order.get("fill_price"),
        "open_pnl": 0.0,
        "live_order": False,
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
    pnl -= safe_float(position.get("brokerage"), 0.0)
    pnl -= simulate_brokerage({"entry": exit_price, "quantity": qty})
    position.update({
        "closed_at": _now(),
        "exit_price": exit_price,
        "status": "CLOSED",
        "outcome": outcome.get("outcome") or outcome.get("result") or "MANUAL",
        "closed_pnl": round(pnl, 2),
    })
    account["open_positions"] = [p for p in _list(account.get("open_positions")) if p.get("paper_position_id") != position.get("paper_position_id")]
    account["closed_positions"] = _list(account.get("closed_positions")) + [position]
    account = update_paper_balance(account, pnl)
    save_paper_account(account)
    generate_paper_audit_log({"event": "PAPER_POSITION_CLOSED", "position": position})
    return account


def update_paper_balance(account: Dict[str, Any], pnl: Any) -> Dict[str, Any]:
    account = _normalize_account(account)
    account["current_balance"] = round(safe_float(account.get("current_balance"), DEFAULT_INITIAL_BALANCE) + safe_float(pnl), 2)
    if check_max_drawdown(account).get("limit_hit"):
        account["paper_trading_status"] = "LOCKED"
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
    loss_pct = max(0.0, (start - equity) / max(start, 1.0) * 100.0)
    limit = safe_float(rules.get("daily_loss_limit_pct"), DAILY_LOSS_LIMIT_PCT)
    return {"daily_loss_pct": round(loss_pct, 2), "limit_pct": limit, "limit_hit": bool(loss_pct >= limit)}


def check_max_drawdown(account: Dict[str, Any]) -> Dict[str, Any]:
    rules = _dict(account.get("risk_rules"))
    drawdown = calculate_drawdown(account)
    limit = safe_float(rules.get("max_drawdown_pct"), MAX_DRAWDOWN_PCT)
    return {"drawdown_pct": drawdown, "limit_pct": limit, "limit_hit": bool(drawdown >= limit)}


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
