import os
import random
import pandas as pd


SCAN_LIMIT = 50


def load_cached_stock_data(limit=SCAN_LIMIT):
    cache_dir = "data/cache"
    all_stock_data = {}

    if not os.path.exists(cache_dir):
        print("No cache folder found. Run main.py first to download data.")
        return {}

    for file in os.listdir(cache_dir):
        if not file.endswith(".csv"):
            continue

        stock_name = file.replace(".csv", "")
        path = os.path.join(cache_dir, file)

        try:
            df = pd.read_csv(path)

            if df.empty:
                continue

            df.columns = [str(col).strip() for col in df.columns]

            for col in ["Open", "High", "Low", "Close", "Volume"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            df = df.dropna(subset=["Close", "Volume"])

            if not df.empty:
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
        symbol: all_stock_data[symbol]
        for symbol in selected_symbols
    }