import os
import pandas as pd


def load_cached_stock_data():
    cache_dir = "data/cache"
    stock_data = {}

    if not os.path.exists(cache_dir):
        print("No cache folder found. Run main.py first to download data.")
        return stock_data

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

            stock_data[stock_name] = df

        except Exception as e:
            print(f"Error loading {file}: {e}")

    return stock_data