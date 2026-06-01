"""Generate all read-only ECHO knowledge registries."""

from __future__ import annotations

from titan_echo.knowledge.architecture_mapper import write_architecture_map
from titan_echo.knowledge.change_rules import write_change_rules
from titan_echo.knowledge.connection_graph import write_connection_graph
from titan_echo.knowledge.danger_classifier import write_danger_registry
from titan_echo.knowledge.echo_memory import initialize_memory_files
from titan_echo.knowledge.engine_registry import write_engine_registry
from titan_echo.knowledge.file_indexer import write_file_index
from titan_echo.knowledge.file_role_mapper import write_file_role_map
from titan_echo.knowledge.module_registry import write_module_registry
from titan_echo.knowledge.ownership_mapper import write_ownership_map
from titan_echo.knowledge.secret_registry import write_secret_registry
from titan_echo.knowledge.test_registry import write_test_registry


def build_all() -> dict[str, object]:
    initialize_memory_files()
    outputs = {
        "file_index": write_file_index()["summary"],
        "module_registry": write_module_registry()["summary"],
        "engine_registry": write_engine_registry()["summary"],
        "file_role_map": write_file_role_map()["summary"],
        "secret_registry": write_secret_registry()["summary"],
        "danger_registry": write_danger_registry()["summary"],
        "ownership_map": write_ownership_map()["summary"],
        "connection_graph": write_connection_graph()["summary"],
        "architecture_map": write_architecture_map()["schema"],
        "change_rules": write_change_rules()["schema"],
        "test_registry": write_test_registry()["schema"],
    }
    return outputs


def main() -> int:
    outputs = build_all()
    print("ECHO knowledge foundation build: PASSED")
    for name, summary in outputs.items():
        print(f"{name}: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
