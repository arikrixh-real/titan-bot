from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import sys


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "data" / "runtime"
MODE_SWITCH_STATUS_PATH = RUNTIME_DIR / "mode_switch_status.json"
PAPER_TRADE_REGISTRY_PATH = RUNTIME_DIR / "paper_trade_registry.json"
LIVE_PRICE_CACHE_PATH = ROOT / "data" / "live_price_cache.json"
HFT_SCANNER_STATUS_PATH = ROOT / "data" / "hft_mode" / "hft_scanner_status.json"
HFT_MODE_SCANNER_STATUS_PATH = RUNTIME_DIR / "hft_mode_scanner_status.json"
CLASSIC_SCANNER_STATUS_PATH = RUNTIME_DIR / "classic_scanner_status.json"
CLASSIC_MODE_SCANNER_STATUS_PATH = RUNTIME_DIR / "classic_mode_scanner_status.json"
MODE_SIGNAL_CLEAR_PATH = RUNTIME_DIR / "mode_signal_clear_status.json"

IST = timezone(timedelta(hours=5, minutes=30))
SWITCHING_STATES = {
    "SWITCH_REQUESTED",
    "STOPPING_OLD_MODE",
    "CLOSING_OLD_MODE_TRADES",
    "CLEARING_PENDING_SIGNALS",
    "STARTING_NEW_MODE",
}
MAX_SWITCH_PRICE_AGE_SECONDS = 120


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


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_dt(value: Any) -> datetime | None:
    if value in (None, "", "null"):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        ts = value / 1000 if value > 9999999999 else value
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(now_ist().tzinfo)
        except Exception:
            return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=now_ist().tzinfo)
    return dt.astimezone(now_ist().tzinfo)


def _payload_age_seconds(payload: dict[str, Any]) -> float | None:
    for key in ("timestamp_ist", "timestamp", "updated_at_ist", "updated_at", "generated_at_ist", "cache_last_updated"):
        dt = _parse_dt(payload.get(key))
        if dt is not None:
            return max(0.0, (now_ist() - dt).total_seconds())
    return None


def write_switch_status(
    state: str,
    old_mode: str,
    new_mode: str,
    *,
    signal_allowed: bool,
    reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timestamp = now_ist().isoformat()
    payload = {
        "state": state,
        "old_mode": normalize_mode(old_mode),
        "new_mode": normalize_mode(new_mode),
        "signal_allowed": bool(signal_allowed),
        "new_trade_creation_allowed": bool(signal_allowed),
        "switching": state in SWITCHING_STATES,
        "timestamp_ist": timestamp,
        "updated_at_ist": timestamp,
        "reason": reason,
        "owner": "runtime_mode_switch",
        "trade_placement_allowed": False,
    }
    if extra:
        payload.update(extra)
    atomic_write_json(MODE_SWITCH_STATUS_PATH, payload)
    return payload


def read_mode_switch_status() -> dict[str, Any]:
    payload = read_json(MODE_SWITCH_STATUS_PATH, {})
    if not payload:
        execution_mode = read_json(RUNTIME_DIR / "execution_mode.json", {})
        mode = normalize_mode((execution_mode or {}).get("active_execution_mode") or (execution_mode or {}).get("mode"))
        return write_switch_status("IDLE", mode, mode, signal_allowed=True)
    return payload if isinstance(payload, dict) else {}


def switch_in_progress() -> bool:
    payload = read_mode_switch_status()
    return bool(payload.get("switching") or str(payload.get("state") or "").upper() in SWITCHING_STATES)


def signal_allowed() -> bool:
    payload = read_mode_switch_status()
    if not payload:
        return True
    return not switch_in_progress() and bool(payload.get("signal_allowed", True))


def _default_registry() -> dict[str, Any]:
    return {"open_positions": [], "closed_positions": [], "seen_keys": [], "paper_account": {}}


def _load_registry() -> dict[str, Any]:
    registry = read_json(PAPER_TRADE_REGISTRY_PATH, _default_registry())
    if not isinstance(registry, dict):
        return _default_registry()
    registry.setdefault("open_positions", [])
    registry.setdefault("closed_positions", [])
    registry.setdefault("seen_keys", [])
    registry.setdefault("paper_account", {})
    return registry


def _cached_price(symbol: str) -> tuple[float | None, str | None]:
    cache = read_json(LIVE_PRICE_CACHE_PATH, {})
    if not isinstance(cache, dict):
        return None, "live_price_cache_missing"
    if isinstance(cache.get("prices"), dict):
        cache = cache["prices"]
    wanted = str(symbol or "").upper().replace(".NS", "")
    for key, raw in cache.items():
        if str(key or "").upper().replace(".NS", "") != wanted:
            continue
        if not isinstance(raw, dict):
            price = _safe_float(raw)
            return (price, None) if price is not None else (None, "price_missing")
        price = None
        for field in ("ltp", "price", "last_price", "close"):
            if field in raw:
                price = _safe_float(raw.get(field))
                break
        if price is None:
            return None, "price_missing"
        age = _payload_age_seconds(raw)
        if age is None:
            return None, "price_timestamp_missing"
        if age > MAX_SWITCH_PRICE_AGE_SECONDS:
            return None, f"price_stale:{round(age, 3)}s"
        return price, None
    return None, "symbol_price_missing"


def _position_pnl(position: dict[str, Any], exit_price: float) -> float:
    entry = _safe_float(position.get("entry"))
    if entry is None:
        entry = _safe_float(position.get("entry_price"))
    if entry is None:
        return 0.0
    quantity = _safe_float(position.get("quantity")) or 1.0
    if str(position.get("side") or "").upper() == "SHORT":
        return round((entry - exit_price) * quantity, 4)
    return round((exit_price - entry) * quantity, 4)


def _account_float(account: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = _safe_float(account.get(key))
    return value if value is not None else default


def close_open_mode_trades(mode: str) -> dict[str, Any]:
    mode = normalize_mode(mode)
    registry = _load_registry()
    open_positions = registry.get("open_positions") if isinstance(registry.get("open_positions"), list) else []
    old_mode_open = [
        position for position in open_positions
        if isinstance(position, dict)
        and str(position.get("status") or "OPEN").upper() == "OPEN"
        and normalize_mode(position.get("mode")) == mode
    ]
    blockers = []
    prices: dict[str, float] = {}
    for position in old_mode_open:
        symbol = str(position.get("symbol") or "").upper()
        price, reason = _cached_price(symbol)
        if price is None:
            blockers.append({"symbol": symbol, "reason": reason})
        else:
            prices[symbol] = price
    if blockers:
        return {"status": "FAILED", "closed": 0, "open_trades": len(old_mode_open), "blockers": blockers}

    closed_positions = registry.get("closed_positions") if isinstance(registry.get("closed_positions"), list) else []
    remaining_open = []
    realized = 0.0
    closed_count = 0
    timestamp = now_ist().isoformat()
    for position in open_positions:
        if not isinstance(position, dict):
            continue
        if str(position.get("status") or "OPEN").upper() == "OPEN" and normalize_mode(position.get("mode")) == mode:
            symbol = str(position.get("symbol") or "").upper()
            exit_price = prices[symbol]
            pnl = _position_pnl(position, exit_price)
            closed = dict(position)
            closed.update(
                {
                    "status": "CLOSED",
                    "outcome": "MODE_SWITCH_EXIT",
                    "result": "MODE_SWITCH_EXIT",
                    "exit_reason": "MODE_SWITCH_EXIT",
                    "exit_price": exit_price,
                    "last_price": exit_price,
                    "realized_pnl": pnl,
                    "closed_at_ist": timestamp,
                    "timestamp_ist": timestamp,
                    "mode": mode,
                    "paper_only": True,
                    "live_order": False,
                }
            )
            closed_positions.append(closed)
            realized += pnl
            closed_count += 1
        else:
            remaining_open.append(position)

    account = registry.get("paper_account") if isinstance(registry.get("paper_account"), dict) else {}
    account["current_balance"] = round(_account_float(account, "current_balance", 1000.0) + realized, 4)
    account["realized_pnl"] = round(_account_float(account, "realized_pnl", 0.0) + realized, 4)
    account["unrealized_pnl"] = 0.0
    account["equity"] = round(account["current_balance"], 4)
    registry["open_positions"] = remaining_open
    registry["closed_positions"] = closed_positions
    registry["paper_account"] = account
    atomic_write_json(PAPER_TRADE_REGISTRY_PATH, registry)
    return {"status": "COMPLETE", "closed": closed_count, "realized_pnl": round(realized, 4), "open_trades": len(old_mode_open)}


def clear_pending_signals(mode: str) -> dict[str, Any]:
    mode = normalize_mode(mode)
    timestamp = now_ist().isoformat()
    cleared = []
    if mode == "HFT":
        for path in (HFT_SCANNER_STATUS_PATH, HFT_MODE_SCANNER_STATUS_PATH):
            payload = read_json(path, {})
            if isinstance(payload, dict) and payload:
                payload["paper_trade_candidates"] = []
                payload["candidate_generation"] = "cleared_by_mode_switch"
                payload["signal_allowed"] = False
                payload["cleared_at_ist"] = timestamp
                atomic_write_json(path, payload)
                cleared.append(str(path.relative_to(ROOT)))
    else:
        for path in (CLASSIC_SCANNER_STATUS_PATH, CLASSIC_MODE_SCANNER_STATUS_PATH):
            payload = read_json(path, {})
            if isinstance(payload, dict) and payload:
                payload["signal_allowed"] = False
                payload["cleared_at_ist"] = timestamp
                atomic_write_json(path, payload)
                cleared.append(str(path.relative_to(ROOT)))
    result = {"status": "COMPLETE", "mode": mode, "cleared": cleared, "timestamp_ist": timestamp}
    atomic_write_json(MODE_SIGNAL_CLEAR_PATH, result)
    return result


def request_mode_switch(new_mode: str, *, old_mode: str, writer) -> dict[str, Any]:
    old_mode = normalize_mode(old_mode)
    new_mode = normalize_mode(new_mode)
    write_switch_status("SWITCH_REQUESTED", old_mode, new_mode, signal_allowed=False)
    try:
        write_switch_status("STOPPING_OLD_MODE", old_mode, new_mode, signal_allowed=False)
        write_switch_status("CLOSING_OLD_MODE_TRADES", old_mode, new_mode, signal_allowed=False)
        close_result = close_open_mode_trades(old_mode)
        if close_result.get("status") != "COMPLETE":
            return write_switch_status(
                "FAILED",
                old_mode,
                new_mode,
                signal_allowed=False,
                reason="unsafe_to_close_open_mode_trades",
                extra={"close_result": close_result},
            )

        write_switch_status("CLEARING_PENDING_SIGNALS", old_mode, new_mode, signal_allowed=False, extra={"close_result": close_result})
        clear_result = clear_pending_signals(old_mode)

        write_switch_status("STARTING_NEW_MODE", old_mode, new_mode, signal_allowed=False, extra={"close_result": close_result, "clear_result": clear_result})
        mode_payload = writer(new_mode)
        return write_switch_status(
            "COMPLETE",
            old_mode,
            new_mode,
            signal_allowed=True,
            reason=None,
            extra={"close_result": close_result, "clear_result": clear_result, "execution_mode": mode_payload},
        )
    except Exception as exc:
        return write_switch_status(
            "FAILED",
            old_mode,
            new_mode,
            signal_allowed=False,
            reason=f"{type(exc).__name__}:{exc}",
        )


def switch_mode(new_mode: str) -> dict[str, Any]:
    from runtime_execution_mode import write_execution_mode

    return write_execution_mode(new_mode, transactional=True)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(json.dumps(read_mode_switch_status(), indent=2, sort_keys=True))
        return 0
    payload = switch_mode(args[0])
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not payload.get("switch_failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
