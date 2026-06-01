"""Discover TITAN engines for ECHO."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from titan_echo.knowledge.common import category_for_path, iter_files, module_for_path, now_utc, output_path, relative, write_json


OUTPUT_PATH = output_path("engine_registry.json")


def is_engine(rel: str) -> bool:
    name = Path(rel).name.lower()
    return "engine" in name or rel.lower().startswith("engines/")


def build_engine_registry() -> dict[str, Any]:
    engines = []
    for path in iter_files({".py"}):
        rel = relative(path)
        if not is_engine(rel):
            continue
        name = Path(rel).stem
        engines.append(
            {
                "engine_name": name,
                "engine": name,
                "file_path": rel,
                "category": category_for_path(rel),
                "related_modules": sorted({module_for_path(rel), rel.split("/")[0]}),
            }
        )
    return {
        "schema": "titan_echo.knowledge.engine_registry.v1",
        "generated_at_utc": now_utc(),
        "mode": "read_only_static_registry",
        "summary": {"total_engines": len(engines)},
        "engines": sorted(engines, key=lambda item: item["file_path"]),
    }


def write_engine_registry(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = payload or build_engine_registry()
    write_json(OUTPUT_PATH, registry)
    return registry


def main() -> int:
    registry = write_engine_registry()
    print("ECHO engine registry: PASSED")
    print(f"Engines: {registry['summary']['total_engines']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
