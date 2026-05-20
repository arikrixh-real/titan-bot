import json
import os
import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
RUNTIME_MODE_STATUS_PATH = Path("data") / "runtime" / "runtime_mode_status.json"
MARKET_OPEN_TIME = time(9, 20)
MARKET_CLOSE_TIME = time(15, 20)
ALLOW_RESEARCH_DURING_MARKET_ENV = "TITAN_ALLOW_RESEARCH_DURING_MARKET"
MASTER_BRAIN_MODE_ENV = "TITAN_RUNTIME_MASTER_BRAIN_MODE"
SAFE_MASTER_BRAIN_MODES = {"READ_ONLY", "HEALTH"}

ALWAYS_ON_TASKS = {
    "heartbeat",
    "runtime_status",
    "broker_health_check",
    "risk_watchdog",
    "live_price_monitor",
    "consciousness_core",
    "report_aggregator",
    "runtime_snapshot_logger",
    "dashboard_sync",
    "worker_health_monitor",
}

MARKET_MODE_TASKS = {
    "master_brain",
    "scanner",
    "setup_engine",
    "market_regime_update",
    "sector_strength",
    "market_pressure_check",
    "volatility_check",
    "news_pulse",
    "light_news_pulse",
    "outcome_tracker",
    "journal",
    "paper_engine",
    "pnl_refresh",
}

RESEARCH_MODE_TASKS = {
    "knowledge_vault_runner",
    "experience_vault_runner",
    "sandbox_evolution",
    "strategy_genome_evolution",
    "recursive_meta_learning",
    "autonomous_research_scientist",
    "deep_causal_reasoning",
    "world_model_expansion",
    "belief_validation",
    "paper_testing_ecosystem",
    "promotion_gate",
    "experience_clustering",
    "confidence_recalibration",
    "daily_review",
    "learning_engine",
    "experience_memory",
    "scenario_simulation",
    "next_day_preparation",
    "memory_compression",
    "historical_replay",
    "backtesting",
    "synthetic_simulation",
    "replay_batch",
    "weekly_report",
}


def _now_ist(value=None):
    if value is None:
        return datetime.now(IST)

    if value.tzinfo is None:
        return value.replace(tzinfo=IST)

    return value.astimezone(IST)


def _is_trading_day(value):
    return value.weekday() < 5


def _market_window_for(day):
    open_at = datetime.combine(day.date(), MARKET_OPEN_TIME, tzinfo=IST)
    close_at = datetime.combine(day.date(), MARKET_CLOSE_TIME, tzinfo=IST)
    return open_at, close_at


def _next_trading_day_start(value):
    candidate = value
    while True:
        if _is_trading_day(candidate):
            open_at, close_at = _market_window_for(candidate)
            if value <= close_at:
                return open_at, close_at
        candidate = datetime.combine(
            (candidate + timedelta(days=1)).date(),
            MARKET_OPEN_TIME,
            tzinfo=IST,
        )


def _allow_research_during_market():
    return os.getenv(ALLOW_RESEARCH_DURING_MARKET_ENV) == "1"


def _safe_master_brain_advisory_mode_enabled():
    raw_mode = os.environ.get(MASTER_BRAIN_MODE_ENV)
    if raw_mode is None:
        return False

    return str(raw_mode).strip().upper() in SAFE_MASTER_BRAIN_MODES


def _atomic_write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as temp_file:
            json.dump(payload, temp_file, indent=2, sort_keys=True)
            temp_file.write("\n")
            temp_path = Path(temp_file.name)

        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def is_market_open_now():
    now = _now_ist()
    open_at, close_at = _market_window_for(now)
    return _is_trading_day(now) and open_at <= now <= close_at


def is_research_mode_now():
    return not is_market_open_now()


def get_runtime_mode():
    if is_market_open_now():
        return "MARKET_MODE"
    return "RESEARCH_MODE"


def should_run_task(task_name):
    task = str(task_name or "").strip()

    if task in ALWAYS_ON_TASKS:
        runtime_mode_snapshot()
        return True

    current_mode = get_runtime_mode()
    if task in MARKET_MODE_TASKS:
        allowed = current_mode == "MARKET_MODE"
        if task == "master_brain" and not allowed:
            allowed = _safe_master_brain_advisory_mode_enabled()
        runtime_mode_snapshot()
        return allowed

    if task in RESEARCH_MODE_TASKS or task not in MARKET_MODE_TASKS:
        allowed = current_mode == "RESEARCH_MODE" or _allow_research_during_market()
        runtime_mode_snapshot()
        return allowed

    runtime_mode_snapshot()
    return False


def runtime_mode_snapshot():
    now = _now_ist()
    is_market_open = is_market_open_now()
    current_mode = "MARKET_MODE" if is_market_open else "RESEARCH_MODE"

    if is_market_open:
        current_open, current_close = _market_window_for(now)
        next_market_open = current_open
        next_market_close = current_close
    else:
        next_market_open, next_market_close = _next_trading_day_start(now)

    payload = {
        "generated_at": now.isoformat(),
        "current_mode": current_mode,
        "is_market_open": is_market_open,
        "is_research_mode": not is_market_open,
        "next_market_open": next_market_open.isoformat(),
        "next_market_close": next_market_close.isoformat(),
        "market_window": "Monday-Friday 09:20-15:20 IST",
        "timezone": "Asia/Kolkata",
        "allow_research_during_market": _allow_research_during_market(),
    }
    _atomic_write_json(RUNTIME_MODE_STATUS_PATH, payload)
    return payload
