from pathlib import Path

from consciousness_core.institutional_utils import (
    clamp,
    evidence_item,
    load_institutional_inputs,
    mode_is_weak,
    recommendation,
)
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = Path("data") / "consciousness_core" / "liquidity_intelligence.json"


def run_liquidity_intelligence(output_path=OUTPUT_PATH, **_kwargs):
    inputs = load_institutional_inputs()
    liquidity = inputs["liquidity_map"]
    micro = inputs["microstructure"]
    no_trade = inputs["no_trade"]

    liquidity_score = clamp(liquidity.get("liquidity_map_score") or 50.0)
    micro_score = clamp(micro.get("microstructure_score") or 50.0)
    danger = clamp(no_trade.get("liquidity_danger", {}).get("danger_score") or 0.0)
    spread_risk = clamp(micro.get("spread_widening", {}).get("risk_score") or 0.0)
    sweep_risk = clamp(micro.get("liquidity_sweeps", {}).get("risk_score") or 0.0)
    absorption = micro.get("absorption_detection", {})

    weak_mode = mode_is_weak(liquidity, ("liquidity_data_mode",)) or mode_is_weak(micro, ("data_mode",))
    participation_score = round((liquidity_score + micro_score) / 2, 2)
    stress_score = clamp((100.0 - participation_score) * 0.45 + danger * 0.35 + spread_risk * 0.2 + (15 if weak_mode else 0))
    imbalance_score = clamp(abs(micro.get("order_book_imbalance", {}).get("imbalance_score") or 0.0))

    regime = "THIN_OR_UNCERTAIN"
    if stress_score >= 65 or weak_mode:
        regime = "STRESSED_THIN_LIQUIDITY"
    elif participation_score >= 65 and stress_score < 35:
        regime = "STRONG_PARTICIPATION"
    elif imbalance_score >= 60:
        regime = "IMBALANCED_LIQUIDITY"

    payload = {
        "generated_at": now_ist(),
        "liquidity_stress": {
            "score": round(stress_score, 2),
            "state": "HIGH" if stress_score >= 65 else "MODERATE" if stress_score >= 35 else "LOW",
            "evidence": [
                evidence_item("liquidity_map", "liquidity_map_score", liquidity_score),
                evidence_item("microstructure", "microstructure_score", micro_score),
                evidence_item("no_trade", "liquidity_danger", danger),
                evidence_item("microstructure", "spread_widening_risk", spread_risk),
            ],
        },
        "participation_weakness": weak_mode or participation_score < 45,
        "thin_liquidity": weak_mode or stress_score >= 60,
        "strong_participation": participation_score >= 65 and not weak_mode,
        "liquidity_imbalance": {
            "score": round(imbalance_score, 2),
            "direction": micro.get("order_book_imbalance", {}).get("direction") or "NEUTRAL",
            "queue_direction": micro.get("queue_imbalance", {}).get("direction") or "NEUTRAL",
        },
        "absorption_zones": {
            "active": bool(absorption.get("active")),
            "score": clamp(absorption.get("score") or 0.0),
            "side": absorption.get("side") or "NEUTRAL",
            "source": "microstructure_absorption_detection",
        },
        "liquidity_regime": regime,
        "read_only_recommendations": [
            recommendation("reduce_aggression_bias", "liquidity evidence is proxy/insufficient or stress is elevated")
            if regime in {"STRESSED_THIN_LIQUIDITY", "THIN_OR_UNCERTAIN"}
            else recommendation("allow_normal_review_bias", "liquidity participation is not showing high stress"),
        ],
        "source_modes": {
            "liquidity_data_mode": liquidity.get("liquidity_data_mode"),
            "microstructure_data_mode": micro.get("data_mode"),
        },
    }
    atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    run_liquidity_intelligence()
