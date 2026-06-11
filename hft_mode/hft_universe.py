"""Static simulation-safe HFT universe rules."""

from __future__ import annotations

from hft_mode.hft_candidate import MAX_PRICE, MIN_PRICE, PREFERRED_MAX_PRICE, PREFERRED_MIN_PRICE
from hft_mode.hft_data_contracts import HFTSymbolState

MIN_UNIVERSE_SIZE = 60
MAX_UNIVERSE_SIZE = 80

_STATIC_SYMBOLS = [
    ("HFTHYDRO01", 24.8, 620000),
    ("HFTGRID02", 24.6, 590000),
    ("HFTMETAL03", 24.3, 580000),
    ("HFTPOWER04", 24.0, 575000),
    ("HFTTEXT05", 23.8, 560000),
    ("HFTCHEM06", 23.6, 555000),
    ("HFTAUTO07", 23.4, 550000),
    ("HFTBANK08", 23.2, 545000),
    ("HFTFMCG09", 23.0, 540000),
    ("HFTINFRA10", 22.8, 535000),
    ("HFTENERGY11", 22.6, 530000),
    ("HFTCAP12", 22.4, 525000),
    ("HFTPIPE13", 22.2, 520000),
    ("HFTWIRE14", 22.0, 515000),
    ("HFTPORT15", 21.8, 510000),
    ("HFTMINE16", 21.6, 505000),
    ("HFTMOB17", 21.4, 500000),
    ("HFTFOOD18", 21.2, 495000),
    ("HFTCEM19", 21.0, 490000),
    ("HFTFERT20", 20.8, 485000),
    ("HFTPUMP21", 20.6, 480000),
    ("HFTCABLE22", 20.4, 475000),
    ("HFTPACK23", 20.2, 470000),
    ("HFTLOG24", 20.0, 465000),
    ("HFTRETAIL25", 19.8, 460000),
    ("HFTMEDIA26", 19.6, 455000),
    ("HFTREALTY27", 19.4, 450000),
    ("HFTSUGAR28", 19.2, 445000),
    ("HFTPAPER29", 19.0, 440000),
    ("HFTGAS30", 18.8, 435000),
    ("HFTSOLAR31", 18.6, 430000),
    ("HFTWIND32", 18.4, 425000),
    ("HFTFIBER33", 18.2, 420000),
    ("HFTSEED34", 18.0, 415000),
    ("HFTTOOLS35", 17.8, 410000),
    ("HFTGLASS36", 17.6, 405000),
    ("HFTCERAM37", 17.4, 400000),
    ("HFTPHARMA38", 17.2, 395000),
    ("HFTLAB39", 17.0, 390000),
    ("HFTPLAST40", 16.8, 385000),
    ("HFTPAINT41", 16.6, 380000),
    ("HFTTYRE42", 16.4, 375000),
    ("HFTRAIL43", 16.2, 370000),
    ("HFTSHIP44", 16.0, 365000),
    ("HFTAGRI45", 15.8, 360000),
    ("HFTCARBON46", 15.6, 355000),
    ("HFTSALT47", 15.4, 350000),
    ("HFTZINC48", 15.2, 345000),
    ("HFTCOPPER49", 15.1, 340000),
    ("HFTALLOY50", 20.5, 335000),
    ("HFTMOTOR51", 21.5, 330000),
    ("HFTVALVE52", 22.5, 325000),
    ("HFTGEAR53", 23.5, 320000),
    ("HFTBOLT54", 24.5, 315000),
    ("HFTNUT55", 19.5, 310000),
    ("HFTFAST56", 18.5, 305000),
    ("HFTCAST57", 17.5, 300000),
    ("HFTFORGE58", 16.5, 295000),
    ("HFTDRIVE59", 15.5, 290000),
    ("HFTNODE60", 20.1, 285000),
    ("HFTEDGE61", 20.3, 280000),
    ("HFTCORE62", 20.7, 275000),
    ("HFTBASE63", 21.1, 270000),
    ("HFTFLOW64", 21.3, 265000),
    ("HFTLINK65", 21.7, 260000),
]


def _symbol_state(symbol: str, price: float, volume: int) -> HFTSymbolState:
    return HFTSymbolState(
        symbol=symbol,
        price=price,
        volume=volume,
        bid=round(price - 0.02, 2),
        ask=round(price + 0.02, 2),
        spread_pct=round((0.04 / price) * 100, 6),
        source="static_simulation_universe",
        is_fresh=True,
        is_liquid=True,
        is_circuit_prone=False,
    )


def reject_reason_for_symbol(state: HFTSymbolState) -> str | None:
    if state.price is None or state.price < MIN_PRICE or state.price > MAX_PRICE:
        return "price_outside_15_25"
    if not state.is_liquid or state.volume is None or state.volume < 250000:
        return "illiquid"
    if state.is_circuit_prone:
        return "circuit_prone"
    return None


def get_static_hft_universe(limit: int = MAX_UNIVERSE_SIZE) -> list[HFTSymbolState]:
    safe_limit = max(0, min(limit, MAX_UNIVERSE_SIZE))
    states = [_symbol_state(symbol, price, volume) for symbol, price, volume in _STATIC_SYMBOLS]
    accepted = [state for state in states if reject_reason_for_symbol(state) is None]
    accepted.sort(key=lambda state: (not (PREFERRED_MIN_PRICE <= state.price <= PREFERRED_MAX_PRICE), -state.volume))
    return accepted[:safe_limit]
