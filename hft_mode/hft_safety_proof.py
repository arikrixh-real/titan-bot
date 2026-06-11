"""Final safety proof for sealed HFT mode."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from hft_mode import hft_config
from hft_mode.hft_dashboard_export import read_hft_dashboard_export
from hft_mode.hft_mode_worker import AUTO_STARTED
from hft_mode.hft_runtime_state import write_hft_json

FINAL_STATUS = "BUILT_DISCONNECTED"

FORBIDDEN_IMPORTS = {
    "titan_daemon",
    "runtime_scheduler_map",
    "runtime_continuous_workers",
    "runtime_status",
    "runtime_truth",
    "runtime_scanner",
    "runtime_setup_engine",
    "runtime_journal",
    "runtime_outcome_tracker",
    "runtime_master_brain",
    "dashboard",
    "titan_api",
    "notifications",
    "titan_master_brain",
    "broker",
    "telegram",
}

FORBIDDEN_LIVE_ORDER_METHODS = {
    "place_order",
    "send_order",
    "submit_order",
    "place_live_order",
    "send_live_order",
    "broker_order",
}


def _hft_module_paths() -> list[Path]:
    root = Path(__file__).resolve().parent
    return sorted(path for path in root.glob("*.py") if path.name != "__init__.py")


def _import_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
            imports.add(node.module)
    return imports


def _function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _write_paths_are_confined() -> bool:
    root = hft_config.HFT_DATA_DIR.resolve()
    for file_name in hft_config.HFT_DATA_FILES.values():
        target = (hft_config.HFT_DATA_DIR / file_name).resolve()
        if target.parent != root:
            return False
    return True


def build_hft_safety_proof() -> dict[str, Any]:
    module_paths = _hft_module_paths()
    imports_by_file = {path.name: sorted(_import_names(path)) for path in module_paths}
    imported_names = {name for names in imports_by_file.values() for name in names}
    function_names = {name for path in module_paths for name in _function_names(path)}
    dashboard_export = read_hft_dashboard_export()

    forbidden_found = sorted(FORBIDDEN_IMPORTS & imported_names)
    live_order_methods_found = sorted(FORBIDDEN_LIVE_ORDER_METHODS & function_names)
    return {
        "hft_enabled": hft_config.HFT_ENABLED,
        "mode": hft_config.MODE,
        "auto_started": AUTO_STARTED,
        "connected_to_titan_runtime": hft_config.ACTIVE_RUNTIME_CONNECTION_ALLOWED,
        "broker_allowed": hft_config.BROKER_ALLOWED,
        "telegram_allowed": hft_config.TELEGRAM_ALLOWED,
        "classic_journal_write_allowed": hft_config.CLASSIC_JOURNAL_WRITE_ALLOWED,
        "classic_memory_write_allowed": hft_config.CLASSIC_MEMORY_WRITE_ALLOWED,
        "titan_evolution_write_allowed": hft_config.TITAN_EVOLUTION_WRITE_ALLOWED,
        "master_brain_access_allowed": hft_config.MASTER_BRAIN_ACCESS_ALLOWED,
        "dashboard_integration_present": "dashboard" in imported_names,
        "daemon_integration_present": "titan_daemon" in imported_names,
        "runtime_scheduler_integration_present": "runtime_scheduler_map" in imported_names,
        "data_write_root": "data/hft_mode",
        "allowed_data_files": sorted(hft_config.HFT_DATA_FILES.values()),
        "forbidden_imports_checked": sorted(FORBIDDEN_IMPORTS),
        "forbidden_imports_found": forbidden_found,
        "write_paths_confined_to_hft_data": _write_paths_are_confined(),
        "live_order_methods_found": live_order_methods_found,
        "worker_auto_started": AUTO_STARTED,
        "dashboard_export_read_only": dashboard_export.get("read_only") is True,
        "hft_off_by_default": hft_config.HFT_ENABLED is False,
        "final_status": FINAL_STATUS,
    }


def write_hft_safety_proof() -> dict[str, Any]:
    proof = build_hft_safety_proof()
    write_hft_json("hft_safety_proof.json", proof)
    return proof
