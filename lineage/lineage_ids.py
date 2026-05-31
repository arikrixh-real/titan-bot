"""Deterministic lineage ID helpers.

These helpers only create forward-compatible identifiers. They do not read,
write, rank, filter, trade, or influence runtime decisions.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


SETUP_ID_VERSION = "setup_id.v1"


def _clean_token(value: Any, fallback: str = "NA") -> str:
    text = str(value or "").strip().upper()
    if not text:
        text = fallback
    text = re.sub(r"[^A-Z0-9]+", "_", text).strip("_")
    return text or fallback


def _stable_hash(payload: dict[str, Any], length: int = 12) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def build_setup_id_record(
    *,
    symbol: Any,
    side: Any = None,
    direction: Any = None,
    setup_type: Any = None,
    timestamp: Any = None,
    scanner_cycle_id: Any = None,
    source: Any = None,
    entry: Any = None,
    stop_loss: Any = None,
    target: Any = None,
    final_score: Any = None,
) -> dict[str, Any]:
    """Return setup_id plus source fields for a setup record."""

    normalized_symbol = _clean_token(symbol, "UNKNOWN")
    normalized_side = _clean_token(side or direction, "NA")
    normalized_time = _clean_token(timestamp or scanner_cycle_id, "NO_TIME")
    source_fields = {
        "version": SETUP_ID_VERSION,
        "symbol": normalized_symbol,
        "side": normalized_side,
        "setup_type": _clean_token(setup_type, "UNKNOWN"),
        "timestamp": str(timestamp or ""),
        "scanner_cycle_id": str(scanner_cycle_id or ""),
        "source": str(source or ""),
        "entry": str(entry or ""),
        "stop_loss": str(stop_loss or ""),
        "target": str(target or ""),
        "final_score": str(final_score or ""),
    }
    short_hash = _stable_hash(source_fields)
    return {
        "setup_id": f"setup_{normalized_symbol}_{normalized_side}_{normalized_time}_{short_hash}",
        "setup_id_hash": short_hash,
        "setup_id_source": source or "UNKNOWN",
        "setup_id_source_fields": source_fields,
    }


def is_valid_setup_id(value: Any) -> bool:
    text = str(value or "")
    return bool(re.fullmatch(r"setup_[A-Z0-9_]+_(BUY|SELL|LONG|SHORT|NA)_[A-Z0-9_]+_[a-f0-9]{12}", text))
