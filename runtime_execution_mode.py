from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "data" / "runtime"
EXECUTION_MODE_PATH = RUNTIME_DIR / "execution_mode.json"
LEGACY_MODE_PATH = RUNTIME_DIR / "trading" / "mode.json"
HFT_DIR = ROOT / "data" / "hft_mode"
HFT_RUNTIME_STATE_PATH = HFT_DIR / "hft_runtime_state.json"

IST = timezone(timedelta(hours=5, minutes=30))
ALLOWED_MODES = {"CLASSIC", "HFT"}


def now_ist() -> datetime:
    try:
        from utils.market_hours import IST as MARKET_IST
    except Exception:
        return datetime.now(IST)
    return datetime.now(MARKET_IST)


def normalize_mode(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"HFT", "HFT_MODE", "HIGH_FREQUENCY", "HIGH_FREQUENCY_TRADING"}:
        return "HFT"
    return "CLASSIC"


def read_json(path: Path, default: Any = None) -> Any:
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if payload is not None else default
    except Exception:
        return default


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def _mode_from_payload(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("active_execution_mode", "mode", "active_mode", "trading_mode", "execution_mode"):
        if payload.get(key):
            return normalize_mode(payload.get(key))
    return None


def _execution_mode_payload(mode: str) -> dict[str, Any]:
    timestamp = now_ist().isoformat()
    return {
        "active_execution_mode": normalize_mode(mode),
        "switch_in_progress": False,
        "updated_at_ist": timestamp,
        "source": "runtime_execution_mode",
    }


def write_hft_runtime_state(mode: str) -> dict[str, Any]:
    mode = normalize_mode(mode)
    enabled = mode == "HFT"
    payload = {
        "connected_to_runtime": False,
        "hft_enabled": enabled,
        "last_update": now_ist().isoformat(),
        "mode": "SIMULATION_ONLY",
        "worker_started": enabled,
    }
    atomic_write_json(HFT_RUNTIME_STATE_PATH, payload)
    return payload


def write_execution_mode(mode: Any, *, mirror_legacy: bool = True) -> dict[str, Any]:
    normalized = normalize_mode(mode)
    if normalized not in ALLOWED_MODES:
        normalized = "CLASSIC"
    payload = _execution_mode_payload(normalized)
    atomic_write_json(EXECUTION_MODE_PATH, payload)
    if mirror_legacy:
        atomic_write_json(LEGACY_MODE_PATH, {"mode": normalized, "updated_at_ist": payload["updated_at_ist"]})
    write_hft_runtime_state(normalized)
    return payload


def read_execution_mode_payload(*, migrate: bool = True) -> dict[str, Any]:
    payload = read_json(EXECUTION_MODE_PATH, {})
    mode = _mode_from_payload(payload)
    if mode is None:
        legacy = read_json(LEGACY_MODE_PATH, {})
        mode = _mode_from_payload(legacy) or "CLASSIC"
        if migrate:
            return write_execution_mode(mode)
    if not isinstance(payload, dict) or payload.get("active_execution_mode") != mode:
        if migrate:
            return write_execution_mode(mode)
    return payload if isinstance(payload, dict) else _execution_mode_payload(mode)


def active_execution_mode(*, migrate: bool = True) -> str:
    return normalize_mode(read_execution_mode_payload(migrate=migrate).get("active_execution_mode"))


def hft_mode_active(*, migrate: bool = True) -> bool:
    return active_execution_mode(migrate=migrate) == "HFT"
