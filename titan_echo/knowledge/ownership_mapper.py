"""Best-effort static read/write ownership map for TITAN."""

from __future__ import annotations

from typing import Any

from titan_echo.knowledge.common import detect_io_targets, iter_files, module_for_path, now_utc, output_path, relative, write_json


OUTPUT_PATH = output_path("ownership_map.json")


def build_ownership_map() -> dict[str, Any]:
    records = []
    for path in iter_files({".py"}):
        rel = relative(path)
        reads = detect_io_targets(path, "read")
        writes = detect_io_targets(path, "write")
        if not reads and not writes:
            continue
        records.append(
            {
                "component": rel,
                "module": module_for_path(rel),
                "reads": reads,
                "writes": writes,
                "analysis": "best_effort_static_ast_only",
            }
        )
    return {
        "schema": "titan_echo.knowledge.ownership_map.v1",
        "generated_at_utc": now_utc(),
        "mode": "read_only_static_analysis",
        "summary": {"components_with_io": len(records)},
        "ownership": records,
    }


def write_ownership_map(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    ownership = payload or build_ownership_map()
    write_json(OUTPUT_PATH, ownership)
    return ownership


def main() -> int:
    ownership = write_ownership_map()
    print("ECHO ownership mapper: PASSED")
    print(f"Components with IO: {ownership['summary']['components_with_io']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
