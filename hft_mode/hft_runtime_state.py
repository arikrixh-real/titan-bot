"""Runtime-state helpers for sealed HFT simulation data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hft_mode import hft_config

DEFAULT_RUNTIME_FILES: dict[str, dict[str, Any]] = {
    "hft_runtime_state.json": {
        "hft_enabled": hft_config.HFT_ENABLED,
        "mode": hft_config.MODE,
        "connected_to_runtime": False,
        "worker_started": False,
        "last_update": None,
    },
    "hft_health.json": {
        "status": "OFFLINE",
        "mode": hft_config.MODE,
        "broker_allowed": hft_config.BROKER_ALLOWED,
        "telegram_allowed": hft_config.TELEGRAM_ALLOWED,
        "runtime_connection_allowed": hft_config.ACTIVE_RUNTIME_CONNECTION_ALLOWED,
    },
    "hft_stats.json": {
        "signals_seen": 0,
        "simulated_orders": 0,
        "live_orders": 0,
        "rejections": 0,
    },
    "hft_active_trades.json": {
        "active_trades": [],
    },
    "hft_closed_summary.json": {
        "closed_trades": 0,
        "wins": 0,
        "losses": 0,
        "net_pnl": 0.0,
    },
    "hft_outcomes.json": {
        "outcomes": [],
    },
    "hft_daily_pnl.json": {
        "daily_pnl": [],
    },
    "hft_rejected_count.json": {
        "rejected_count": 0,
        "reasons": {},
    },
}


def hft_data_dir() -> Path:
    return hft_config.HFT_DATA_DIR


def resolve_hft_data_path(file_name: str | Path) -> Path:
    candidate = Path(file_name)
    if candidate.is_absolute() or ".." in candidate.parts or len(candidate.parts) != 1:
        raise ValueError("HFT data writes must target a file directly under data/hft_mode")

    target = (hft_data_dir() / candidate).resolve()
    root = hft_data_dir().resolve()
    if target.parent != root:
        raise ValueError("HFT data writes must stay inside data/hft_mode")
    return target


def write_hft_json(file_name: str | Path, payload: dict[str, Any]) -> Path:
    target = resolve_hft_data_path(file_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def read_hft_json(file_name: str | Path) -> dict[str, Any]:
    target = resolve_hft_data_path(file_name)
    return json.loads(target.read_text(encoding="utf-8"))


def initialize_hft_runtime_files() -> list[Path]:
    written = []
    for file_name, payload in DEFAULT_RUNTIME_FILES.items():
        written.append(write_hft_json(file_name, payload))
    return written
