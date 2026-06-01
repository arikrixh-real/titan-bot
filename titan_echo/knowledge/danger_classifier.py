"""Classify TITAN files by ECHO modification danger level."""

from __future__ import annotations

from typing import Any

from titan_echo.knowledge.common import category_for_path, danger_for_path, iter_files, module_for_path, now_utc, output_path, relative, write_json


OUTPUT_PATH = output_path("danger_registry.json")


def build_danger_registry() -> dict[str, Any]:
    files = []
    counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    for path in iter_files():
        rel = relative(path)
        level, reason = danger_for_path(rel)
        counts[level] = counts.get(level, 0) + 1
        files.append(
            {
                "path": rel,
                "module": module_for_path(rel),
                "category": category_for_path(rel),
                "danger_level": level,
                "reason": reason,
                "change_rule": "read-only unless explicitly approved" if level in {"HIGH", "CRITICAL"} else "verify before change",
            }
        )
    return {
        "schema": "titan_echo.knowledge.danger_registry.v1",
        "generated_at_utc": now_utc(),
        "levels": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
        "summary": {"danger_counts": counts, "total_files": len(files)},
        "files": files,
    }


def write_danger_registry(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = payload or build_danger_registry()
    write_json(OUTPUT_PATH, registry)
    return registry


def main() -> int:
    registry = write_danger_registry()
    print("ECHO danger classifier: PASSED")
    print(f"Danger counts: {registry['summary']['danger_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
