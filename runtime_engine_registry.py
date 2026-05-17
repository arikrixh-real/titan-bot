from runtime_heartbeat import write_heartbeat
from runtime_news_pulse import run_news_pulse
from runtime_outcome_tracker import run_outcome_tracker
from runtime_live_price_monitor import run_live_price_monitor
from runtime_risk_watchdog import run_risk_watchdog
from runtime_status import write_runtime_status
from runtime_setup_engine import run_setup_engine
from runtime_evolution_engine import run_evolution_engine
from runtime_historical_replay import run_historical_replay
from runtime_backtesting import run_backtesting
from runtime_synthetic_simulation import run_synthetic_simulation
from runtime_memory_compression import run_memory_compression
from runtime_weekly_report import run_weekly_report
from runtime_dashboard_sync import run_dashboard_sync
from runtime_scanner import run_scanner
from runtime_journal import run_journal
from runtime_master_brain import run_master_brain
from runtime_volatility_check import run_volatility_check
from runtime_broker_health_check import run_broker_health_check
from runtime_pnl_refresh import run_pnl_refresh
from runtime_market_pressure_check import run_market_pressure_check
from runtime_market_regime_update import run_market_regime_update
from runtime_sector_strength import run_sector_strength


def get_engine_registry():
    return {
        "heartbeat": write_heartbeat,
        "news_pulse": run_news_pulse,
        "light_news_pulse": run_news_pulse,
        "outcome_tracker": run_outcome_tracker,
        "live_price_monitor": run_live_price_monitor,
        "risk_watchdog": run_risk_watchdog,
        "runtime_status": write_runtime_status,
        "setup_engine": run_setup_engine,
        "evolution_engine": run_evolution_engine,
        "historical_replay": run_historical_replay,
        "backtesting": run_backtesting,
        "synthetic_simulation": run_synthetic_simulation,
        "memory_compression": run_memory_compression,
        "weekly_report": run_weekly_report,
        "dashboard_sync": run_dashboard_sync,
        "scanner": run_scanner,
        "journal": run_journal,
        "master_brain": run_master_brain,
        "volatility_check": run_volatility_check,
        "broker_health_check": run_broker_health_check,
        "pnl_refresh": run_pnl_refresh,
        "market_pressure_check": run_market_pressure_check,
        "market_regime_update": run_market_regime_update,
        "sector_strength": run_sector_strength,
    }


def get_registered_handler(task_name):
    return get_engine_registry().get(task_name)


if __name__ == "__main__":
    print(list(get_engine_registry().keys()))
