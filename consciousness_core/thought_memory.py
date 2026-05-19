import json
from pathlib import Path

from consciousness_core.state import now_ist


BASE_DIR = Path("data") / "consciousness_core"
THOUGHT_MEMORY_PATH = BASE_DIR / "thought_memory.jsonl"
REFLECTION_LOG_PATH = BASE_DIR / "reflection_log.jsonl"
INTERNAL_NARRATIVE_PATH = BASE_DIR / "internal_narrative.jsonl"


def append_jsonl(path, event):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(event)
    payload.setdefault("created_at", now_ist())
    with path.open("a", encoding="utf-8") as memory_file:
        memory_file.write(json.dumps(payload, sort_keys=True, default=str))
        memory_file.write("\n")


def append_thought(event):
    append_jsonl(THOUGHT_MEMORY_PATH, event)


def append_reflection(event):
    append_jsonl(REFLECTION_LOG_PATH, event)


def append_internal_narrative(event):
    append_jsonl(INTERNAL_NARRATIVE_PATH, event)

