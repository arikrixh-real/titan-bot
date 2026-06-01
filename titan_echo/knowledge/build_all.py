"""Generate all read-only ECHO knowledge registries."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from titan_echo.knowledge import architecture_mapper
from titan_echo.knowledge import change_rules
from titan_echo.knowledge import connection_graph
from titan_echo.knowledge import danger_classifier
from titan_echo.knowledge import engine_registry
from titan_echo.knowledge import file_indexer
from titan_echo.knowledge import file_role_mapper
from titan_echo.knowledge import module_registry
from titan_echo.knowledge import ownership_mapper
from titan_echo.knowledge import secret_registry
from titan_echo.knowledge import test_registry
from titan_echo.knowledge.common import get_scan_stats, now_utc, output_path, reset_scan_stats, set_safe_mode, write_json
from titan_echo.knowledge.echo_memory import initialize_memory_files


STATUS_PATH = output_path("knowledge_build_status.json")

BUILDERS: tuple[tuple[str, Callable[[], dict[str, Any]], str], ...] = (
    ("file_index", file_indexer.write_file_index, "file_index.json"),
    ("module_registry", module_registry.write_module_registry, "module_registry.json"),
    ("engine_registry", engine_registry.write_engine_registry, "engine_registry.json"),
    ("file_role_map", file_role_mapper.write_file_role_map, "file_role_map.json"),
    ("secret_registry", secret_registry.write_secret_registry, "secret_registry.json"),
    ("danger_registry", danger_classifier.write_danger_registry, "danger_registry.json"),
    ("ownership_map", ownership_mapper.write_ownership_map, "ownership_map.json"),
    ("connection_graph", connection_graph.write_connection_graph, "connection_graph.json"),
    ("architecture_map", architecture_mapper.write_architecture_map, "architecture_map.json"),
    ("change_rules", change_rules.write_change_rules, "change_rules.json"),
    ("test_registry", test_registry.write_test_registry, "test_registry.json"),
)


def _public_output_path(name: str) -> str:
    return output_path(name).relative_to(output_path(name).parents[3]).as_posix()


def _summary(payload: dict[str, Any]) -> object:
    return payload.get("summary") or payload.get("schema") or "written"


def _write_status(status: dict[str, Any]) -> None:
    status["updated_at_utc"] = now_utc()
    status["scan_summary"] = get_scan_stats()
    write_json(STATUS_PATH, status)


def build_all(*, safe: bool = False) -> dict[str, Any]:
    set_safe_mode(safe)
    reset_scan_stats()
    memory_files = initialize_memory_files()
    outputs: dict[str, object] = {}
    errors: dict[str, dict[str, str]] = {}
    output_paths: dict[str, str] = {"status": _public_output_path("knowledge_build_status.json")}
    output_paths.update({f"memory_{name}": path for name, path in memory_files.items()})
    status: dict[str, Any] = {
        "schema": "titan_echo.knowledge.build_status.v1",
        "started_at_utc": now_utc(),
        "mode": "safe" if safe else "default",
        "ok": True,
        "outputs": outputs,
        "errors": errors,
        "output_paths": output_paths,
        "scan_summary": get_scan_stats(),
    }
    _write_status(status)

    for name, writer, filename in BUILDERS:
        try:
            payload = writer()
            outputs[name] = _summary(payload)
            output_paths[name] = _public_output_path(filename)
        except Exception as exc:
            errors[name] = {"type": type(exc).__name__, "message": str(exc)}
            status["ok"] = False
        _write_status(status)

    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build ECHO knowledge registries.")
    parser.add_argument("--safe", action="store_true", help="Use VPS-safe scan limits and partial-failure status writes.")
    args = parser.parse_args(argv)

    status = build_all(safe=args.safe)
    print("ECHO knowledge foundation build: PASSED" if status["ok"] else "ECHO knowledge foundation build: COMPLETED WITH ERRORS")
    summary = status["scan_summary"]
    print(f"files_seen: {summary['files_seen']}")
    print(f"files_indexed: {summary['files_indexed']}")
    print(f"files_skipped: {summary['files_skipped']}")
    print("output_paths:")
    for name, path in sorted(status["output_paths"].items()):
        print(f"  {name}: {path}")
    if status["errors"]:
        print("errors:")
        for name, error in sorted(status["errors"].items()):
            print(f"  {name}: {error['type']}: {error['message']}")
    return 0 if status["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
