import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


IST = timezone(timedelta(hours=5, minutes=30))
STATE_VERSION = 1
DEFAULT_STATE_PATH = Path("data") / "consciousness_core" / "state.json"


def now_ist():
    return datetime.now(IST).isoformat()


def atomic_write_json(path, payload):
    path = Path(path)
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
            json.dump(payload, temp_file, indent=2, sort_keys=True, default=str)
            temp_file.write("\n")
            temp_path = Path(temp_file.name)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def stable_hash(payload):
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _default_state():
    now = now_ist()
    return {
        "state_version": STATE_VERSION,
        "created_at": now,
        "updated_at": now,
        "run_count": 0,
        "consciousness_cycle": 0,
        "current_mode": "OBSERVE_REFLECT_PROPOSE",
        "current_focus": "system continuity",
        "last_status": "NEW",
        "last_error": None,
        "cumulative_runtime_seconds": 0.0,
        "memory_cursor": 0,
        "thought_cursor": 0,
        "belief_generation": 0,
        "evolution_generation": 0,
        "last_observation_hash": None,
        "last_output_hash": None,
        "active_goals": [],
        "open_questions": [],
        "active_weaknesses": [],
        "latest_summary": "",
    }


def _resolve_state_path(state_path=None):
    if not state_path:
        return DEFAULT_STATE_PATH
    path = Path(state_path)
    if "intelligence_state" in path.parts:
        return DEFAULT_STATE_PATH
    return path


def load_state(state_path=None):
    path = _resolve_state_path(state_path)
    try:
        with path.open("r", encoding="utf-8") as state_file:
            state = json.load(state_file)
        if not isinstance(state, dict):
            raise ValueError("state payload is not an object")
    except FileNotFoundError:
        state = _default_state()
        atomic_write_json(path, state)
    except Exception as exc:
        state = _default_state()
        state["last_status"] = "RESET_CORRUPT"
        state["last_error"] = f"corrupt state reset: {exc}"
        atomic_write_json(path, state)

    for key, value in _default_state().items():
        state.setdefault(key, value)
    state["state_version"] = STATE_VERSION
    return state, path


def save_state(state, state_path=None):
    path = _resolve_state_path(state_path)
    next_state = dict(state)
    next_state["state_version"] = STATE_VERSION
    next_state.setdefault("created_at", now_ist())
    next_state["updated_at"] = now_ist()
    next_state["last_output_hash"] = stable_hash(next_state)
    atomic_write_json(path, next_state)
    return next_state

