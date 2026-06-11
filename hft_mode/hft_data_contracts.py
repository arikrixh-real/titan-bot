"""Data contracts for the isolated HFT simulation input layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class HFTSymbolState:
    symbol: str
    price: float | None = None
    timestamp: datetime | None = None
    volume: int | None = None
    bid: float | None = None
    ask: float | None = None
    spread_pct: float | None = None
    source: str = "simulation"
    is_fresh: bool = False
    reason_if_rejected: str | None = None
    is_liquid: bool = False
    is_circuit_prone: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HFTPriceTick:
    symbol: str
    price: float | None
    timestamp: datetime
    volume: int | None = None
    bid: float | None = None
    ask: float | None = None
    spread_pct: float | None = None
    source: str = "simulation"
    is_fresh: bool = False
    reason_if_rejected: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HFTCandidate:
    symbol: str
    price: float
    timestamp: datetime
    volume: int
    bid: float
    ask: float
    spread_pct: float
    source: str = "simulation"
    is_fresh: bool = True
    reason_if_rejected: str | None = None
    strategy_name: str | None = None
    momentum_strength: float = 0.0
    volume_strength: float = 0.0
    volatility_quality: float = 0.0
    spread_quality: float = 0.0
    speed_of_move: float = 0.0
    strategy_confidence: float = 0.0
    setup_cleanliness: float = 0.0
    score: float = 0.0
    eligible: bool = False
    executable: bool = False
    signal_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HFTFeedSnapshot:
    symbol: str
    price: float | None
    timestamp: datetime | None
    volume: int | None
    bid: float | None
    ask: float | None
    spread_pct: float | None
    source: str = "simulation"
    is_fresh: bool = False
    reason_if_rejected: str | None = None
    accepted: bool = False
    candidates: tuple[HFTCandidate, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
