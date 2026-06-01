"""Build TITAN module registry for ECHO."""

from __future__ import annotations

from typing import Any

from titan_echo.knowledge.common import category_for_path, iter_files, module_for_path, now_utc, output_path, relative, write_json


OUTPUT_PATH = output_path("module_registry.json")

MODULE_ROLES = {
    "api": "external and local API surfaces",
    "brain": "decision and orchestration intelligence",
    "dashboard": "operator visibility and reporting UI",
    "echo": "ECHO observer, memory, proof, and knowledge layer",
    "engines": "strategy, scoring, execution, and intelligence engines",
    "evolution": "learning evolution and mutation governance",
    "journal": "trade journals and outcome records",
    "learning": "adaptive learning and feedback systems",
    "memory": "persistent memory and state stores",
    "news": "news and calendar intelligence",
    "research": "historical research, replay, and enrichment",
    "runtime": "runtime workers, health, scheduling, and status",
    "scanner": "market scanner and setup selection",
}


def build_module_registry() -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for path in iter_files():
        rel = relative(path)
        module = module_for_path(rel)
        item = grouped.setdefault(
            module,
            {
                "module": module,
                "module_name": module,
                "role": MODULE_ROLES.get(module, f"{module} support module"),
                "category": category_for_path(rel),
                "locations": [],
                "location": "",
                "file_count": 0,
            },
        )
        item["locations"].append(rel)
        item["file_count"] += 1
        if not item["location"]:
            item["location"] = rel.split("/")[0] if "/" in rel else rel
    modules = sorted(grouped.values(), key=lambda item: item["module"])
    return {
        "schema": "titan_echo.knowledge.module_registry.v1",
        "generated_at_utc": now_utc(),
        "mode": "read_only_static_registry",
        "summary": {"total_modules": len(modules)},
        "modules": modules,
    }


def write_module_registry(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = payload or build_module_registry()
    write_json(OUTPUT_PATH, registry)
    return registry


def main() -> int:
    registry = write_module_registry()
    print("ECHO module registry: PASSED")
    print(f"Modules: {registry['summary']['total_modules']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
