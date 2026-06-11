from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "data" / "runtime"
APPROVED_SIGNALS_PATH = RUNTIME_DIR / "approved_signals.json"
SIGNAL_STATUS_PATH = RUNTIME_DIR / "signal_manager_status.json"

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    return datetime.now(IST)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        if not path.exists():
            return default
        payload = json.loads(path.read_text(encoding="utf-8"))
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


def normalize_mode(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"HFT", "HFT_MODE"}:
        return "HFT"
    if text in {"CLASSICAL_TOIF", "TOIF", "CLASSIC"}:
        return "CLASSIC"
    return text or "UNKNOWN"


def signal_key(signal: dict[str, Any]) -> str:
    symbol = str(signal.get("symbol") or "").strip().upper().replace(".NS", "")
    mode = normalize_mode(signal.get("mode"))
    direction = str(signal.get("side") or signal.get("direction") or "LONG").strip().upper()
    signal_type = str(signal.get("signal_type") or signal.get("strategy") or signal.get("source") or "UNKNOWN").strip().upper()
    candle = str(signal.get("candle_time") or signal.get("window") or signal.get("latest_tick_timestamp") or "").strip()
    return "|".join([symbol, mode, direction, signal_type, candle])


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _valid_hft_microstructure(signal: dict[str, Any]) -> bool:
    bid = _safe_float(signal.get("bid"))
    ask = _safe_float(signal.get("ask"))
    spread = _safe_float(signal.get("spread"))
    spread_pct = _safe_float(signal.get("spread_pct"))
    if bid is None or ask is None or bid <= 0 or ask <= 0 or bid > ask:
        return False
    if spread is None or spread <= 0:
        return False
    if spread_pct is None or spread_pct > 0.75:
        return False
    return True


def _classic_reject_reason(signal: dict[str, Any]) -> str | None:
    engine = str(signal.get("engine") or "").strip().upper()
    source = str(signal.get("source") or "").strip()
    if engine != "TOIF" or source != "runtime_classic_engine":
        return "missing_toif_provenance"
    if _safe_float(signal.get("alpha")) is None:
        return "missing_toif_alpha"
    if signal.get("signal_allowed") is not True:
        return "signal_not_allowed"
    reject_reason = str(signal.get("reject_reason") or "").strip()
    if reject_reason:
        return reject_reason
    return None


def _load_signal_state() -> dict[str, Any]:
    payload = read_json(APPROVED_SIGNALS_PATH, {})
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("approved_signals", [])
    payload.setdefault("seen_keys", [])
    return payload


def approve_signals(
    candidates: list[dict[str, Any]],
    *,
    mode: str,
    signal_allowed: bool,
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    mode = normalize_mode(mode)
    blockers = list(blockers or [])
    state = _load_signal_state()
    seen = {str(item) for item in state.get("seen_keys") or []}
    approved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    timestamp = now_ist().isoformat()

    if not signal_allowed:
        for candidate in candidates or []:
            rejected.append({
                "symbol": candidate.get("symbol") if isinstance(candidate, dict) else None,
                "reason": "signal_not_allowed",
            })
    else:
        for candidate in candidates or []:
            if not isinstance(candidate, dict):
                rejected.append({"symbol": None, "reason": "invalid_candidate_payload"})
                continue
            key = signal_key({**candidate, "mode": mode})
            symbol = str(candidate.get("symbol") or "").strip().upper()
            if not symbol:
                rejected.append({"symbol": None, "reason": "missing_symbol"})
                continue
            if mode == "HFT" and not _valid_hft_microstructure(candidate):
                rejected.append({"symbol": symbol, "reason": "missing_real_hft_microstructure"})
                continue
            if mode == "CLASSIC":
                classic_reject_reason = _classic_reject_reason(candidate)
                if classic_reject_reason:
                    rejected.append({"symbol": symbol, "reason": classic_reject_reason})
                    continue
            if key in seen:
                rejected.append({"symbol": symbol, "reason": "duplicate_signal", "key": key})
                continue
            signal = dict(candidate)
            signal.update(
                {
                    "key": key,
                    "mode": mode,
                    "status": "APPROVED",
                    "approved_at_ist": timestamp,
                    "paper_only": True,
                    "broker_orders": False,
                    "live_order_placement": False,
                    "source_owner": "runtime_signal_manager",
                }
            )
            approved.append(signal)
            seen.add(key)

    active_signals = [
        item for item in state.get("approved_signals") or []
        if isinstance(item, dict) and normalize_mode(item.get("mode")) == mode and item.get("status") == "APPROVED"
    ]
    active_signals.extend(approved)
    state.update(
        {
            "timestamp_ist": timestamp,
            "status": "ACTIVE" if signal_allowed else "BLOCKED",
            "mode": mode,
            "approved_signals": active_signals[-200:],
            "seen_keys": sorted(seen)[-1000:],
            "approved_count": len(approved),
            "active_signal_count": len(active_signals[-200:]),
            "rejected_count": len(rejected),
            "rejected": rejected[:200],
            "blockers": blockers,
            "paper_only": True,
            "broker_orders": False,
            "live_order_placement": False,
        }
    )
    atomic_write_json(APPROVED_SIGNALS_PATH, state)
    atomic_write_json(SIGNAL_STATUS_PATH, state)
    return state


def approved_signals_for_mode(mode: str) -> list[dict[str, Any]]:
    mode = normalize_mode(mode)
    payload = _load_signal_state()
    return [
        dict(item) for item in payload.get("approved_signals") or []
        if isinstance(item, dict) and normalize_mode(item.get("mode")) == mode and item.get("status") == "APPROVED"
    ]


def clear_signals_for_mode(mode: str, *, reason: str = "cleared") -> dict[str, Any]:
    mode = normalize_mode(mode)
    payload = _load_signal_state()
    kept = [
        item for item in payload.get("approved_signals") or []
        if not (isinstance(item, dict) and normalize_mode(item.get("mode")) == mode)
    ]
    payload.update(
        {
            "timestamp_ist": now_ist().isoformat(),
            "mode": mode,
            "status": "CLEARED",
            "approved_signals": kept,
            "clear_reason": reason,
        }
    )
    atomic_write_json(APPROVED_SIGNALS_PATH, payload)
    atomic_write_json(SIGNAL_STATUS_PATH, payload)
    return payload
