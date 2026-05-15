import os
import random
import hashlib
import json
import pandas as pd
from datetime import datetime, timezone

try:
    from config.universe import (
        MICRO_CAPITAL_PRICE_SOFT_CAP,
        MICRO_CAPITAL_PRIORITY,
        get_capital_adaptive_universe,
        is_adaptive_1k_mode,
    )
except Exception:
    MICRO_CAPITAL_PRICE_SOFT_CAP = 700.0
    MICRO_CAPITAL_PRIORITY = []
    get_capital_adaptive_universe = None
    is_adaptive_1k_mode = None


SCAN_LIMIT = 50
STALE_CACHE_MAX_AGE_HOURS = 24
SELECTION_STATE_FILE = os.path.join("data", "scan_selection_state.json")
LAST_LOAD_DEBUG = {}


def get_last_load_debug():
    return dict(LAST_LOAD_DEBUG)


def _clean_stock_df(df):
    if df is None or df.empty:
        return None

    df = df.copy()
    df.columns = [str(col).strip() for col in df.columns]

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    required_cols = [col for col in ["Close", "Volume"] if col in df.columns]

    if required_cols:
        df = df.dropna(subset=required_cols)

    if df.empty:
        return None

    return df


def _symbol_key(symbol):
    return str(symbol).replace(".NS", "").upper().strip()


def _latest_close(df):
    try:
        return float(df["Close"].iloc[-1])
    except Exception:
        return 0.0


def _file_age_hours(path):
    try:
        modified = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc)
        return (datetime.now(timezone.utc) - modified).total_seconds() / 3600.0
    except Exception:
        return None


def _selection_hash(symbols):
    stable = "|".join(sorted(str(symbol) for symbol in symbols))
    return hashlib.sha1(stable.encode("utf-8")).hexdigest()[:12]


def _load_previous_selection_hash():
    try:
        if not os.path.exists(SELECTION_STATE_FILE):
            return None
        with open(SELECTION_STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        return state.get("selected_set_hash")
    except Exception:
        return None


def _save_selection_state(selected_symbols, selected_set_hash):
    try:
        os.makedirs(os.path.dirname(SELECTION_STATE_FILE), exist_ok=True)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "selected_set_hash": selected_set_hash,
            "selected_symbols_count": len(selected_symbols),
            "selected_symbols": selected_symbols,
        }
        with open(SELECTION_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        pass


def _select_micro_capital_symbols(all_stock_data, limit):
    available = set(all_stock_data.keys())
    selected = []
    seen = set()

    def add(symbol):
        clean = _symbol_key(symbol)
        if clean in available and clean not in seen:
            selected.append(clean)
            seen.add(clean)

    for symbol in MICRO_CAPITAL_PRIORITY:
        add(symbol)

    affordable = [
        symbol for symbol, df in all_stock_data.items()
        if symbol not in seen and 0 < _latest_close(df) <= MICRO_CAPITAL_PRICE_SOFT_CAP
    ]

    universe = get_capital_adaptive_universe() if get_capital_adaptive_universe else []
    adaptive_affordable = [
        _symbol_key(symbol)
        for symbol in universe
        if (
            _symbol_key(symbol) in available
            and _symbol_key(symbol) not in seen
            and 0 < _latest_close(all_stock_data[_symbol_key(symbol)]) <= MICRO_CAPITAL_PRICE_SOFT_CAP
        )
    ]

    rotating_pool = []
    rotating_seen = set()
    for symbol in affordable + adaptive_affordable:
        clean = _symbol_key(symbol)
        if clean not in seen and clean not in rotating_seen:
            rotating_pool.append(clean)
            rotating_seen.add(clean)

    random.shuffle(rotating_pool)
    for symbol in rotating_pool:
        add(symbol)
        if len(selected) >= limit:
            return selected[:limit]

    expensive = [symbol for symbol in available if symbol not in seen]
    random.shuffle(expensive)
    for symbol in expensive:
        add(symbol)

    return selected[:limit]


def load_cached_stock_data(symbol=None, limit=SCAN_LIMIT):
    """
    TITAN cached data loader.

    Supports BOTH usages:

    1) Single stock mode:
       load_cached_stock_data("RELIANCE.NS")

    2) Dynamic scan mode:
       load_cached_stock_data(limit=50)
       load_cached_stock_data()

    This fixes:
    TypeError: '<=' not supported between instances of 'int' and 'str'
    """

    cache_dir = "data/cache"

    if not os.path.exists(cache_dir):
        print("No cache folder found. Run main.py first to download data.")
        return None if symbol else {}

    # ✅ SINGLE STOCK MODE
    if isinstance(symbol, str) and symbol.strip():
        symbol = symbol.strip()

        possible_files = [
            f"{symbol}.csv",
            f"{symbol.replace('.NS', '')}.csv",
        ]

        for file_name in possible_files:
            path = os.path.join(cache_dir, file_name)

            if os.path.exists(path):
                try:
                    df = pd.read_csv(path)
                    return _clean_stock_df(df)
                except Exception as e:
                    print(f"Error loading {file_name}: {e}")
                    return None

        return None

    # ✅ DYNAMIC MULTI-STOCK MODE
    try:
        limit = int(limit)
    except Exception:
        limit = SCAN_LIMIT

    all_stock_data = {}
    cache_debug = {}
    stale_symbols = []

    for file in os.listdir(cache_dir):
        if not file.endswith(".csv"):
            continue

        stock_name = file.replace(".csv", "")
        path = os.path.join(cache_dir, file)

        try:
            age_hours = _file_age_hours(path)
            df = pd.read_csv(path)
            df = _clean_stock_df(df)

            if df is not None and not df.empty:
                all_stock_data[stock_name] = df
                is_stale = age_hours is not None and age_hours > STALE_CACHE_MAX_AGE_HOURS
                cache_debug[stock_name] = {
                    "cache_age_hours": round(age_hours, 2) if age_hours is not None else None,
                    "cache_stale": is_stale,
                }
                if is_stale:
                    stale_symbols.append(stock_name)

        except Exception as e:
            print(f"Error loading {file}: {e}")

    all_symbols = list(all_stock_data.keys())

    if is_adaptive_1k_mode is not None and is_adaptive_1k_mode():
        selected_symbols = _select_micro_capital_symbols(all_stock_data, limit)
    elif len(all_symbols) <= limit:
        selected_symbols = all_symbols
    else:
        selected_symbols = random.sample(all_symbols, limit)

    selected_set_hash = _selection_hash(selected_symbols)
    previous_set_hash = _load_previous_selection_hash()
    repeated_selection_warning = previous_set_hash == selected_set_hash
    selected_stale_symbols = [
        symbol for symbol in selected_symbols
        if cache_debug.get(symbol, {}).get("cache_stale")
    ]

    global LAST_LOAD_DEBUG
    LAST_LOAD_DEBUG = {
        "selected_set_hash": selected_set_hash,
        "selected_symbols_count": len(selected_symbols),
        "repeated_selection_warning": repeated_selection_warning,
        "stale_cache_count": len(selected_stale_symbols),
        "stale_cache_symbols": selected_stale_symbols,
        "cache_debug": cache_debug,
    }
    _save_selection_state(selected_symbols, selected_set_hash)

    print("DYNAMIC MODE ACTIVE")
    print(f"Total cached stocks: {len(all_symbols)}")
    print(f"Selected for this scan: {len(selected_symbols)}")
    print(f"Selected set hash: {selected_set_hash}")
    print(f"Repeated selection warning: {repeated_selection_warning}")
    if selected_stale_symbols:
        print(
            f"WARNING: stale OHLC cache files in selected scan: "
            f"{len(selected_stale_symbols)} older than {STALE_CACHE_MAX_AGE_HOURS}h"
        )
    print(f"Selected stocks: {selected_symbols}")

    return {
        selected_symbol: all_stock_data[selected_symbol]
        for selected_symbol in selected_symbols
    }
