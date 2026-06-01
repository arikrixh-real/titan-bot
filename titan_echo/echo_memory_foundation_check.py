"""Validate the TITAN ECHO Phase 1 memory foundation files."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FOLDERS = [
    REPO_ROOT / "titan_echo",
    REPO_ROOT / "data" / "runtime" / "echo",
]

JSON_FILES = [
    REPO_ROOT / "data" / "runtime" / "echo" / "titan_architecture_map.json",
    REPO_ROOT / "data" / "runtime" / "echo" / "titan_module_registry.json",
    REPO_ROOT / "data" / "runtime" / "echo" / "titan_connection_graph.json",
    REPO_ROOT / "data" / "runtime" / "echo" / "titan_roadmap.json",
    REPO_ROOT / "data" / "runtime" / "echo" / "titan_known_risks.json",
]

JSONL_FILES = [
    REPO_ROOT / "data" / "runtime" / "echo" / "echo_memory.jsonl",
    REPO_ROOT / "data" / "runtime" / "echo" / "titan_change_history.jsonl",
    REPO_ROOT / "data" / "runtime" / "echo" / "titan_mission_history.jsonl",
]

OTHER_FILES = [
    REPO_ROOT / "titan_echo" / "README.md",
    REPO_ROOT / "titan_echo" / "echo_memory_foundation_check.py",
]


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def validate_folders() -> list[str]:
    errors: list[str] = []
    for folder in REQUIRED_FOLDERS:
        if not folder.is_dir():
            errors.append(f"Missing folder: {relative(folder)}")
    return errors


def validate_files() -> list[str]:
    errors: list[str] = []
    for path in [*JSON_FILES, *JSONL_FILES, *OTHER_FILES]:
        if not path.is_file():
            errors.append(f"Missing file: {relative(path)}")
    return errors


def validate_json() -> list[str]:
    errors: list[str] = []
    for path in JSON_FILES:
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                json.load(handle)
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid JSON: {relative(path)} line {exc.lineno}")
    return errors


def main() -> int:
    errors = []
    errors.extend(validate_folders())
    errors.extend(validate_files())
    errors.extend(validate_json())

    if errors:
        print("TITAN ECHO foundation check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("TITAN ECHO foundation check: PASSED")
    print(f"Folders checked: {len(REQUIRED_FOLDERS)}")
    print(f"Files checked: {len(JSON_FILES) + len(JSONL_FILES) + len(OTHER_FILES)}")
    print(f"Valid JSON files: {len(JSON_FILES)}")
    print(f"JSONL files present: {len(JSONL_FILES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
