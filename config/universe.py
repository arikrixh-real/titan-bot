import json
from pathlib import Path

from config.nifty100 import NIFTY100


MICRO_CAPITAL_PRICE_SOFT_CAP = 700.0
MICRO_CAPITAL_TIGHT_SL_PCT = 0.75

SMALL_CAPITAL_PRIORITY = [
    "NIFTYBEES", "BANKBARODA", "CANBK", "PNB", "IDFCFIRSTB",
    "FEDERALBNK", "YESBANK", "SAIL", "NMDC", "GAIL", "ONGC",
    "BEL", "BHEL", "IRFC", "IREDA", "RVNL", "NBCC", "NHPC", "SJVN",
    "TATASTEEL", "WIPRO", "VEDL", "INDUSTOWER", "NATIONALUM", "IDEA",
    "SUZLON", "IOC", "ASHOKLEY", "HINDPETRO", "BPCL",
]

MICRO_CAPITAL_PRIORITY = SMALL_CAPITAL_PRIORITY


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


def paper_account_snapshot(default=1000.0):
    try:
        path = Path("data/paper_trading/paper_account.json")
        if not path.exists() or path.stat().st_size == 0:
            return {"capital_mode": "ADAPTIVE_1K", "current_balance": default}
        account = json.loads(path.read_text(encoding="utf-8"))
        return account if isinstance(account, dict) else {"capital_mode": "ADAPTIVE_1K", "current_balance": default}
    except Exception:
        return {"capital_mode": "ADAPTIVE_1K", "current_balance": default}


def is_adaptive_1k_mode(account=None, balance=None):
    account = paper_account_snapshot() if account is None else account
    mode = str((account or {}).get("capital_mode") or "").upper()
    if mode == "ADAPTIVE_1K":
        return True
    if balance is None:
        balance = (account or {}).get("current_balance") or (account or {}).get("balance")
    try:
        return float(balance or 0.0) < 5000.0
    except Exception:
        return False


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
