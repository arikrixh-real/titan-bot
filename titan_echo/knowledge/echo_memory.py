"""Read-only permanent memory access for the ECHO knowledge foundation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from titan_echo.knowledge.common import ECHO_RUNTIME, output_path, write_json


MEMORY_FILES = {
    "memory": output_path("echo_memory.json"),
    "decision_history": output_path("echo_decision_history.jsonl"),
    "mission_history": output_path("echo_mission_history.jsonl"),
    "architecture_history": output_path("echo_architecture_history.jsonl"),
    "learning_memory": output_path("echo_learning_memory.json"),
}


def read_json_file(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}


def read_jsonl_file(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            item = json.loads(text)
        except Exception:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records[-limit:] if limit else records


def initialize_memory_files() -> dict[str, str]:
    ECHO_RUNTIME.mkdir(parents=True, exist_ok=True)
    defaults = {
        MEMORY_FILES["memory"]: {
            "schema": "titan_echo.knowledge.memory.v1",
            "architecture_knowledge": {},
            "decisions": [],
            "mission_summaries": [],
            "discovered_titan_knowledge": {},
            "approved_architecture_rules": [],
            "mode": "read_only_access_first",
        },
        MEMORY_FILES["learning_memory"]: {
            "schema": "titan_echo.knowledge.learning_memory.v1",
            "lessons": [],
            "mode": "read_only_access_first",
        },
    }
    for path, payload in defaults.items():
        if not path.exists():
            write_json(path, payload)
    for path in (MEMORY_FILES["decision_history"], MEMORY_FILES["mission_history"], MEMORY_FILES["architecture_history"]):
        if not path.exists():
            path.write_text("", encoding="utf-8")
    return {name: str(path.relative_to(ECHO_RUNTIME.parents[2])).replace("\\", "/") for name, path in MEMORY_FILES.items()}


def load_echo_memory(limit: int | None = None) -> dict[str, Any]:
    initialize_memory_files()
    return {
        "schema": "titan_echo.knowledge.memory_snapshot.v1",
        "mode": "read_only",
        "files": {name: str(path).replace("\\", "/") for name, path in MEMORY_FILES.items()},
        "memory": read_json_file(MEMORY_FILES["memory"]),
        "decision_history": read_jsonl_file(MEMORY_FILES["decision_history"], limit),
        "mission_history": read_jsonl_file(MEMORY_FILES["mission_history"], limit),
        "architecture_history": read_jsonl_file(MEMORY_FILES["architecture_history"], limit),
        "learning_memory": read_json_file(MEMORY_FILES["learning_memory"]),
    }


def main() -> int:
    files = initialize_memory_files()
    print("ECHO knowledge memory foundation: PASSED")
    for name, path in files.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
