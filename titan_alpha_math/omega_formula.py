import math

from titan_alpha_math import alpha_config


EPSILON = 1e-9
REQUIRED_ALPHA_INPUTS = {
    "ltp",
    "vwap",
    "atr",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "avg_volume",
    "bid_depth",
    "ask_depth",
    "stock_return",
    "sector_return",
    "index_return",
    "relative_volatility",
    "hold",
    "retest",
    "rejection",
    "similar_wins",
    "similar_losses",
    "spread",
    "timing_freshness",
    "regime_fit",
    "trap_risk",
    "slippage_risk",
    "late_entry_risk",
    "impact_risk",
}


def _num(value):
    try:
        if value is None or value == "":
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _blocked_score(direction, lane_weight, missing_inputs, reason="MISSING_ALPHA_INPUT"):
    return {
        "direction": str(direction).upper(),
        "weight_profile": lane_weight,
        "alpha": None,
        "alpha_edge": None,
        "reliability": None,
        "cost_risk": None,
        "components": {},
        "reliability_components": {},
        "missing_inputs": sorted(set(missing_inputs)),
        "status": "BLOCKED",
        "reject_reason": reason,
        "signal_allowed": False,
    }


def _required_missing(record):
    missing = set(record.get("missing_inputs") or [])
    for field in REQUIRED_ALPHA_INPUTS:
        if _num(record.get(field)) is None:
            missing.add(field)
    return sorted(missing)


def clip(value, low=-1.0, high=1.0):
    number = _num(value)
    if number is None:
        return None
    return max(low, min(high, number))


def _safe_div(numerator, denominator):
    numerator_value = _num(numerator)
    denominator_value = _num(denominator)
    if numerator_value is None or denominator_value is None or abs(denominator_value) <= EPSILON:
        return None
    return numerator_value / denominator_value


def _bounded01(value):
    return clip(value, 0.0, 1.0)


def direction_sign(direction):
    return 1.0 if str(direction).upper() == "LONG" else -1.0


def component_values(record, direction):
    missing = _required_missing(record)
    if missing:
        return {"missing_inputs": missing, "status": "BLOCKED", "reject_reason": "MISSING_ALPHA_INPUT"}

    d = direction_sign(direction)
    ltp = _num(record.get("ltp"))
    vwap = _num(record.get("vwap"))
    atr = _num(record.get("atr"))
    open_ = _num(record.get("open"))
    high = _num(record.get("high"))
    low = _num(record.get("low"))
    close = _num(record.get("close"))
    volume = _num(record.get("volume"))
    avg_volume = _num(record.get("avg_volume"))
    bid = _num(record.get("bid_depth"))
    ask = _num(record.get("ask_depth"))
    stock_return = _num(record.get("stock_return"))
    sector_return = _num(record.get("sector_return"))
    index_return = _num(record.get("index_return"))
    relative_volatility = _num(record.get("relative_volatility"))
    hold = _bounded01(record.get("hold"))
    retest = _bounded01(record.get("retest"))
    rejection = _bounded01(record.get("rejection"))
    wins = _num(record.get("similar_wins"))
    losses = _num(record.get("similar_losses"))

    range_size = high - low
    if range_size <= EPSILON or avg_volume <= EPSILON or relative_volatility <= EPSILON:
        return {
            "missing_inputs": [],
            "status": "BLOCKED",
            "reject_reason": "INVALID_ALPHA_INPUT",
        }

    auction_acceptance = clip(d * _safe_div(ltp - vwap, atr))
    directed_energy = clip(d * ((close - open_) / range_size) * math.log(1 + volume / avg_volume))
    footprint_pressure = clip(d * _safe_div(bid - ask, bid + ask))
    relative_dominance = clip(d * _safe_div((stock_return - sector_return) + 0.5 * (sector_return - index_return), relative_volatility))
    breakout_survival = clip(0.40 * hold + 0.30 * retest + 0.30 * rejection, 0.0, 1.0)
    movement_quality = clip(d * (2 * ((close - low) / range_size) - 1))
    memory_edge = clip(2 * ((wins + 0.5) / (wins + losses + 1)) - 1)
    components = {
        "auction_acceptance": auction_acceptance,
        "directed_energy": directed_energy,
        "footprint_pressure": footprint_pressure,
        "relative_dominance": relative_dominance,
        "breakout_survival": breakout_survival,
        "movement_quality": movement_quality,
        "memory_edge": memory_edge,
        "missing_inputs": [],
    }
    if any(value is None for key, value in components.items() if key != "missing_inputs"):
        return {
            "missing_inputs": [],
            "status": "BLOCKED",
            "reject_reason": "INVALID_ALPHA_INPUT",
        }
    return components


def reliability_components(record, components):
    missing = _required_missing(record)
    if missing:
        return {"missing_inputs": missing, "status": "BLOCKED", "reject_reason": "MISSING_ALPHA_INPUT"}

    liquidity_fit = _bounded01(record.get("liquidity_fit"))
    if liquidity_fit is None:
        volume = _num(record.get("volume"))
        avg_volume = _num(record.get("avg_volume"))
        if volume is None or avg_volume is None or avg_volume <= EPSILON:
            return {"missing_inputs": ["liquidity_fit"], "status": "BLOCKED", "reject_reason": "MISSING_ALPHA_INPUT"}
        liquidity_fit = _bounded01(volume / avg_volume)

    timing = _bounded01(record.get("timing_freshness"))
    trap = _bounded01(record.get("trap_risk"))
    regime = _bounded01(record.get("regime_fit"))
    agreement_override = _bounded01(record.get("component_agreement"))
    if timing is None or trap is None or regime is None:
        return {
            "missing_inputs": ["timing_freshness", "trap_risk", "regime_fit"],
            "status": "BLOCKED",
            "reject_reason": "MISSING_ALPHA_INPUT",
        }
    agreement = agreement_override
    if agreement is None:
        agreement = sum(1 for value in components.values() if isinstance(value, (int, float)) and value > 0) / 7.0
    return {
        "regime_fit": regime,
        "liquidity_fit": liquidity_fit,
        "timing_freshness": timing,
        "component_agreement": _bounded01(agreement),
        "trap_risk": trap,
    }


def cost_risk(record):
    ltp = _num(record.get("ltp"))
    spread = _num(record.get("spread"))
    slippage = _bounded01(record.get("slippage_risk"))
    late = _bounded01(record.get("late_entry_risk"))
    impact = _bounded01(record.get("impact_risk"))
    if ltp is None or abs(ltp) <= EPSILON or spread is None or slippage is None or late is None or impact is None:
        return None
    spread_cost = abs(spread) / abs(ltp)
    return max(0.0, min(1.0, spread_cost + slippage + late + impact))


def calculate_score(record, direction, lane_weight="STRONG"):
    components = component_values(record, direction)
    if components.get("status") == "BLOCKED":
        return _blocked_score(direction, lane_weight, components.get("missing_inputs") or [], components.get("reject_reason") or "MISSING_ALPHA_INPUT")

    weights = alpha_config.LANE_WEIGHTS.get(lane_weight, alpha_config.LANE_WEIGHTS["STRONG"])
    raw = (
        weights["A"] * components["auction_acceptance"]
        + weights["E"] * components["directed_energy"]
        + weights["F"] * components["footprint_pressure"]
        + weights["R"] * components["relative_dominance"]
        + weights["B"] * components["breakout_survival"]
        + weights["Q"] * components["movement_quality"]
        + weights["M"] * components["memory_edge"]
    )
    alpha_edge = math.tanh(raw)
    rel_components = reliability_components(record, {k: v for k, v in components.items() if k != "missing_inputs"})
    if rel_components.get("status") == "BLOCKED":
        return _blocked_score(direction, lane_weight, rel_components.get("missing_inputs") or [], rel_components.get("reject_reason") or "MISSING_ALPHA_INPUT")

    reliability = (
        rel_components["regime_fit"]
        * rel_components["liquidity_fit"]
        * rel_components["timing_freshness"]
        * rel_components["component_agreement"]
        * (1 - rel_components["trap_risk"])
    )
    risk = cost_risk(record)
    if risk is None:
        return _blocked_score(direction, lane_weight, ["cost_risk"], "MISSING_ALPHA_INPUT")

    trade_power = alpha_edge * reliability - risk
    probability = 1 / (1 + math.exp(-5 * trade_power))
    return {
        "direction": str(direction).upper(),
        "weight_profile": lane_weight,
        "alpha": round(max(-1.0, min(1.0, trade_power)), 6),
        "probability": round(_bounded01(probability), 6),
        "trade_power": round(max(-1.0, min(1.0, trade_power)), 6),
        "alpha_edge": round(max(-1.0, min(1.0, alpha_edge)), 6),
        "reliability": round(_bounded01(reliability), 6),
        "cost_risk": round(_bounded01(risk), 6),
        "components": {k: round(v, 6) for k, v in components.items() if k != "missing_inputs"},
        "reliability_components": {k: round(v, 6) for k, v in rel_components.items()},
        "missing_inputs": components["missing_inputs"],
        "status": "OK",
        "reject_reason": None,
        "signal_allowed": True,
    }
