from pathlib import Path


VAULT_ROOT = Path("data") / "experience_vault"

SOURCE_FOLDERS = (
    "market_regimes",
    "stock_personality",
    "setup_reliability",
    "failure_memory",
    "liquidity_traps",
    "manipulation_patterns",
    "news_reactions",
    "time_of_day",
    "sector_rotation",
    "confidence_calibration",
    "no_trade_cases",
    "risk_cases",
    "paper_tests",
    "historical_crisis",
    "psychology",
    "multi_timeframe",
    "pattern_memory",
    "causal_cases",
    "imported_trade_logs",
)

DERIVED_FOLDERS = (
    "reports",
    "memory",
    "metadata",
    "processed",
)

PROCESSED_INDEX_PATH = VAULT_ROOT / "metadata" / "processed_index.json"
IMPORTED_EXPERIENCE_MEMORY_PATH = VAULT_ROOT / "memory" / "imported_experience_memory.json"
SETUP_RELIABILITY_MEMORY_PATH = VAULT_ROOT / "memory" / "setup_reliability_memory.json"
STOCK_PERSONALITY_MEMORY_PATH = VAULT_ROOT / "memory" / "stock_personality_memory.json"
FAILURE_PATTERN_MEMORY_PATH = VAULT_ROOT / "memory" / "failure_pattern_memory.json"
NO_TRADE_MEMORY_PATH = VAULT_ROOT / "memory" / "no_trade_memory.json"
CONFIDENCE_LESSONS_PATH = VAULT_ROOT / "memory" / "confidence_lessons.json"
PACKET_PATH = VAULT_ROOT / "reports" / "external_experience_packet.json"
REPORT_PATH = VAULT_ROOT / "reports" / "latest_experience_report.txt"
EXPERIENCE_INTELLIGENCE_SUMMARY_PATH = VAULT_ROOT / "reports" / "experience_intelligence_summary.json"


def ensure_vault_dirs():
    VAULT_ROOT.mkdir(parents=True, exist_ok=True)
    for folder in SOURCE_FOLDERS + DERIVED_FOLDERS:
        (VAULT_ROOT / folder).mkdir(parents=True, exist_ok=True)


def source_paths():
    ensure_vault_dirs()
    return [VAULT_ROOT / folder for folder in SOURCE_FOLDERS]
