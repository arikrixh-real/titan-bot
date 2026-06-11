"""Locked configuration for the isolated HFT mode foundation."""

from pathlib import Path

HFT_ENABLED = False
MODE = "SIMULATION_ONLY"
BROKER_ALLOWED = False
TELEGRAM_ALLOWED = False
CLASSIC_MEMORY_WRITE_ALLOWED = False
CLASSIC_JOURNAL_WRITE_ALLOWED = False
MASTER_BRAIN_ACCESS_ALLOWED = False
TITAN_EVOLUTION_WRITE_ALLOWED = False
ACTIVE_RUNTIME_CONNECTION_ALLOWED = False

REPO_ROOT = Path(__file__).resolve().parents[1]
HFT_DATA_DIR = REPO_ROOT / "data" / "hft_mode"

HFT_DATA_FILES = {
    "runtime_state": "hft_runtime_state.json",
    "health": "hft_health.json",
    "stats": "hft_stats.json",
    "active_trades": "hft_active_trades.json",
    "closed_summary": "hft_closed_summary.json",
    "outcomes": "hft_outcomes.json",
    "daily_pnl": "hft_daily_pnl.json",
    "rejected_count": "hft_rejected_count.json",
    "safety_proof": "hft_safety_proof.json",
}

SAFETY_RULES = {
    "live_trades": False,
    "broker_calls": BROKER_ALLOWED,
    "telegram_messages": TELEGRAM_ALLOWED,
    "classic_journal_writes": CLASSIC_JOURNAL_WRITE_ALLOWED,
    "titan_memory_writes": CLASSIC_MEMORY_WRITE_ALLOWED,
    "titan_evolution_writes": TITAN_EVOLUTION_WRITE_ALLOWED,
    "master_brain_access": MASTER_BRAIN_ACCESS_ALLOWED,
    "runtime_connection": ACTIVE_RUNTIME_CONNECTION_ALLOWED,
    "write_scope": "data/hft_mode",
}
