"""
TITAN Phase 27 - Options Flow Intelligence
------------------------------------------

Options-chain aware flow analyzer. Uses real strikes/call/put/OI/IV data when
available, proxy market context when not, and neutral insufficient mode when
there is no useful input. It never places orders or enables live execution.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List


REPORT_PATH = Path("data/options_flow/latest_options_flow_report.json")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        result = float(value)
        if not math.isfinite(result):
            return default
        return result
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def safe_text(value: Any, default: str = "") -> str:
    try:
        if value is None:
            return default
        text = str(value).strip()
        return text if text else default
    except Exception:
        return default


def safe_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def clamp(value: Any, min_value: float = 0.0, max_value: float = 100.0) -> float:
    low = safe_float(min_value, 0.0)
    high = safe_float(max_value, 100.0)
    if low > high:
        low, high = high, low
    return max(low, min(high, safe_float(value, low)))


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first(data: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for key in keys:
        if key in data and data.get(key) is not None:
            return data.get(key)
    return default


def _option_side(raw: Any) -> Dict[str, float]:
    data = _dict(raw)
    return {
        "oi": safe_float(_first(data, ["oi", "open_interest", "openInterest", "OI"]), 0.0),
        "oi_change": safe_float(_first(data, ["oi_change", "change_oi", "changeInOI", "change_in_oi", "oiChange"]), 0.0),
        "iv": safe_float(_first(data, ["iv", "implied_volatility", "impliedVolatility", "IV"]), 0.0),
        "volume": safe_float(_first(data, ["volume", "vol", "traded_volume", "totalTradedVolume"]), 0.0),
        "ltp": safe_float(_first(data, ["ltp", "last_price", "lastPrice", "price"]), 0.0),
    }


def _row_from_mapping(row: Dict[str, Any]) -> Dict[str, Any]:
    call = row.get("call") or row.get("calls") or row.get("CE") or row.get("ce") or {}
    put = row.get("put") or row.get("puts") or row.get("PE") or row.get("pe") or {}
    strike = safe_float(_first(row, ["strike", "strike_price", "strikePrice", "sp"]), 0.0)
    return {"strike": strike, "call": _option_side(call), "put": _option_side(put)}


def _extract_rows(option_chain: Any) -> List[Any]:
    if isinstance(option_chain, list):
        return option_chain
    data = _dict(option_chain)
    for key in ("strikes", "data", "records", "option_chain", "chain", "items"):
        rows = data.get(key)
        if isinstance(rows, list):
            return rows
        if isinstance(rows, dict) and isinstance(rows.get("data"), list):
            return rows.get("data")
    if isinstance(data.get("records"), dict) and isinstance(data["records"].get("data"), list):
        return data["records"]["data"]
    return []


def normalize_option_chain(option_chain: Any = None) -> Dict[str, Any]:
    rows = []
    for row in _extract_rows(option_chain):
        if isinstance(row, dict):
            normalized = _row_from_mapping(row)
        elif isinstance(row, (list, tuple)):
            normalized = {
                "strike": safe_float(row[0] if len(row) > 0 else 0.0),
                "call": _option_side(row[1] if len(row) > 1 else {}),
                "put": _option_side(row[2] if len(row) > 2 else {}),
            }
        else:
            continue
        if normalized["strike"] > 0 and (normalized["call"]["oi"] > 0 or normalized["put"]["oi"] > 0):
            rows.append(normalized)

    rows.sort(key=lambda item: item["strike"])
    meta = _dict(option_chain)
    return {
        "strikes": rows,
        "available": bool(rows),
        "underlying_price": safe_float(
            _first(meta, ["underlying_price", "underlyingValue", "spot", "spot_price", "last_price", "price"]),
            0.0,
        ),
        "expiry": safe_text(_first(meta, ["expiry", "expiry_date", "expiryDate"]), ""),
        "symbol": safe_text(_first(meta, ["symbol", "underlying", "name"]), ""),
    }


def calculate_pcr(option_chain: Any = None) -> Dict[str, Any]:
    chain = normalize_option_chain(option_chain)
    put_oi = sum(row["put"]["oi"] for row in chain["strikes"])
    call_oi = sum(row["call"]["oi"] for row in chain["strikes"])
    pcr = put_oi / call_oi if call_oi > 0 else 0.0
    if pcr >= 1.15:
        bias = "BULLISH"
    elif pcr <= 0.80 and pcr > 0:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"
    return {"pcr": round(pcr, 3), "put_oi": round(put_oi, 2), "call_oi": round(call_oi, 2), "bias": bias}


def analyze_oi_buildup(option_chain: Any = None, setup: Any = None, context: Any = None) -> Dict[str, Any]:
    chain = normalize_option_chain(option_chain)
    call_change = sum(row["call"]["oi_change"] for row in chain["strikes"])
    put_change = sum(row["put"]["oi_change"] for row in chain["strikes"])
    delta = put_change - call_change
    score = clamp(50.0 + delta / max(abs(call_change) + abs(put_change), 1.0) * 50.0)
    return {
        "score": round(score, 2),
        "bias": "BULLISH" if score >= 58 else "BEARISH" if score <= 42 else "NEUTRAL",
        "call_oi_change": round(call_change, 2),
        "put_oi_change": round(put_change, 2),
    }


def detect_iv_spikes(option_chain: Any = None, context: Any = None) -> Dict[str, Any]:
    chain = normalize_option_chain(option_chain)
    ivs = [side["iv"] for row in chain["strikes"] for side in (row["call"], row["put"]) if side["iv"] > 0]
    avg_iv = sum(ivs) / len(ivs) if ivs else safe_float(_dict(context).get("iv") or _dict(context).get("india_vix") or _dict(context).get("vix"), 0.0)
    baseline = safe_float(_dict(context).get("avg_iv") or _dict(context).get("normal_iv") or _dict(context).get("vix_baseline"), 18.0)
    spike_score = clamp((avg_iv - baseline) * 4.0)
    return {"active": spike_score >= 35.0, "avg_iv": round(avg_iv, 2), "spike_score": round(spike_score, 2)}


def calculate_max_pain(option_chain: Any = None) -> Dict[str, Any]:
    chain = normalize_option_chain(option_chain)
    strikes = chain["strikes"]
    if not strikes:
        return {"max_pain": 0.0, "available": False}
    best_strike = 0.0
    best_pain = None
    for candidate in strikes:
        strike_price = candidate["strike"]
        pain = 0.0
        for row in strikes:
            pain += max(0.0, strike_price - row["strike"]) * row["call"]["oi"]
            pain += max(0.0, row["strike"] - strike_price) * row["put"]["oi"]
        if best_pain is None or pain < best_pain:
            best_pain = pain
            best_strike = strike_price
    return {"max_pain": round(best_strike, 2), "available": True, "pain_value": round(safe_float(best_pain), 2)}


def analyze_call_put_writing_pressure(option_chain: Any = None, setup: Any = None) -> Dict[str, Any]:
    buildup = analyze_oi_buildup(option_chain, setup)
    call_change = safe_float(buildup.get("call_oi_change"))
    put_change = safe_float(buildup.get("put_oi_change"))
    pressure = "PUT_WRITING" if put_change > call_change * 1.15 and put_change > 0 else "CALL_WRITING" if call_change > put_change * 1.15 and call_change > 0 else "MIXED"
    bias = "BULLISH" if pressure == "PUT_WRITING" else "BEARISH" if pressure == "CALL_WRITING" else "NEUTRAL"
    return {"pressure": pressure, "bias": bias, "score": buildup.get("score", 50.0)}


def estimate_gamma_exposure_proxy(option_chain: Any = None, setup: Any = None) -> Dict[str, Any]:
    chain = normalize_option_chain(option_chain)
    spot = chain["underlying_price"] or safe_float(_dict(setup).get("entry") or _dict(setup).get("price"), 0.0)
    if not chain["strikes"] or spot <= 0:
        return {"gamma_proxy_score": 50.0, "pin_risk": False, "nearest_strike": 0.0}
    nearest = min(chain["strikes"], key=lambda row: abs(row["strike"] - spot))
    oi_near = nearest["call"]["oi"] + nearest["put"]["oi"]
    total_oi = sum(row["call"]["oi"] + row["put"]["oi"] for row in chain["strikes"])
    concentration = oi_near / max(total_oi, 1.0) * 100.0
    score = clamp(50.0 + concentration * 1.2)
    return {"gamma_proxy_score": round(score, 2), "pin_risk": concentration >= 18.0, "nearest_strike": nearest["strike"]}


def detect_strike_concentration(option_chain: Any = None) -> Dict[str, Any]:
    chain = normalize_option_chain(option_chain)
    if not chain["strikes"]:
        return {"active": False, "score": 0.0, "strike": 0.0}
    total_oi = sum(row["call"]["oi"] + row["put"]["oi"] for row in chain["strikes"])
    top = max(chain["strikes"], key=lambda row: row["call"]["oi"] + row["put"]["oi"])
    share = (top["call"]["oi"] + top["put"]["oi"]) / max(total_oi, 1.0) * 100.0
    return {"active": share >= 22.0, "score": round(clamp(share * 3.0), 2), "strike": top["strike"], "oi_share_pct": round(share, 2)}


def analyze_expiry_day_behavior(option_chain: Any = None, context: Any = None) -> Dict[str, Any]:
    ctx = _dict(context)
    days = safe_int(ctx.get("days_to_expiry") or ctx.get("dte"), -1)
    is_expiry = bool(ctx.get("is_expiry_day") or days == 0)
    iv = detect_iv_spikes(option_chain, ctx)
    risk = clamp((35.0 if is_expiry else 0.0) + safe_float(iv.get("spike_score")) * 0.55)
    return {"is_expiry_day": is_expiry, "days_to_expiry": days, "risk_score": round(risk, 2), "warning": "WAIT" if risk >= 55 else "NONE"}


def detect_unusual_options_activity(option_chain: Any = None, context: Any = None) -> Dict[str, Any]:
    chain = normalize_option_chain(option_chain)
    volumes = [row["call"]["volume"] + row["put"]["volume"] for row in chain["strikes"]]
    avg_volume = sum(volumes) / len(volumes) if volumes else 0.0
    top_volume = max(volumes) if volumes else safe_float(_dict(context).get("options_volume_ratio"), 0.0) * 100.0
    score = clamp((top_volume / max(avg_volume, 1.0) - 1.0) * 25.0 if avg_volume else top_volume)
    return {"active": score >= 45.0, "score": round(score, 2), "top_volume": round(top_volume, 2)}


def infer_dealer_positioning(option_chain: Any = None, setup: Any = None) -> Dict[str, Any]:
    pcr = calculate_pcr(option_chain)
    gamma = estimate_gamma_exposure_proxy(option_chain, setup)
    concentration = detect_strike_concentration(option_chain)
    if pcr["bias"] == "BULLISH" and not gamma.get("pin_risk"):
        positioning = "SUPPORTIVE"
    elif pcr["bias"] == "BEARISH" and not gamma.get("pin_risk"):
        positioning = "RESISTIVE"
    elif gamma.get("pin_risk") or concentration.get("active"):
        positioning = "PINNED"
    else:
        positioning = "MIXED"
    return {"positioning": positioning, "pcr": pcr.get("pcr"), "pin_risk": gamma.get("pin_risk")}


def detect_options_driven_squeeze(option_chain: Any = None, setup: Any = None, context: Any = None) -> Dict[str, Any]:
    unusual = detect_unusual_options_activity(option_chain, context)
    iv = detect_iv_spikes(option_chain, context)
    buildup = analyze_oi_buildup(option_chain, setup, context)
    side = safe_text(_dict(setup).get("side") or _dict(setup).get("direction"), "").upper()
    aligned = (side == "LONG" and buildup.get("bias") == "BULLISH") or (side == "SHORT" and buildup.get("bias") == "BEARISH")
    score = clamp(safe_float(unusual.get("score")) * 0.45 + safe_float(iv.get("spike_score")) * 0.35 + (20.0 if aligned else 0.0))
    return {"active": score >= 50.0, "score": round(score, 2), "aligned_with_setup": aligned}


def _proxy_report(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    side = safe_text(setup.get("side") or setup.get("direction"), "").upper()
    price_pressure = safe_float(context.get("price_pressure") or context.get("change_pct") or context.get("price_change_pct"), 0.0)
    volume_ratio = safe_float(context.get("volume_ratio") or context.get("relative_volume"), 1.0)
    vix = safe_float(context.get("india_vix") or context.get("vix"), 0.0)
    expiry_known = bool(context.get("expiry") or context.get("days_to_expiry") is not None or context.get("is_expiry_day"))
    directional = price_pressure if side != "SHORT" else -price_pressure
    score = clamp(50.0 + directional * 10.0 + (volume_ratio - 1.0) * 8.0 - max(0.0, vix - 22.0) * 0.8)
    warning = "REVIEW" if vix >= 24.0 or context.get("is_expiry_day") else "NONE"
    explanations = ["No usable option chain found; using expiry/VIX/volume/price proxy."]
    if expiry_known:
        explanations.append("Expiry context is available for proxy options-flow risk.")
    return {
        "score": round(score, 2),
        "bias": "BULLISH" if score >= 58 else "BEARISH" if score <= 42 else "NEUTRAL",
        "warning": warning,
        "explanations": explanations,
    }


def analyze_option_chain(option_chain: Any = None, setup: Any = None, context: Any = None) -> Dict[str, Any]:
    chain = normalize_option_chain(option_chain)
    ctx = _dict(context)
    setup_data = _dict(setup)
    if chain["available"]:
        pcr = calculate_pcr(option_chain)
        buildup = analyze_oi_buildup(option_chain, setup_data, ctx)
        writing = analyze_call_put_writing_pressure(option_chain, setup_data)
        iv = detect_iv_spikes(option_chain, ctx)
        max_pain = calculate_max_pain(option_chain)
        gamma = estimate_gamma_exposure_proxy(option_chain, setup_data)
        concentration = detect_strike_concentration(option_chain)
        expiry = analyze_expiry_day_behavior(option_chain, ctx)
        unusual = detect_unusual_options_activity(option_chain, ctx)
        dealer = infer_dealer_positioning(option_chain, setup_data)
        squeeze = detect_options_driven_squeeze(option_chain, setup_data, ctx)
        score = clamp(
            safe_float(buildup.get("score")) * 0.28
            + (65.0 if pcr.get("bias") == "BULLISH" else 35.0 if pcr.get("bias") == "BEARISH" else 50.0) * 0.18
            + safe_float(writing.get("score")) * 0.18
            + (100.0 - safe_float(expiry.get("risk_score"))) * 0.12
            + safe_float(unusual.get("score")) * 0.10
            + safe_float(gamma.get("gamma_proxy_score")) * 0.08
            + (100.0 - safe_float(iv.get("spike_score"))) * 0.06
        )
        warning = "NONE"
        if expiry.get("warning") == "WAIT" or iv.get("spike_score", 0) >= 70:
            warning = "WAIT"
        if concentration.get("score", 0) >= 80 and squeeze.get("active"):
            warning = "REVIEW"
        explanations = [
            "Real option-chain strikes/OI/IV were used.",
            f"PCR bias: {pcr.get('bias')} at {pcr.get('pcr')}.",
            f"OI buildup bias: {buildup.get('bias')}.",
        ]
        if max_pain.get("available"):
            explanations.append(f"Max pain estimated near {max_pain.get('max_pain')}.")
        return {
            "data_mode": "REAL_OPTIONS",
            "score": round(score, 2),
            "bias": "BULLISH" if score >= 58 else "BEARISH" if score <= 42 else "NEUTRAL",
            "warning": warning,
            "pcr": pcr,
            "oi_buildup": buildup,
            "iv_spikes": iv,
            "max_pain": max_pain,
            "writing_pressure": writing,
            "gamma_exposure_proxy": gamma,
            "strike_concentration": concentration,
            "expiry_behavior": expiry,
            "unusual_activity": unusual,
            "dealer_positioning": dealer,
            "options_squeeze": squeeze,
            "explanations": explanations,
        }
    if ctx and any(ctx.get(key) is not None for key in ("expiry", "days_to_expiry", "is_expiry_day", "india_vix", "vix", "volume_ratio", "relative_volume", "price_pressure", "change_pct", "price_change_pct")):
        proxy = _proxy_report(setup_data, ctx)
        return {"data_mode": "PROXY", **proxy}
    return {
        "data_mode": "INSUFFICIENT",
        "score": 50.0,
        "bias": "NEUTRAL",
        "warning": "REVIEW",
        "explanations": ["No useful option-chain or proxy context available; score kept neutral."],
    }


def build_options_flow_report(setup: Any = None, option_chain: Any = None, context: Any = None) -> Dict[str, Any]:
    setup_data = _dict(setup)
    ctx = _dict(context)
    raw = _dict(setup_data.get("raw"))
    if option_chain is None:
        option_chain = setup_data.get("option_chain") or raw.get("option_chain") or ctx.get("option_chain")
        symbol = safe_text(setup_data.get("symbol") or raw.get("symbol") or setup_data.get("stock") or raw.get("stock"), "").upper()
        chains = ctx.get("option_chains")
        if option_chain is None and isinstance(chains, dict) and symbol:
            option_chain = chains.get(symbol) or chains.get(symbol.upper()) or chains.get(symbol.lower())

    analysis = analyze_option_chain(option_chain, setup_data, ctx)
    symbol = safe_text(
        setup_data.get("symbol")
        or raw.get("symbol")
        or setup_data.get("stock")
        or raw.get("stock")
        or normalize_option_chain(option_chain).get("symbol"),
        "UNKNOWN",
    ).upper()
    report = {
        "symbol": symbol,
        "data_mode": analysis.get("data_mode", "INSUFFICIENT"),
        "options_flow_score": round(clamp(analysis.get("score", 50.0)), 2),
        "options_flow_bias": analysis.get("bias", "NEUTRAL"),
        "options_warning": analysis.get("warning", "REVIEW"),
        "live_order_allowed": False,
        "explanations": safe_list(analysis.get("explanations"))[:8],
        "details": {key: value for key, value in analysis.items() if key not in {"score", "bias", "warning", "explanations"}},
    }
    try:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return report


if __name__ == "__main__":
    sample_chain = {
        "symbol": "NIFTY",
        "underlying_price": 22540,
        "expiry": "2026-05-14",
        "strikes": [
            {"strike": 22400, "CE": {"openInterest": 12000, "changeInOI": 500, "impliedVolatility": 13.5, "totalTradedVolume": 1000}, "PE": {"openInterest": 18000, "changeInOI": 2500, "impliedVolatility": 14.1, "totalTradedVolume": 1800}},
            {"strike": 22500, "CE": {"openInterest": 22000, "changeInOI": 1000, "impliedVolatility": 14.0, "totalTradedVolume": 2200}, "PE": {"openInterest": 26000, "changeInOI": 3200, "impliedVolatility": 14.4, "totalTradedVolume": 2800}},
            {"strike": 22600, "CE": {"openInterest": 28000, "changeInOI": 2200, "impliedVolatility": 14.8, "totalTradedVolume": 2600}, "PE": {"openInterest": 14000, "changeInOI": 700, "impliedVolatility": 14.2, "totalTradedVolume": 900}},
        ],
    }
    real_report = build_options_flow_report({"symbol": "NIFTY", "side": "LONG", "entry": 22540}, sample_chain, {"days_to_expiry": 4, "avg_iv": 13.0})
    proxy_report = build_options_flow_report({"symbol": "RELIANCE", "side": "LONG"}, None, {"india_vix": 16.5, "volume_ratio": 1.6, "change_pct": 0.8, "days_to_expiry": 3})
    insufficient_report = build_options_flow_report({"symbol": "TCS"}, None, {})
    print(json.dumps({"real_options": real_report, "proxy": proxy_report, "insufficient": insufficient_report}, indent=2, sort_keys=True))
