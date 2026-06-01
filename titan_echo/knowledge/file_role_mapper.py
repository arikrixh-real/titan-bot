"""Assign human-readable roles to TITAN files."""

from __future__ import annotations

from typing import Any

from titan_echo.knowledge.common import category_for_path, iter_files, module_for_path, now_utc, output_path, relative, role_for_path, write_json


OUTPUT_PATH = output_path("file_role_map.json")


def build_file_role_map() -> dict[str, Any]:
    roles = [
        {
            "path": relative(path),
            "module": module_for_path(relative(path)),
            "category": category_for_path(relative(path)),
            "role": role_for_path(relative(path)),
        }
        for path in iter_files()
    ]
    return {
        "schema": "titan_echo.knowledge.file_role_map.v1",
        "generated_at_utc": now_utc(),
        "mode": "read_only_static_role_inference",
        "summary": {"total_files": len(roles)},
        "files": roles,
    }


def write_file_role_map(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    role_map = payload or build_file_role_map()
    write_json(OUTPUT_PATH, role_map)
    return role_map


def main() -> int:
    role_map = write_file_role_map()
    print("ECHO file role mapper: PASSED")
    print(f"Files: {role_map['summary']['total_files']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
