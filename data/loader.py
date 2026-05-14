import os
import random
import pandas as pd

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
    affordable.sort(key=lambda symbol: (_latest_close(all_stock_data[symbol]), symbol))
    for symbol in affordable:
        add(symbol)

    universe = get_capital_adaptive_universe() if get_capital_adaptive_universe else []
    for symbol in universe:
        add(symbol)

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

    for file in os.listdir(cache_dir):
        if not file.endswith(".csv"):
            continue

        stock_name = file.replace(".csv", "")
        path = os.path.join(cache_dir, file)

        try:
            df = pd.read_csv(path)
            df = _clean_stock_df(df)

            if df is not None and not df.empty:
                all_stock_data[stock_name] = df

        except Exception as e:
            print(f"Error loading {file}: {e}")

    all_symbols = list(all_stock_data.keys())

    if is_adaptive_1k_mode is not None and is_adaptive_1k_mode():
        selected_symbols = _select_micro_capital_symbols(all_stock_data, limit)
    elif len(all_symbols) <= limit:
        selected_symbols = all_symbols
    else:
        selected_symbols = random.sample(all_symbols, limit)

    print("DYNAMIC MODE ACTIVE")
    print(f"Total cached stocks: {len(all_symbols)}")
    print(f"Selected for this scan: {len(selected_symbols)}")
    print(f"Selected stocks: {selected_symbols}")

    return {
        selected_symbol: all_stock_data[selected_symbol]
        for selected_symbol in selected_symbols
    }
