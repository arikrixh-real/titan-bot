import json
import os
import tempfile
from pathlib import Path

from runtime_safe_json import safe_atomic_write_json
from .vault_paths import BELIEFS_PATH, KNOWLEDGE_MEMORY_PATH, PROCESSED_INDEX_PATH, RESEARCH_IDEAS_PATH


def atomic_write_json(path, payload):
    safe_atomic_write_json(path, payload, ensure_ascii=True)


def load_json(path, default):
    try:
        with Path(path).open("r", encoding="utf-8") as source_file:
            payload = json.load(source_file)
        return payload if isinstance(payload, type(default)) else default
    except Exception:
        return default


def load_processed_index():
    return load_json(PROCESSED_INDEX_PATH, {"files": {}, "chunks": {}, "last_run": None})


def save_processed_index(index):
    atomic_write_json(PROCESSED_INDEX_PATH, index)


def load_memory():
    return load_json(KNOWLEDGE_MEMORY_PATH, [])


def save_memory(memory):
    atomic_write_json(KNOWLEDGE_MEMORY_PATH, memory)


def load_beliefs():
    return load_json(BELIEFS_PATH, [])


def save_beliefs(beliefs):
    atomic_write_json(BELIEFS_PATH, beliefs)


def load_research_ideas():
    return load_json(RESEARCH_IDEAS_PATH, [])


def save_research_ideas(ideas):
    atomic_write_json(RESEARCH_IDEAS_PATH, ideas)
