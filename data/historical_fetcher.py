import yfinance as yf
import pandas as pd
import os

from config.universe import NSE_STOCKS
from config.settings import DATA_PERIOD, DATA_INTERVAL


def fetch_and_save_all_data():
    os.makedirs("data/cache", exist_ok=True)

    for stock in NSE_STOCKS:
        try:
            print(f"Fetching {stock}...")
            df = yf.download(stock, period=DATA_PERIOD, interval=DATA_INTERVAL, progress=False)

            if df.empty:
                print(f"No data for {stock}")
                continue

            file_name = stock.replace(".NS", "") + ".csv"
            save_path = os.path.join("data/cache", file_name)
            df.to_csv(save_path)

            print(f"Saved -> {save_path}")

        except Exception as e:
            print(f"Error fetching {stock}: {e}")


if __name__ == "__main__":
    fetch_and_save_all_data()