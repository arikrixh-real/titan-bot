import json
from pathlib import Path


DEFAULT_CAPITAL = 1000.0
ACCOUNT_PATH = Path("data/paper_trading/paper_account.json")


def _current_capital(default=DEFAULT_CAPITAL):
    try:
        if not ACCOUNT_PATH.exists() or ACCOUNT_PATH.stat().st_size == 0:
            return default
        account = json.loads(ACCOUNT_PATH.read_text(encoding="utf-8"))
        if not isinstance(account, dict):
            return default
        balance = float(
            account.get("current_balance")
            or account.get("balance")
            or account.get("initial_balance")
            or default
        )
        if account.get("capital_mode") != "ADAPTIVE_1K" and balance >= 99999:
            return default
        return max(balance, 0.0)
    except Exception:
        return default


def calculate_position_size(stock_data, risk_management):
    capital = _current_capital()

    entry = float(stock_data.get("entry", 0))
    sl = float(stock_data.get("sl", 0))

    if entry <= 0 or sl <= 0:
        return {
            "qty": 0,
            "capital": capital,
            "risk_amount": 0,
            "status": "INVALID_DATA"
        }

    risk_per_share = abs(entry - sl)

    risk_percent = risk_management.get("suggested_risk_percent", 0.5)

    risk_amount = capital * (risk_percent / 100)

    if risk_per_share == 0:
        return {
            "qty": 0,
            "capital": capital,
            "risk_amount": risk_amount,
            "status": "ZERO_RISK"
        }

    qty = int(risk_amount / risk_per_share)
    if qty * entry > capital:
        qty = 0
        status = "INSUFFICIENT_CAPITAL"
    else:
        status = "OK"

    return {
        "qty": qty,
        "capital": capital,
        "risk_amount": round(risk_amount, 2),
        "risk_per_share": round(risk_per_share, 2),
        "status": status
    }
