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
RUNTIME_MODE_STATUS_PATH = RUNTIME_DIR / "runtime_mode_status.json"
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
    normalized = normalize_mode(mode)
    return {
        "active_execution_mode": normalized,
        "canonical_active_mode": normalized,
        "mode": normalized,
        "mode_consistency": "OK",
        "source_of_truth": "execution_mode",
        "timestamp": timestamp,
        "timestamp_ist": timestamp,
        "switch_in_progress": False,
        "updated_at_ist": timestamp,
        "owner": "runtime_execution_mode",
        "source": "runtime_execution_mode",
    }


def _write_runtime_mode_status_from_execution_mode(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_mode(payload.get("active_execution_mode") or payload.get("mode"))
    timestamp = payload.get("timestamp_ist") or now_ist().isoformat()
    previous = read_json(RUNTIME_MODE_STATUS_PATH, {})
    status = dict(previous) if isinstance(previous, dict) else {}
    status.update(
        {
            "active_execution_mode": normalized,
            "canonical_active_mode": normalized,
            "execution_mode_source": "data/runtime/execution_mode.json",
            "mode_consistency": "OK",
            "source_of_truth": "execution_mode",
            "timestamp_ist": timestamp,
            "updated_at_ist": timestamp,
        }
    )
    status.setdefault("current_mode", "UNKNOWN")
    atomic_write_json(RUNTIME_MODE_STATUS_PATH, status)
    return status


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


def _write_execution_mode_direct(mode: Any, *, mirror_legacy: bool = True) -> dict[str, Any]:
    normalized = normalize_mode(mode)
    if normalized not in ALLOWED_MODES:
        normalized = "CLASSIC"
    payload = _execution_mode_payload(normalized)
    atomic_write_json(EXECUTION_MODE_PATH, payload)
    _write_runtime_mode_status_from_execution_mode(payload)
    if mirror_legacy:
        atomic_write_json(
            LEGACY_MODE_PATH,
            {
                "active_execution_mode": normalized,
                "canonical_active_mode": normalized,
                "mode": normalized,
                "mode_consistency": "OK",
                "source_of_truth": "execution_mode",
                "timestamp": payload["timestamp"],
                "timestamp_ist": payload["timestamp_ist"],
                "updated_at_ist": payload["updated_at_ist"],
                "owner": "runtime_execution_mode",
                "source": "runtime_execution_mode_legacy_mirror",
            },
        )
    write_hft_runtime_state(normalized)
    return payload


def write_execution_mode(mode: Any, *, mirror_legacy: bool = True, transactional: bool = True) -> dict[str, Any]:
    normalized = normalize_mode(mode)
    if normalized not in ALLOWED_MODES:
        normalized = "CLASSIC"
    current = _mode_from_payload(read_json(EXECUTION_MODE_PATH, {}))
    if current is None:
        legacy = read_json(LEGACY_MODE_PATH, {})
        current = _mode_from_payload(legacy) or normalized
    if transactional and current != normalized:
        from runtime_mode_switch import request_mode_switch

        switch_payload = request_mode_switch(
            normalized,
            old_mode=current,
            writer=lambda target_mode: _write_execution_mode_direct(target_mode, mirror_legacy=mirror_legacy),
        )
        if switch_payload.get("state") == "COMPLETE":
            return switch_payload.get("execution_mode") or read_execution_mode_payload(migrate=False)
        failed = _execution_mode_payload(current)
        failed["switch_in_progress"] = False
        failed["switch_failed"] = True
        failed["switch_failure_reason"] = switch_payload.get("reason")
        failed["mode_switch_status_path"] = "data/runtime/mode_switch_status.json"
        return failed
    return _write_execution_mode_direct(normalized, mirror_legacy=mirror_legacy)


def read_execution_mode_payload(*, migrate: bool = True) -> dict[str, Any]:
    payload = read_json(EXECUTION_MODE_PATH, {})
    mode = _mode_from_payload(payload)
    if mode is None:
        legacy = read_json(LEGACY_MODE_PATH, {})
        mode = _mode_from_payload(legacy) or "CLASSIC"
        if migrate:
            return write_execution_mode(mode, transactional=False)
    if not isinstance(payload, dict) or payload.get("active_execution_mode") != mode:
        if migrate:
            return write_execution_mode(mode, transactional=False)
    return payload if isinstance(payload, dict) else _execution_mode_payload(mode)


def active_execution_mode(*, migrate: bool = True) -> str:
    return normalize_mode(read_execution_mode_payload(migrate=migrate).get("active_execution_mode"))


def get_active_mode(*, migrate: bool = True) -> str:
    return active_execution_mode(migrate=migrate)


def hft_mode_active(*, migrate: bool = True) -> bool:
    return active_execution_mode(migrate=migrate) == "HFT"
