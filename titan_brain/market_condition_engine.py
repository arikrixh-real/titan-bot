from titan_brain.supabase_client import supabase
from engines.market_filter import market_regime_status


def store_market_condition():
    """
    Stores current market condition into Supabase.
    Compatible with market_conditions table schema.
    """

    try:
        market_status = market_regime_status()

        if not market_status:
            print("[MARKET MEMORY] Market status unavailable")
            return None

        direction = market_status.get("direction", "NEUTRAL")
        regime = market_status.get("regime", market_status.get("status", "UNKNOWN"))
        volatility = market_status.get("volatility", "UNKNOWN")

        data = {
            "market_name": "INDIAN_MARKET",
            "regime": regime,
            "direction": direction,
            "volatility": volatility,
            "nifty_trend": market_status.get("nifty_trend", direction),
            "banknifty_trend": market_status.get("banknifty_trend", "UNKNOWN"),
            "vix_value": market_status.get("vix_value", None),
            "notes": "Auto stored by TITAN market condition engine",
            "raw_data": market_status
        }

        supabase.table("market_conditions").insert(data).execute()

        print(f"📊 Market condition stored: {direction} / {regime}")
        return data

    except Exception as e:
        print(f"[MARKET CONDITION ERROR] {e}")
        return None