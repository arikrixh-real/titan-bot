"""
TITAN Phase 24 - Broker Execution Safety System
-----------------------------------------------

Safety-control layer for any future broker execution. Defaults are fail-closed
for execution: DRY_RUN mode, live trading disabled, and execution_allowed false.
This module never places orders and never imports broker order placement code.
"""

from __future__ import annotations

import json
import math
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


SAFETY_DIR = Path("data/execution_safety")
STATE_PATH = SAFETY_DIR / "execution_safety_state.json"
AUDIT_LOG_PATH = SAFETY_DIR / "execution_safety_audit_log.json"


DEFAULT_STATE = {
    "broker_execution_mode": "DRY_RUN",
    "live_trading_enabled": False,
    "kill_switch_active": False,
    "emergency_exit_active": False,
    "risk_limits": {
        "max_daily_loss_pct": 2.0,
        "max_order_count_per_day": 3,
        "max_position_size_pct": 10.0,
        "max_single_trade_risk_pct": 1.0,
    },
    "updated_at": None,
    "last_reason": "initialized",
}


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


def safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _ensure_storage() -> None:
    SAFETY_DIR.mkdir(parents=True, exist_ok=True)
    if not AUDIT_LOG_PATH.exists():
        AUDIT_LOG_PATH.write_text("[]", encoding="utf-8")


def _normalize_state(state: Any) -> Dict[str, Any]:
    source = _dict(state)
    risk = _dict(source.get("risk_limits"))
    normalized = deepcopy(DEFAULT_STATE)
    normalized.update({
        "broker_execution_mode": safe_text(source.get("broker_execution_mode"), "DRY_RUN").upper(),
        "live_trading_enabled": safe_bool(source.get("live_trading_enabled"), False),
        "kill_switch_active": safe_bool(source.get("kill_switch_active"), False),
        "emergency_exit_active": safe_bool(source.get("emergency_exit_active"), False),
        "updated_at": source.get("updated_at") or _now(),
        "last_reason": safe_text(source.get("last_reason"), "loaded"),
    })
    if normalized["broker_execution_mode"] not in {"DRY_RUN", "LIVE_DISABLED", "LIVE_READY", "LOCKED"}:
        normalized["broker_execution_mode"] = "DRY_RUN"
    normalized["risk_limits"] = {
        "max_daily_loss_pct": safe_float(risk.get("max_daily_loss_pct"), 2.0),
        "max_order_count_per_day": safe_int(risk.get("max_order_count_per_day"), 3),
        "max_position_size_pct": safe_float(risk.get("max_position_size_pct"), 10.0),
        "max_single_trade_risk_pct": safe_float(risk.get("max_single_trade_risk_pct"), 1.0),
    }
    if not normalized["live_trading_enabled"] and normalized["broker_execution_mode"] == "LIVE_READY":
        normalized["broker_execution_mode"] = "LIVE_DISABLED"
    if normalized["kill_switch_active"] or normalized["emergency_exit_active"]:
        normalized["broker_execution_mode"] = "LOCKED"
    return normalized


def _write_json(path: Path, data: Any) -> bool:
    try:
        _ensure_storage()
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:
        return False


def _read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return deepcopy(default)
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return deepcopy(default)


def _audit(event: str, reason: str = "", details: Any = None) -> Dict[str, Any]:
    _ensure_storage()
    row = {"timestamp": _now(), "event": event, "reason": reason, "details": details or {}}
    logs = _list(_read_json(AUDIT_LOG_PATH, []))
    logs.append(row)
    _write_json(AUDIT_LOG_PATH, logs[-1000:])
    return row


def load_execution_safety_state() -> Dict[str, Any]:
    _ensure_storage()
    if not STATE_PATH.exists():
        return initialize_execution_safety_state()
    return _normalize_state(_read_json(STATE_PATH, DEFAULT_STATE))


def save_execution_safety_state(state: Any) -> bool:
    clean = _normalize_state(state)
    clean["updated_at"] = _now()
    return _write_json(STATE_PATH, clean)


def initialize_execution_safety_state() -> Dict[str, Any]:
    state = _normalize_state(DEFAULT_STATE)
    state["updated_at"] = _now()
    save_execution_safety_state(state)
    _audit("INITIALIZE_SAFETY_STATE", "default_dry_run")
    return state


def activate_kill_switch(reason: str = "manual") -> Dict[str, Any]:
    state = load_execution_safety_state()
    state["kill_switch_active"] = True
    state["broker_execution_mode"] = "LOCKED"
    state["last_reason"] = reason
    save_execution_safety_state(state)
    _audit("KILL_SWITCH_ACTIVATED", reason)
    return state


def deactivate_kill_switch(reason: str = "manual") -> Dict[str, Any]:
    state = load_execution_safety_state()
    state["kill_switch_active"] = False
    state["broker_execution_mode"] = "LIVE_DISABLED"
    state["live_trading_enabled"] = False
    state["last_reason"] = reason
    save_execution_safety_state(state)
    _audit("KILL_SWITCH_DEACTIVATED_LIVE_STILL_DISABLED", reason)
    return state


def check_live_trading_enabled(state: Any) -> Dict[str, Any]:
    state = _normalize_state(state)
    enabled = bool(state.get("live_trading_enabled")) and state.get("broker_execution_mode") == "LIVE_READY"
    return {"passed": enabled, "live_trading_enabled": bool(state.get("live_trading_enabled")), "mode": state.get("broker_execution_mode")}


def check_kill_switch(state: Any) -> Dict[str, Any]:
    state = _normalize_state(state)
    active = bool(state.get("kill_switch_active") or state.get("emergency_exit_active"))
    return {"passed": not active, "kill_switch_active": state.get("kill_switch_active"), "emergency_exit_active": state.get("emergency_exit_active")}


def check_max_daily_loss(state: Any, account_snapshot: Any = None) -> Dict[str, Any]:
    state = _normalize_state(state)
    snap = _dict(account_snapshot)
    limit = safe_float(state["risk_limits"].get("max_daily_loss_pct"), 2.0)
    loss_pct = safe_float(snap.get("daily_loss_pct") or snap.get("loss_pct"), 0.0)
    return {"passed": loss_pct < limit, "daily_loss_pct": round(loss_pct, 2), "limit_pct": limit}


def check_max_order_count(state: Any, order_history: Any = None) -> Dict[str, Any]:
    state = _normalize_state(state)
    limit = safe_int(state["risk_limits"].get("max_order_count_per_day"), 3)
    count = len([o for o in _list(order_history) if isinstance(o, dict)])
    return {"passed": count < limit, "order_count": count, "limit": limit}


def check_max_position_size(state: Any, order: Any = None, account_snapshot: Any = None) -> Dict[str, Any]:
    state = _normalize_state(state)
    order = _dict(order)
    snap = _dict(account_snapshot)
    capital = safe_float(snap.get("equity") or snap.get("balance") or snap.get("current_balance"), 100000.0)
    notional = safe_float(order.get("notional") or order.get("position_value"), 0.0)
    if notional <= 0:
        notional = safe_float(order.get("entry") or order.get("price"), 0.0) * safe_float(order.get("quantity") or order.get("qty"), 0.0)
    size_pct = notional / max(capital, 1.0) * 100.0
    limit = safe_float(state["risk_limits"].get("max_position_size_pct"), 10.0)
    return {"passed": size_pct <= limit, "position_size_pct": round(size_pct, 2), "limit_pct": limit}


def check_duplicate_order(state: Any, order: Any = None, order_history: Any = None) -> Dict[str, Any]:
    order = _dict(order)
    symbol = safe_text(order.get("symbol")).upper()
    side = safe_text(order.get("side")).upper()
    duplicate = False
    for old in _list(order_history):
        if not isinstance(old, dict):
            continue
        if safe_text(old.get("symbol")).upper() == symbol and safe_text(old.get("side")).upper() == side and safe_text(old.get("status"), "OPEN").upper() in {"OPEN", "PENDING", "LIVE"}:
            duplicate = True
            break
    return {"passed": not duplicate, "duplicate_order": duplicate, "symbol": symbol, "side": side}


def check_broker_connection(broker_status: Any = None) -> Dict[str, Any]:
    status = _dict(broker_status)
    connected = safe_bool(status.get("connected"), False)
    healthy = safe_text(status.get("status"), "DISCONNECTED").upper() in {"OK", "CONNECTED", "HEALTHY"}
    return {"passed": bool(connected and healthy), "connected": connected, "status": safe_text(status.get("status"), "DISCONNECTED")}


def check_rejected_order_handling(order_response: Any = None) -> Dict[str, Any]:
    response = _dict(order_response)
    rejected = safe_text(response.get("status")).upper() in {"REJECTED", "FAILED", "ERROR"}
    return {"passed": not rejected, "rejected": rejected, "reason": safe_text(response.get("reason") or response.get("error"))}


def check_execution_confirmation(order_response: Any = None) -> Dict[str, Any]:
    response = _dict(order_response)
    confirmed = safe_bool(response.get("confirmed"), False) or safe_text(response.get("status")).upper() in {"FILLED", "CONFIRMED"}
    return {"passed": confirmed, "confirmed": confirmed, "order_id": safe_text(response.get("order_id"))}


def enable_dry_run_mode(state: Any) -> Dict[str, Any]:
    state = _normalize_state(state)
    state["broker_execution_mode"] = "DRY_RUN"
    state["live_trading_enabled"] = False
    save_execution_safety_state(state)
    _audit("DRY_RUN_ENABLED", "safety")
    return state


def disable_live_execution(state: Any, reason: str = "safety") -> Dict[str, Any]:
    state = _normalize_state(state)
    state["broker_execution_mode"] = "LIVE_DISABLED"
    state["live_trading_enabled"] = False
    state["last_reason"] = reason
    save_execution_safety_state(state)
    _audit("LIVE_EXECUTION_DISABLED", reason)
    return state


def request_live_execution_permission(state: Any, reason: str = "manual_review_required") -> Dict[str, Any]:
    state = _normalize_state(state)
    state["broker_execution_mode"] = "LIVE_DISABLED"
    state["live_trading_enabled"] = False
    state["last_reason"] = reason
    save_execution_safety_state(state)
    _audit("LIVE_PERMISSION_REQUEST_RECORDED", reason)
    return state


def run_pre_order_safety_checks(order: Any = None, state: Any = None, account_snapshot: Any = None, order_history: Any = None, broker_status: Any = None) -> Dict[str, Any]:
    state = _normalize_state(state or load_execution_safety_state())
    checks = {
        "live_trading": check_live_trading_enabled(state),
        "kill_switch": check_kill_switch(state),
        "daily_loss": check_max_daily_loss(state, account_snapshot),
        "order_count": check_max_order_count(state, order_history),
        "position_size": check_max_position_size(state, order, account_snapshot),
        "duplicate_order": check_duplicate_order(state, order, order_history),
        "broker_connection": check_broker_connection(broker_status),
    }
    passed = all(item.get("passed") for item in checks.values())
    return {"execution_allowed": False if not passed else bool(state.get("live_trading_enabled") and state.get("broker_execution_mode") == "LIVE_READY"), "checks": checks, "fail_closed": True}


def trigger_emergency_exit(state: Any, reason: str = "risk_event") -> Dict[str, Any]:
    state = _normalize_state(state)
    state["emergency_exit_active"] = True
    state["kill_switch_active"] = True
    state["broker_execution_mode"] = "LOCKED"
    state["live_trading_enabled"] = False
    state["last_reason"] = reason
    save_execution_safety_state(state)
    _audit("EMERGENCY_EXIT_TRIGGERED", reason)
    return state


def manual_override(state: Any, action: Any = None, reason: str = "manual") -> Dict[str, Any]:
    state = _normalize_state(state)
    action = safe_text(action).upper()
    if action == "DRY_RUN":
        return enable_dry_run_mode(state)
    if action == "DISABLE_LIVE":
        return disable_live_execution(state, reason)
    if action == "KILL_SWITCH":
        return activate_kill_switch(reason)
    _audit("MANUAL_OVERRIDE_REJECTED", reason, {"action": action})
    return state


def reconcile_orders(local_orders: Any = None, broker_orders: Any = None) -> Dict[str, Any]:
    local = _list(local_orders)
    broker = _list(broker_orders)
    local_ids = {safe_text(o.get("order_id") or o.get("id")) for o in local if isinstance(o, dict)}
    broker_ids = {safe_text(o.get("order_id") or o.get("id")) for o in broker if isinstance(o, dict)}
    missing_at_broker = sorted(item for item in local_ids - broker_ids if item)
    unexpected_broker = sorted(item for item in broker_ids - local_ids if item)
    return {"passed": not missing_at_broker and not unexpected_broker, "local_count": len(local), "broker_count": len(broker), "missing_at_broker": missing_at_broker, "unexpected_broker": unexpected_broker}


def build_execution_safety_report(state: Any = None, account_snapshot: Any = None, order_history: Any = None, broker_status: Any = None) -> Dict[str, Any]:
    state = _normalize_state(state or load_execution_safety_state())
    sample_order = _dict(_list(order_history)[-1]) if _list(order_history) and isinstance(_list(order_history)[-1], dict) else {}
    daily = check_max_daily_loss(state, account_snapshot)
    count = check_max_order_count(state, order_history)
    size = check_max_position_size(state, sample_order, account_snapshot)
    duplicate = check_duplicate_order(state, sample_order, order_history[:-1] if isinstance(order_history, list) else [])
    broker = check_broker_connection(broker_status)
    rejected = check_rejected_order_handling({})
    confirm = check_execution_confirmation({})
    reconciliation = reconcile_orders(order_history, [])
    live = check_live_trading_enabled(state)
    kill = check_kill_switch(state)
    checks = [daily, count, size, duplicate, broker, live, kill]
    passed_count = sum(1 for item in checks if item.get("passed"))
    safety_score = round(passed_count / max(1, len(checks)) * 100.0, 2)
    execution_allowed = False
    if all(item.get("passed") for item in checks) and state.get("live_trading_enabled") and state.get("broker_execution_mode") == "LIVE_READY":
        execution_allowed = False  # Intentionally disabled until future explicit promotion.
    risk_status = "BLOCKED" if not kill.get("passed") or daily.get("passed") is False or not broker.get("passed") else "CAUTION" if safety_score < 85 else "SAFE"
    explanations = ["Execution is fail-closed by default; no broker orders are allowed."]
    if not state.get("live_trading_enabled"):
        explanations.append("Live trading is disabled.")
    if state.get("broker_execution_mode") == "DRY_RUN":
        explanations.append("Broker execution mode is DRY_RUN.")
    if not broker.get("passed"):
        explanations.append("Broker connection is not confirmed healthy.")
    return {
        "broker_execution_mode": state.get("broker_execution_mode"),
        "live_trading_enabled": bool(state.get("live_trading_enabled")),
        "kill_switch_active": bool(state.get("kill_switch_active")),
        "emergency_exit_active": bool(state.get("emergency_exit_active")),
        "daily_loss_check": daily,
        "order_count_check": count,
        "position_size_check": size,
        "duplicate_order_check": duplicate,
        "broker_connection_check": broker,
        "rejected_order_handling": rejected,
        "execution_confirmation_check": confirm,
        "order_reconciliation": reconciliation,
        "safety_score": safety_score,
        "execution_allowed": execution_allowed,
        "risk_status": risk_status,
        "explanations": explanations,
    }


if __name__ == "__main__":
    state = initialize_execution_safety_state()
    sample_order = {"symbol": "TCS", "side": "LONG", "entry": 3900, "quantity": 10, "status": "PENDING"}
    checks = run_pre_order_safety_checks(
        order=sample_order,
        state=state,
        account_snapshot={"balance": 100000, "daily_loss_pct": 0.0},
        order_history=[],
        broker_status={"connected": False, "status": "DISCONNECTED"},
    )
    report = build_execution_safety_report(
        state=state,
        account_snapshot={"balance": 100000, "daily_loss_pct": 0.0},
        order_history=[sample_order],
        broker_status={"connected": False, "status": "DISCONNECTED"},
    )
    print(json.dumps({"pre_order_checks": checks, "safety_report": report}, indent=2, sort_keys=True))
