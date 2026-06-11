"""
Legacy Upstox OAuth auth for account/broker APIs.

Do not use this module for scanner, quote, OHLC, LTP, or other market-data
paths. Market data must use data.upstox_auth and UPSTOX_ANALYTICS_TOKEN.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv


load_dotenv()

try:
    from config.api_keys import UPSTOX_ACCESS_TOKEN as CONFIG_UPSTOX_ACCESS_TOKEN
except Exception:
    CONFIG_UPSTOX_ACCESS_TOKEN = None


def get_upstox_token():
    token_sources = [
        ("UPSTOX_EXTENDED_TOKEN", "EXTENDED_TOKEN"),
        ("UPSTOX_ACCESS_TOKEN", "ACCESS_TOKEN"),
    ]

    for env_key, token_type in token_sources:
        token = os.getenv(env_key)
        if token and str(token).strip():
            return str(token).strip(), token_type

    if CONFIG_UPSTOX_ACCESS_TOKEN and str(CONFIG_UPSTOX_ACCESS_TOKEN).strip():
        return str(CONFIG_UPSTOX_ACCESS_TOKEN).strip(), "ACCESS_TOKEN"

    return None, "MISSING"
