from datetime import datetime, time

from utils.market_hours import IST, TRADE_WINDOW_START, as_ist_datetime, is_trade_window, is_trading_day


def is_premarket(value=None):
    now = datetime.now(IST) if value is None else as_ist_datetime(value)
    if not is_trading_day(now):
        return False

    now = now.time()
    return time(9, 0) <= now < TRADE_WINDOW_START


def is_market_open(value=None):
    return is_trade_window(value)


def current_bot_mode(value=None):
    if is_premarket(value):
        return "PRE_MARKET_MODE"

    if is_market_open(value):
        return "MARKET_MODE"

    if not is_trading_day(value):
        return "WEEKEND_MODE"

    return "INTELLIGENCE_MODE"


def get_mode_permissions(value=None):
    mode = current_bot_mode(value)

    permissions = {
        "PRE_MARKET_MODE": {
            "live_allowed_engines": [
                "live_price_monitor",
                "news_pulse",
                "watchlist_preparation",
            ],
            "research_allowed_engines": [
                "overnight_summary_loader",
                "premarket_bias_builder",
            ],
            "blocked_engines": [
                "telegram_alerts",
                "live_trade_creation",
                "historical_replay",
                "heavy_evolution",
            ],
            "reason": "Pre-market observation window; live market execution is not implied.",
        },
        "MARKET_MODE": {
            "live_allowed_engines": [
                "live_price_monitor",
                "scanner",
                "setup_engine",
                "master_brain",
                "journal",
                "outcome_tracker",
                "telegram_alerts",
                "risk_filter",
            ],
            "research_allowed_engines": [
                "light_news_pulse",
                "light_market_context",
            ],
            "blocked_engines": [
                "historical_replay",
                "deep_backtesting",
                "heavy_evolution",
                "memory_rebuild",
                "strategy_mutation",
            ],
            "reason": "Market window is active; runtime behavior remains controlled elsewhere.",
        },
        "INTELLIGENCE_MODE": {
            "live_allowed_engines": [
                "outcome_tracker",
                "dashboard_sync",
            ],
            "research_allowed_engines": [
                "news_intelligence",
                "daily_review",
                "learning_engine",
                "evolution_engine",
                "scenario_simulation",
                "experience_memory",
                "next_day_preparation",
            ],
            "blocked_engines": [
                "telegram_alerts",
                "live_trade_creation",
            ],
            "reason": "Outside market window on a trading day; intelligence tasks may be observed.",
        },
        "WEEKEND_MODE": {
            "live_allowed_engines": [
                "dashboard_sync",
            ],
            "research_allowed_engines": [
                "historical_replay",
                "backtesting",
                "synthetic_simulation",
                "learning_engine",
                "evolution_engine",
                "memory_compression",
                "weekly_report",
            ],
            "blocked_engines": [
                "telegram_alerts",
                "live_trade_creation",
                "live_scanner",
            ],
            "reason": "Non-trading day; live scanning is not included in observed permissions.",
        },
    }

    mode_permissions = permissions[mode]
    return {
        "mode": mode,
        "live_allowed_engines": mode_permissions["live_allowed_engines"],
        "research_allowed_engines": mode_permissions["research_allowed_engines"],
        "blocked_engines": mode_permissions["blocked_engines"],
        "reason": mode_permissions["reason"],
    }
