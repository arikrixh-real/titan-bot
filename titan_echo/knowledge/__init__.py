"""Read-only TITAN ECHO knowledge foundation."""

from __future__ import annotations

from titan_echo.knowledge.architecture_mapper import build_architecture_map
from titan_echo.knowledge.change_rules import build_change_rules
from titan_echo.knowledge.connection_graph import build_connection_graph
from titan_echo.knowledge.danger_classifier import build_danger_registry
from titan_echo.knowledge.engine_registry import build_engine_registry
from titan_echo.knowledge.file_indexer import build_file_index
from titan_echo.knowledge.file_role_mapper import build_file_role_map
from titan_echo.knowledge.module_registry import build_module_registry
from titan_echo.knowledge.ownership_mapper import build_ownership_map
from titan_echo.knowledge.secret_registry import build_secret_registry
from titan_echo.knowledge.test_registry import build_test_registry


__all__ = [
    "build_architecture_map",
    "build_change_rules",
    "build_connection_graph",
    "build_danger_registry",
    "build_engine_registry",
    "build_file_index",
    "build_file_role_map",
    "build_module_registry",
    "build_ownership_map",
    "build_secret_registry",
    "build_test_registry",
]
