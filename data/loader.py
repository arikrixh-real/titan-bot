import os
import random
import pandas as pd


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

    if len(all_symbols) <= limit:
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