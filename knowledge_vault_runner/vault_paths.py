from pathlib import Path


VAULT_ROOT = Path("data") / "knowledge_vault"
UPLOAD_FOLDERS = (
    "books",
    "strategies",
    "institutional",
    "market_research",
    "psychology",
    "case_studies",
    "backtests",
    "news_research",
    "notes",
    "screenshots",
)
DERIVED_FOLDERS = (
    "extracted_text",
    "processed",
    "memory",
    "reports",
    "metadata",
)

PROCESSED_INDEX_PATH = VAULT_ROOT / "metadata" / "processed_index.json"
KNOWLEDGE_MEMORY_PATH = VAULT_ROOT / "memory" / "knowledge_memory.json"
BELIEFS_PATH = VAULT_ROOT / "memory" / "beliefs_from_knowledge.json"
RESEARCH_IDEAS_PATH = VAULT_ROOT / "memory" / "research_ideas.json"
PACKET_PATH = VAULT_ROOT / "reports" / "knowledge_to_consciousness_packet.json"
REPORT_PATH = VAULT_ROOT / "reports" / "latest_knowledge_report.txt"


def ensure_vault_dirs():
    VAULT_ROOT.mkdir(parents=True, exist_ok=True)
    for folder in UPLOAD_FOLDERS + DERIVED_FOLDERS:
        (VAULT_ROOT / folder).mkdir(parents=True, exist_ok=True)


def upload_paths():
    ensure_vault_dirs()
    return [VAULT_ROOT / folder for folder in UPLOAD_FOLDERS]

