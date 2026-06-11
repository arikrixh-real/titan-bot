from titan_alpha_math import alpha_config
from titan_alpha_math.omega_formula import calculate_score


def classify_lane(score):
    rc = score.get("reliability_components", {})

    def passes(lane):
        thresholds = alpha_config.LANE_THRESHOLDS[lane]
        checks = [
            score.get("probability", 0) >= thresholds["probability"],
            score.get("trade_power", 0) >= thresholds["trade_power"],
            rc.get("component_agreement", 0) >= thresholds["agreement"],
            rc.get("trap_risk", 1) <= thresholds["trap_risk_max"],
            rc.get("liquidity_fit", 0) >= thresholds["liquidity"],
        ]
        if "regime" in thresholds:
            checks.append(rc.get("regime_fit", 0) >= thresholds["regime"])
        return all(checks)

    for lane in ("ELITE", "STRONG", "MICRO"):
        if passes(lane):
            return lane
    return "NO_TRADE"


def classify_input(record, direction):
    checked = []
    for lane in ("ELITE", "STRONG", "MICRO"):
        score = calculate_score(record, direction, lane_weight=lane)
        checked.append(score)
        if classify_lane(score) == lane:
            return lane, score
    fallback = max(checked, key=lambda item: item.get("trade_power", -1.0)) if checked else calculate_score(record, direction)
    return "NO_TRADE", fallback
