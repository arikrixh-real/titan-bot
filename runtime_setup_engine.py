import json
from pathlib import Path

from runtime_engine_health import (
    atomic_write_json,
    build_setup_engine_runtime_health,
    enrich_setup_engine_payload,
)
from runtime_fallback_resolver import apply_off_hours_runtime_continuity
from engines.time_filter import current_bot_mode
from utils.market_hours import as_ist_datetime, is_trade_window


SETUP_ENGINE_STATUS_PATH = Path("data") / "runtime" / "setup_engine_status.json"


def run_setup_engine():
    now_ist = as_ist_datetime()
    payload = {
        "generated_at": now_ist.isoformat(),
        "timestamp_ist": now_ist.isoformat(),
        "mode": current_bot_mode(now_ist),
        "status": "DIAGNOSTIC_SKIPPED",
        "setup_engine_status": "DIAGNOSTIC_SKIPPED",
        "setup_engine_connection": "DIAGNOSTIC_SKIPPED",
        "reason": "setup_generation_intentionally_skipped_for_runtime_proof",
        "off_hours_runtime_continuity": not is_trade_window(now_ist),
        "setup_engine_research_freshness": "OFF_HOURS_STANDBY" if not is_trade_window(now_ist) else None,
        "engine_contract": "runtime marker only; does not call scan_for_setups",
        "marker_only": True,
        "real_setup_engine_called": False,
        "actual_setup_generation": False,
        "trade_creation": False,
        "telegram_alerts": False,
        "journal_writes": False,
        "supabase_writes": False,
        "broker_orders": False,
        "live_execution_enabled": False,
        "affects_execution": False,
        "affects_live_ranking": False,
        "alert_generation": False,
        "broker_mutation": False,
    }
    payload = enrich_setup_engine_payload(payload, now=now_ist)

    atomic_write_json(SETUP_ENGINE_STATUS_PATH, payload)
    setup_health = build_setup_engine_runtime_health(status_payload=payload)
    apply_off_hours_runtime_continuity({}, setup_health, now=now_ist, write=True, require_daemon=False)
    return payload


if __name__ == "__main__":
    run_setup_engine()
