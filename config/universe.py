import json
from pathlib import Path

from config.nifty100 import NIFTY100


SMALL_CAPITAL_PRIORITY = [
    "NIFTYBEES", "YESBANK", "SUZLON", "IDFCFIRSTB", "PNB", "BANKBARODA",
    "CANBK", "SAIL", "NMDC", "GAIL", "IOC", "ONGC", "TATASTEEL",
    "ASHOKLEY", "FEDERALBNK", "VEDL", "HINDPETRO", "BPCL",
]


def _paper_balance(default=1000.0):
    try:
        path = Path("data/paper_trading/paper_account.json")
        if not path.exists() or path.stat().st_size == 0:
            return default
        account = json.loads(path.read_text(encoding="utf-8"))
        balance = float(account.get("current_balance") or account.get("balance") or account.get("initial_balance") or default)
        if account.get("capital_mode") != "ADAPTIVE_1K" and balance >= 99999:
            return default
        return max(balance, 0.0)
    except Exception:
        return default


def _with_ns(symbols):
    result = []
    seen = set()
    for symbol in symbols:
        clean = str(symbol).replace(".NS", "").upper().strip()
        if clean and clean not in seen:
            result.append(f"{clean}.NS")
            seen.add(clean)
    return result


def get_capital_adaptive_universe(balance=None):
    balance = _paper_balance() if balance is None else float(balance or 0.0)
    major = list(NIFTY100)
    if balance < 5000:
        ordered = SMALL_CAPITAL_PRIORITY + major
    elif balance < 25000:
        ordered = SMALL_CAPITAL_PRIORITY[:10] + major
    else:
        ordered = ["NIFTYBEES"] + major
    return _with_ns(ordered)


NSE_STOCKS = get_capital_adaptive_universe()
