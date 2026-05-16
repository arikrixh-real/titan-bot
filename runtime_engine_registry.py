from runtime_heartbeat import write_heartbeat
from runtime_dashboard_sync import run_dashboard_sync
from runtime_news_pulse import run_news_pulse
from runtime_outcome_tracker import run_outcome_tracker
from runtime_live_price_monitor import run_live_price_monitor
from runtime_journal import run_journal
from runtime_risk_watchdog import run_risk_watchdog
from runtime_status import write_runtime_status
from runtime_scanner import run_scanner
from runtime_setup_engine import run_setup_engine
from runtime_master_brain import run_master_brain
from runtime_evolution_engine import run_evolution_engine
from runtime_historical_replay import run_historical_replay
from runtime_backtesting import run_backtesting
from runtime_synthetic_simulation import run_synthetic_simulation
from runtime_memory_compression import run_memory_compression
from runtime_weekly_report import run_weekly_report


def get_engine_registry():
    return {
        "heartbeat": write_heartbeat,
        "dashboard_sync": run_dashboard_sync,
        "news_pulse": run_news_pulse,
        "light_news_pulse": run_news_pulse,
        "outcome_tracker": run_outcome_tracker,
        "live_price_monitor": run_live_price_monitor,
        "journal": run_journal,
        "risk_watchdog": run_risk_watchdog,
        "runtime_status": write_runtime_status,
        "scanner": run_scanner,
        "setup_engine": run_setup_engine,
        "master_brain": run_master_brain,
        "evolution_engine": run_evolution_engine,
        "historical_replay": run_historical_replay,
        "backtesting": run_backtesting,
        "synthetic_simulation": run_synthetic_simulation,
        "memory_compression": run_memory_compression,
        "weekly_report": run_weekly_report,
    }


def get_registered_handler(task_name):
    return get_engine_registry().get(task_name)


if __name__ == "__main__":
    print(list(get_engine_registry().keys()))
