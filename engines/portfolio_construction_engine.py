"""
TITAN Phase 2 - Portfolio Construction Intelligence
---------------------------------------------------

Research-only portfolio quality proxies from cached OHLCV and local journals.
No broker positions, order placement, or live execution is used here.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable

import pandas as pd

try:
    from engines.pro_risk_engine import sector_for_symbol
except Exception:
    def sector_for_symbol(symbol: Any) -> str:
        return "UNKNOWN"


CACHE_DIR = Path("data/cache")
ACTIVE_TRADE_FILES = [
    Path("data/journals/active_trades.csv"),
    Path("active_trades.csv"),
]
MARKET_SYMBOLS = ["^NSEI", "NIFTYBEES"]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def normalize_symbol(symbol: Any) -> str:
    return str(symbol or "").replace(".NS", "").strip().upper()


def _neutral(reason: str = "portfolio_data_unavailable") -> Dict[str, Any]:
    return {
        "available": False,
        "sector": "UNKNOWN",
        "sector_exposure_score": 50.0,
        "portfolio_concentration_risk": 50.0,
        "correlation_proxy": 0.0,
        "beta_like_market_sensitivity": 1.0,
        "volatility_contribution_score": 50.0,
        "portfolio_quality_score": 50.0,
        "open_trade_count": 0,
        "same_sector_open_count": 0,
        "portfolio_risk_warnings": [reason],
    }


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []

    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _open_trade_rows() -> list[dict[str, Any]]:
    rows = []
    seen = set()
    files_to_read = ACTIVE_TRADE_FILES

    if ACTIVE_TRADE_FILES and ACTIVE_TRADE_FILES[0].exists():
        files_to_read = [ACTIVE_TRADE_FILES[0]]

    for path in files_to_read:
        for row in _read_csv_rows(path):
            status = str(row.get("status", "")).upper().strip()
            if status not in {"OPEN", "ACTIVE", "LIVE"}:
                continue

            symbol = normalize_symbol(row.get("symbol"))
            side = str(row.get("side", "")).upper().strip()
            key = f"{symbol}|{side}"

            if not symbol or key in seen:
                continue

            seen.add(key)
            rows.append(row)

    return rows


def _clean_df(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None

    clean = df.copy()
    clean.columns = [str(col).strip() for col in clean.columns]

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in clean.columns:
            clean[col] = pd.to_numeric(clean[col], errors="coerce")

    if "Close" not in clean.columns:
        return None

    clean = clean.dropna(subset=["Close"])
    if clean.empty:
        return None

    return clean


def _load_cached_df(symbol: Any) -> pd.DataFrame | None:
    symbol_key = normalize_symbol(symbol)
    if not symbol_key:
        return None

    possible = [
        CACHE_DIR / f"{symbol_key}.csv",
        CACHE_DIR / f"{symbol_key}.NS.csv",
    ]

    for path in possible:
        if not path.exists():
            continue

        try:
            return _clean_df(pd.read_csv(path))
        except Exception:
            return None

    return None


def _load_market_df() -> pd.DataFrame | None:
    for symbol in MARKET_SYMBOLS:
        df = _load_cached_df(symbol)
        if df is not None and len(df) >= 20:
            return df
    return None


def _returns(df: pd.DataFrame | None, window: int = 30) -> pd.Series:
    clean = _clean_df(df)
    if clean is None or len(clean) < 3:
        return pd.Series(dtype="float64")

    return clean["Close"].pct_change().dropna().tail(window)


def _aligned_correlation(a: pd.Series, b: pd.Series) -> float | None:
    if a.empty or b.empty:
        return None

    size = min(len(a), len(b))
    if size < 8:
        return None

    left = a.tail(size).reset_index(drop=True)
    right = b.tail(size).reset_index(drop=True)
    corr = left.corr(right)

    if pd.isna(corr):
        return None

    return _safe_float(corr)


def _volatility(returns: pd.Series) -> float | None:
    if returns.empty or len(returns) < 5:
        return None
    value = returns.std()
    if pd.isna(value):
        return None
    return _safe_float(value)


def _beta_like(stock_returns: pd.Series, market_returns: pd.Series) -> float | None:
    size = min(len(stock_returns), len(market_returns))
    if size < 10:
        return None

    stock = stock_returns.tail(size).reset_index(drop=True)
    market = market_returns.tail(size).reset_index(drop=True)
    market_var = market.var()

    if pd.isna(market_var) or market_var <= 0:
        return None

    cov = stock.cov(market)
    if pd.isna(cov):
        return None

    return _safe_float(cov / market_var, 1.0)


def _sector_counts(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {}
    for row in rows:
        sector = sector_for_symbol(row.get("symbol"))
        counts[sector] = counts.get(sector, 0) + 1
    return counts


def analyze_portfolio_construction(
    setup: Dict[str, Any],
    df: pd.DataFrame | None,
    active_rows: list[dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    Returns portfolio construction metadata.

    Scores are 0-100 where higher is better, except risk/warning fields.
    """

    if not isinstance(setup, dict):
        return _neutral("invalid_setup")

    symbol = normalize_symbol(setup.get("symbol"))
    sector = sector_for_symbol(symbol)
    active_rows = _open_trade_rows() if active_rows is None else active_rows

    candidate_returns = _returns(df)
    if candidate_returns.empty or len(candidate_returns) < 8:
        result = _neutral("portfolio_return_data_unavailable")
        result["sector"] = sector
        result["open_trade_count"] = len(active_rows)
        return result

    open_count = len(active_rows)
    sector_counts = _sector_counts(active_rows)
    same_sector_open_count = sector_counts.get(sector, 0) if sector != "UNKNOWN" else 0

    sector_exposure_score = _clamp(100.0 - (same_sector_open_count * 18.0))

    symbol_repeats = sum(1 for row in active_rows if normalize_symbol(row.get("symbol")) == symbol)
    portfolio_concentration_risk = _clamp(
        (open_count * 4.0)
        + (same_sector_open_count * 16.0)
        + (symbol_repeats * 28.0)
    )

    correlations = []
    active_vols = []

    for row in active_rows:
        active_symbol = normalize_symbol(row.get("symbol"))
        if not active_symbol or active_symbol == symbol:
            continue

        active_df = _load_cached_df(active_symbol)
        active_returns = _returns(active_df)
        corr = _aligned_correlation(candidate_returns, active_returns)
        if corr is not None:
            correlations.append(corr)

        vol = _volatility(active_returns)
        if vol is not None:
            active_vols.append(vol)

    positive_corrs = [max(0.0, value) for value in correlations]
    correlation_proxy = sum(positive_corrs) / len(positive_corrs) if positive_corrs else 0.0

    market_returns = _returns(_load_market_df())
    beta = _beta_like(candidate_returns, market_returns)
    if beta is None:
        beta = 1.0

    candidate_vol = _volatility(candidate_returns)
    avg_active_vol = sum(active_vols) / len(active_vols) if active_vols else candidate_vol

    if candidate_vol is None or avg_active_vol is None or avg_active_vol <= 0:
        volatility_contribution_score = 50.0
        vol_ratio = 1.0
    else:
        vol_ratio = candidate_vol / avg_active_vol
        volatility_contribution_score = _clamp(100.0 - abs(vol_ratio - 1.0) * 45.0)
        if vol_ratio > 1.4:
            volatility_contribution_score = _clamp(volatility_contribution_score - ((vol_ratio - 1.4) * 35.0))

    beta_quality = _clamp(100.0 - max(0.0, abs(beta) - 1.0) * 35.0)
    correlation_quality = _clamp(100.0 - correlation_proxy * 60.0)
    concentration_quality = _clamp(100.0 - portfolio_concentration_risk)

    portfolio_quality_score = _clamp(
        (sector_exposure_score * 0.25)
        + (concentration_quality * 0.25)
        + (correlation_quality * 0.20)
        + (beta_quality * 0.15)
        + (volatility_contribution_score * 0.15)
    )

    warnings = []
    if same_sector_open_count >= 2:
        warnings.append("sector_crowding")
    if portfolio_concentration_risk >= 60:
        warnings.append("portfolio_concentration_risk")
    if correlation_proxy >= 0.65:
        warnings.append("high_correlation_proxy")
    if abs(beta) >= 1.6:
        warnings.append("high_beta_like_market_sensitivity")
    if vol_ratio >= 1.5:
        warnings.append("high_volatility_contribution")

    return {
        "available": True,
        "sector": sector,
        "sector_exposure_score": round(sector_exposure_score, 2),
        "portfolio_concentration_risk": round(portfolio_concentration_risk, 2),
        "correlation_proxy": round(correlation_proxy, 4),
        "beta_like_market_sensitivity": round(beta, 4),
        "volatility_contribution_score": round(volatility_contribution_score, 2),
        "portfolio_quality_score": round(portfolio_quality_score, 2),
        "open_trade_count": open_count,
        "same_sector_open_count": same_sector_open_count,
        "candidate_volatility": round(candidate_vol or 0.0, 6),
        "active_avg_volatility": round(avg_active_vol or 0.0, 6),
        "volatility_ratio": round(vol_ratio, 4),
        "portfolio_risk_warnings": warnings,
    }
