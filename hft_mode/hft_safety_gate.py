"""Hard-deny gates for the sealed HFT foundation."""

from __future__ import annotations

from hft_mode import hft_config


class HFTSafetyError(PermissionError):
    """Raised when HFT code attempts a forbidden integration."""


def hft_is_enabled() -> bool:
    return hft_config.HFT_ENABLED


def assert_hft_simulation_only() -> None:
    if hft_config.HFT_ENABLED or hft_config.MODE != "SIMULATION_ONLY":
        raise HFTSafetyError("HFT mode must remain disabled and simulation-only")


def assert_live_trade_allowed() -> None:
    raise HFTSafetyError("HFT live trade placement is disabled")


def assert_broker_allowed() -> None:
    if not hft_config.BROKER_ALLOWED:
        raise HFTSafetyError("HFT broker access is disabled")


def assert_telegram_allowed() -> None:
    if not hft_config.TELEGRAM_ALLOWED:
        raise HFTSafetyError("HFT Telegram access is disabled")


def assert_classic_memory_write_allowed() -> None:
    if not hft_config.CLASSIC_MEMORY_WRITE_ALLOWED:
        raise HFTSafetyError("HFT writes to TITAN memory are disabled")


def assert_classic_journal_write_allowed() -> None:
    if not hft_config.CLASSIC_JOURNAL_WRITE_ALLOWED:
        raise HFTSafetyError("HFT writes to Classic journals are disabled")


def assert_master_brain_access_allowed() -> None:
    if not hft_config.MASTER_BRAIN_ACCESS_ALLOWED:
        raise HFTSafetyError("HFT Master Brain access is disabled")


def assert_titan_evolution_write_allowed() -> None:
    if not hft_config.TITAN_EVOLUTION_WRITE_ALLOWED:
        raise HFTSafetyError("HFT writes to TITAN evolution are disabled")


def assert_runtime_connection_allowed() -> None:
    if not hft_config.ACTIVE_RUNTIME_CONNECTION_ALLOWED:
        raise HFTSafetyError("HFT daemon/runtime connection is disabled")


def safety_snapshot() -> dict[str, object]:
    return {
        "hft_enabled": hft_config.HFT_ENABLED,
        "mode": hft_config.MODE,
        "broker_allowed": hft_config.BROKER_ALLOWED,
        "telegram_allowed": hft_config.TELEGRAM_ALLOWED,
        "classic_memory_write_allowed": hft_config.CLASSIC_MEMORY_WRITE_ALLOWED,
        "classic_journal_write_allowed": hft_config.CLASSIC_JOURNAL_WRITE_ALLOWED,
        "master_brain_access_allowed": hft_config.MASTER_BRAIN_ACCESS_ALLOWED,
        "titan_evolution_write_allowed": hft_config.TITAN_EVOLUTION_WRITE_ALLOWED,
        "active_runtime_connection_allowed": hft_config.ACTIVE_RUNTIME_CONNECTION_ALLOWED,
    }
