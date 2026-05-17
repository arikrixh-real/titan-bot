"""
Safe interval scheduler map for future TITAN orchestration.

This module defines engine names as strings only. It does not import engines,
start loops, call brokers, or execute runtime logic.
"""


def _empty_scheduler_map():
    return {
        "every_1_second": [],
        "every_5_seconds": [],
        "every_10_seconds": [],
        "every_1_minute": [],
        "every_5_minutes": [],
        "every_15_minutes": [],
        "every_30_minutes": [],
        "every_1_hour": [],
    }


def get_scheduler_map(mode):
    scheduler_map = _empty_scheduler_map()

    if mode == "PRE_MARKET_MODE":
        scheduler_map["every_1_second"] = [
            "heartbeat",
            "runtime_status",
        ]
        scheduler_map["every_10_seconds"] = [
            "premarket_price_context",
            "global_market_check",
        ]
        scheduler_map["every_1_minute"] = [
            "dashboard_sync",
            "news_pulse",
            "premarket_bias_builder",
            "watchlist_preparation",
        ]
        scheduler_map["every_5_minutes"] = [
            "risk_warning_builder",
            "sector_preparation",
        ]

    elif mode == "MARKET_MODE":
        scheduler_map["every_1_second"] = [
            "heartbeat",
            "runtime_status",
            "live_price_monitor",
            "risk_watchdog",
        ]
        scheduler_map["every_5_seconds"] = [
            "volatility_check",
            "broker_health_check",
        ]
        scheduler_map["every_10_seconds"] = [
            "pnl_refresh",
            "market_pressure_check",
        ]
        scheduler_map["every_1_minute"] = [
            "dashboard_sync",
            "market_regime_update",
            "news_pulse",
            "sector_strength",
            "outcome_tracker",
        ]
        scheduler_map["every_5_minutes"] = [
            "scanner",
            "light_news_pulse",
            "setup_engine",
            "master_brain",
            "journal",
            "paper_engine",
        ]

    elif mode == "INTELLIGENCE_MODE":
        scheduler_map["every_1_second"] = [
            "heartbeat",
            "runtime_status",
        ]
        scheduler_map["every_1_minute"] = [
            "dashboard_sync",
            "news_intelligence",
            "daily_review",
        ]
        scheduler_map["every_5_minutes"] = [
            "learning_engine",
            "experience_memory",
        ]
        scheduler_map["every_15_minutes"] = [
            "scenario_simulation",
            "next_day_preparation",
        ]
        scheduler_map["every_30_minutes"] = [
            "evolution_engine",
            "replay_batch",
        ]

    elif mode == "WEEKEND_MODE":
        scheduler_map["every_1_second"] = [
            "heartbeat",
            "runtime_status",
        ]
        scheduler_map["every_1_minute"] = [
            "dashboard_sync",
        ]
        scheduler_map["every_5_minutes"] = [
            "historical_replay",
            "backtesting",
        ]
        scheduler_map["every_15_minutes"] = [
            "synthetic_simulation",
        ]
        scheduler_map["every_30_minutes"] = [
            "evolution_engine",
            "memory_compression",
        ]
        scheduler_map["every_1_hour"] = [
            "weekly_report",
        ]

    return scheduler_map


if __name__ == "__main__":
    print(get_scheduler_map("WEEKEND_MODE"))
