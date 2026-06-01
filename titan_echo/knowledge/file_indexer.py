"""Build a read-only index of TITAN files for ECHO."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from titan_echo.knowledge.common import (
    ast_defs,
    ast_imports,
    category_for_path,
    danger_for_path,
    iter_files,
    module_for_path,
    now_utc,
    output_path,
    parse_ast,
    relative,
    role_for_path,
    write_json,
)


OUTPUT_PATH = output_path("file_index.json")


def index_file(path: Path) -> dict[str, Any]:
    rel = relative(path)
    tree = parse_ast(path)
    functions, classes = ast_defs(tree)
    danger, reason = danger_for_path(rel)
    return {
        "path": rel,
        "relative_path": rel,
        "module": module_for_path(rel),
        "module_name": module_for_path(rel),
        "extension": path.suffix.lower(),
        "category": category_for_path(rel),
        "size_bytes": path.stat().st_size,
        "modified_timestamp": path.stat().st_mtime,
        "modified_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        "detected_imports": ast_imports(tree),
        "detected_functions": functions,
        "detected_classes": classes,
        "probable_role": role_for_path(rel),
        "criticality": danger,
        "danger_reason": reason,
    }


def build_file_index() -> dict[str, Any]:
    files = [index_file(path) for path in iter_files()]
    category_counts: dict[str, int] = {}
    module_counts: dict[str, int] = {}
    danger_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    for item in files:
        category_counts[item["category"]] = category_counts.get(item["category"], 0) + 1
        module_counts[item["module"]] = module_counts.get(item["module"], 0) + 1
        danger_counts[item["criticality"]] = danger_counts.get(item["criticality"], 0) + 1
    return {
        "schema": "titan_echo.knowledge.file_index.v1",
        "generated_at_utc": now_utc(),
        "mode": "read_only_static_index",
        "summary": {
            "total_files": len(files),
            "category_counts": dict(sorted(category_counts.items())),
            "module_counts": dict(sorted(module_counts.items())),
            "danger_counts": danger_counts,
        },
        "excluded": [
            ".venv",
            ".git",
            "__pycache__",
            "data/cache",
            "data/historical_longterm",
            "data/runtime",
            "data/journals",
            "data/report_vault",
            "reports",
            "backups",
            "node_modules",
        ],
        "files": files,
    }


def write_file_index(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    index = payload or build_file_index()
    write_json(OUTPUT_PATH, index)
    return index


def main() -> int:
    index = write_file_index()
    print("ECHO file indexer: PASSED")
    print(f"Indexed files: {index['summary']['total_files']}")
    print(f"Output: {OUTPUT_PATH.relative_to(OUTPUT_PATH.parents[3]).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
