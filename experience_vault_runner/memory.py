from .io_utils import atomic_write_json, load_json
from .vault_paths import (
    CONFIDENCE_LESSONS_PATH,
    FAILURE_PATTERN_MEMORY_PATH,
    IMPORTED_EXPERIENCE_MEMORY_PATH,
    NO_TRADE_MEMORY_PATH,
    PROCESSED_INDEX_PATH,
    SETUP_RELIABILITY_MEMORY_PATH,
    STOCK_PERSONALITY_MEMORY_PATH,
)


def load_processed_index():
    return load_json(PROCESSED_INDEX_PATH, {"files": {}, "chunks": {}, "last_run": None})


def save_processed_index(index):
    atomic_write_json(PROCESSED_INDEX_PATH, index)


def load_imported_memory():
    return load_json(IMPORTED_EXPERIENCE_MEMORY_PATH, [])


def save_imported_memory(memory):
    atomic_write_json(IMPORTED_EXPERIENCE_MEMORY_PATH, memory)


def write_derived_memories(memory):
    setup = [item for item in memory if item.get("lesson_type") in {"setup_type", "trade_result", "entry_reason"}]
    stock = [item for item in memory if item.get("lesson_type") == "stock_behavior"]
    failure = [item for item in memory if item.get("lesson_type") in {"failure_success_reason", "trap_evidence"}]
    no_trade = [item for item in memory if item.get("lesson_type") == "no_trade_lesson"]
    confidence = [item for item in memory if item.get("lesson_type") == "confidence_lesson"]

    atomic_write_json(SETUP_RELIABILITY_MEMORY_PATH, setup)
    atomic_write_json(STOCK_PERSONALITY_MEMORY_PATH, stock)
    atomic_write_json(FAILURE_PATTERN_MEMORY_PATH, failure)
    atomic_write_json(NO_TRADE_MEMORY_PATH, no_trade)
    atomic_write_json(CONFIDENCE_LESSONS_PATH, confidence)

