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
        ]
        scheduler_map["every_5_seconds"] = [
            "volatility_check",
            "broker_health_check",
        ]
        scheduler_map["every_10_seconds"] = [
            "pnl_refresh",
        ]
        scheduler_map["every_1_minute"] = [
            "dashboard_sync",
            "news_pulse",
            "sector_strength",
            "runtime_snapshot_logger",
        ]
        scheduler_map["every_5_minutes"] = [
            "live_price_monitor",
            "market_regime_update",
            "market_pressure_check",
            "outcome_tracker",
            "ohlc_refresh",
            "scanner",
            "light_news_pulse",
            "setup_engine",
            "master_brain",
            "journal",
            "paper_engine",
        ]
        scheduler_map["every_15_minutes"] = [
            "report_aggregator",
        ]
        scheduler_map["every_30_minutes"] = [
            "consciousness_core",
            "learning_engine",
            "experience_memory",
            "knowledge_vault_runner",
            "experience_vault_runner",
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
            "scanner",
            "runtime_snapshot_logger",
        ]
        scheduler_map["every_15_minutes"] = [
            "report_aggregator",
        ]
        scheduler_map["every_30_minutes"] = [
            "consciousness_core",
            "learning_engine",
            "experience_memory",
            "memory_compression",
            "knowledge_vault_runner",
            "experience_vault_runner",
        ]
        scheduler_map["every_1_hour"] = [
            "scenario_simulation",
            "next_day_preparation",
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
            "runtime_snapshot_logger",
        ]
        scheduler_map["every_15_minutes"] = [
            "report_aggregator",
        ]
        scheduler_map["every_30_minutes"] = [
            "consciousness_core",
            "memory_compression",
            "knowledge_vault_runner",
            "experience_vault_runner",
        ]
        scheduler_map["every_1_hour"] = [
            "historical_replay",
            "backtesting",
            "synthetic_simulation",
            "evolution_engine",
            "weekly_report",
        ]

    return scheduler_map


if __name__ == "__main__":
    print(get_scheduler_map("WEEKEND_MODE"))
