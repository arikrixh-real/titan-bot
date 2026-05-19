import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


IST = timezone(timedelta(hours=5, minutes=30))
STATE_VERSION = 1
INTELLIGENCE_STATE_DIR = Path("data") / "runtime" / "intelligence_state"


def now_ist():
    return datetime.now(IST).isoformat()


def state_path_for_task(task):
    return INTELLIGENCE_STATE_DIR / f"{task}.json"


def default_intelligence_state(task):
    now = now_ist()
    return {
        "task": task,
        "state_version": STATE_VERSION,
        "created_at": now,
        "updated_at": now,
        "run_count": 0,
        "last_status": "NEW",
        "last_error": None,
        "cumulative_runtime_seconds": 0.0,
        "memory_cursor": None,
        "learning_cursor": None,
        "evolution_generation": 0,
        "last_input_hash": None,
        "last_output_hash": None,
        "notes": [],
    }


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


def _stable_hash(payload):
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ensure_intelligence_state(task):
    path = state_path_for_task(task)

    try:
        with path.open("r", encoding="utf-8") as state_file:
            state = json.load(state_file)
        if not isinstance(state, dict):
            raise ValueError("state payload is not an object")
    except FileNotFoundError:
        state = default_intelligence_state(task)
        _atomic_write_json(path, state)
        print(f"INTELLIGENCE_STATE_SAVE task={task} path={path}", flush=True)
    except Exception as exc:
        print(
            f"INTELLIGENCE_STATE_ERROR task={task} path={path} error={exc}",
            flush=True,
        )
        state = default_intelligence_state(task)
        state["last_status"] = "RESET_CORRUPT"
        state["last_error"] = f"corrupt state reset: {exc}"
        _atomic_write_json(path, state)
        print(f"INTELLIGENCE_STATE_SAVE task={task} path={path}", flush=True)

    for key, value in default_intelligence_state(task).items():
        state.setdefault(key, value)
    state["task"] = task
    state["state_version"] = STATE_VERSION

    print(f"INTELLIGENCE_STATE_LOAD task={task} path={path}", flush=True)
    return state, path


def save_intelligence_state(task, state, status, runtime_seconds, error=None):
    path = state_path_for_task(task)
    if error is not None:
        print(
            f"INTELLIGENCE_STATE_ERROR task={task} path={path} error={error}",
            flush=True,
        )

    next_state = dict(state)
    next_state["task"] = task
    next_state["state_version"] = STATE_VERSION
    next_state.setdefault("created_at", now_ist())
    next_state["updated_at"] = now_ist()
    next_state["last_status"] = status
    next_state["last_error"] = None if error is None else str(error)
    next_state["cumulative_runtime_seconds"] = float(
        next_state.get("cumulative_runtime_seconds") or 0.0
    ) + float(runtime_seconds or 0.0)
    next_state["last_output_hash"] = _stable_hash(next_state)

    if status == "OK":
        next_state["run_count"] = int(next_state.get("run_count") or 0) + 1

    _atomic_write_json(path, next_state)
    print(f"INTELLIGENCE_STATE_SAVE task={task} path={path}", flush=True)
    return next_state, path


def state_hash(state):
    return _stable_hash(state)
