"""Validate the TITAN ECHO read-only architecture mapper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
MAPPER_PATH = REPO_ROOT / "titan_echo" / "echo_architecture_mapper.py"
ECHO_RUNTIME = REPO_ROOT / "data" / "runtime" / "echo"
ARCHITECTURE_MAP_PATH = ECHO_RUNTIME / "titan_architecture_map.json"
MODULE_REGISTRY_PATH = ECHO_RUNTIME / "titan_module_registry.json"
CONNECTION_GRAPH_PATH = ECHO_RUNTIME / "titan_connection_graph.json"
EXPECTED_SEQUENCE = [
    "Ari",
    "ECHO",
    "Unified Brain",
    "Consciousness Core",
    "Master Brain",
    "Specialist Engines",
    "Data/Runtime/Memory/Logs",
]


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def run_mapper() -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(MAPPER_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None, f"Missing file: {relative(path)}"
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {relative(path)} line {exc.lineno}"

    if not isinstance(data, dict):
        return None, f"JSON root must be an object: {relative(path)}"
    return data, None


def validate_top_hierarchy(data: dict[str, Any]) -> list[str]:
    hierarchy = data.get("top_level_hierarchy")
    if not isinstance(hierarchy, dict):
        return ["Architecture map missing top_level_hierarchy object."]
    sequence = hierarchy.get("sequence")
    if sequence != EXPECTED_SEQUENCE:
        return ["Architecture map top hierarchy sequence does not match expected Ari -> ECHO chain."]
    return []


def validate_module_registry(data: dict[str, Any]) -> list[str]:
    modules = data.get("modules")
    if not isinstance(modules, list):
        return ["Module registry field 'modules' must be a list."]
    layers = {
        str(item.get("layer"))
        for item in modules
        if isinstance(item, dict) and item.get("layer")
    }
    if len(layers) < 5:
        return ["Module registry must contain at least 5 layers/groups."]
    return []


def main() -> int:
    errors: list[str] = []

    if not MAPPER_PATH.is_file():
        errors.append(f"Missing mapper: {relative(MAPPER_PATH)}")
    else:
        returncode, stdout, stderr = run_mapper()
        if returncode != 0:
            errors.append(f"Mapper failed with exit code {returncode}.")
        if stderr:
            errors.append("Mapper wrote to stderr.")
        if stdout:
            allowed_prefixes = (
                "TITAN ECHO architecture mapper:",
                "Input files mapped:",
                "Populated layers:",
                "Modules registered:",
                "Graph edges:",
            )
            for line in stdout.splitlines():
                if not line.startswith(allowed_prefixes):
                    errors.append("Mapper printed unexpected output.")
                    break

    architecture_map, error = load_json(ARCHITECTURE_MAP_PATH)
    if error:
        errors.append(error)
    elif architecture_map is not None:
        errors.extend(validate_top_hierarchy(architecture_map))

    module_registry, error = load_json(MODULE_REGISTRY_PATH)
    if error:
        errors.append(error)
    elif module_registry is not None:
        errors.extend(validate_module_registry(module_registry))

    _, error = load_json(CONNECTION_GRAPH_PATH)
    if error:
        errors.append(error)

    if errors:
        print("TITAN ECHO architecture mapper check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    modules = module_registry.get("modules", []) if module_registry else []
    layers = {
        str(item.get("layer"))
        for item in modules
        if isinstance(item, dict) and item.get("layer")
    }
    print("TITAN ECHO architecture mapper check: PASSED")
    print(f"Mapped layers/groups: {len(layers)}")
    print(f"Architecture map: {relative(ARCHITECTURE_MAP_PATH)}")
    print(f"Module registry: {relative(MODULE_REGISTRY_PATH)}")
    print(f"Connection graph: {relative(CONNECTION_GRAPH_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
