from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List


NEURAL_SCHEMA_VERSION = "neural_schema_v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_warnings(warnings: Any) -> List[str]:
    if warnings is None:
        return []
    if isinstance(warnings, str):
        return [warnings]
    if isinstance(warnings, Iterable) and not isinstance(warnings, (dict, bytes)):
        return [str(item) for item in warnings if item is not None]
    return [str(warnings)]


def neural_packet(
    *,
    source: str,
    timestamp: str | None = None,
    freshness: Dict[str, Any] | None = None,
    confidence: float | None = None,
    risk: str = "UNKNOWN",
    warnings: Any = None,
    memory_type: str = "ADVISORY",
    trust_level: str = "UNVERIFIED",
    validation_status: str = "UNVALIDATED",
    action_permission: str = "READ_ONLY",
    live_apply_allowed: bool = False,
    payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Standard envelope for cross-brain advisory packets.

    This is a schema helper only. It does not score, rank, mutate live strategy,
    place orders, or promote any recommendation.
    """

    packet = {
        "schema_version": NEURAL_SCHEMA_VERSION,
        "source": str(source),
        "timestamp": timestamp or utc_now_iso(),
        "freshness": deepcopy(freshness) if isinstance(freshness, dict) else {},
        "confidence": confidence,
        "risk": str(risk or "UNKNOWN").upper(),
        "warnings": normalize_warnings(warnings),
        "memory_type": str(memory_type or "ADVISORY").upper(),
        "trust_level": str(trust_level or "UNVERIFIED").upper(),
        "validation_status": str(validation_status or "UNVALIDATED").upper(),
        "action_permission": str(action_permission or "READ_ONLY").upper(),
        "live_apply_allowed": bool(live_apply_allowed),
    }
    if payload is not None:
        packet["payload"] = deepcopy(payload) if isinstance(payload, dict) else payload
    return packet
