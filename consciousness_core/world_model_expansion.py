from pathlib import Path

from consciousness_core.institutional_utils import evidence_item, load_institutional_inputs
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = Path("data") / "consciousness_core" / "world_model_expansion.json"


def run_world_model_expansion(output_path=OUTPUT_PATH, **_kwargs):
    inputs = load_institutional_inputs()
    world = inputs["world_model_memory"]
    no_trade = inputs["no_trade"]
    news = inputs["news"]
    confidence = inputs["confidence"]
    liquidity = inputs["liquidity_map"]
    micro = inputs["microstructure"]
    real_memory = inputs["real_experience_memory"]

    expansion = {
        "generated_at": now_ist(),
        "macro_memory": {
            "prior": world.get("macro_memory", {}),
            "current_evidence": [evidence_item("economic_calendar", "available", bool(inputs["economic_calendar"])), evidence_item("news", "event_classification", news.get("event_classification"))],
            "long_horizon_lesson": "macro remains contextual and cannot authorize live action from this module",
        },
        "sector_rotation_memory": {
            "status": "LIMITED_EVIDENCE",
            "current_sector_report": inputs["sector_strength"],
            "long_horizon_lesson": "sector rotation needs direct breadth and sector outcome evidence before it can raise conviction",
        },
        "volatility_cycle_memory": {
            "prior": world.get("volatility_memory", []),
            "current_choppy_market": no_trade.get("choppy_market", {}),
            "long_horizon_lesson": "rising volatility should be interpreted with liquidity and breadth, not in isolation",
        },
        "liquidity_cycle_memory": {
            "prior": world.get("liquidity_memory", []),
            "current_liquidity_warning": liquidity.get("liquidity_warning"),
            "current_microstructure_warning": micro.get("execution_warning"),
            "long_horizon_lesson": "proxy or insufficient liquidity evidence should cap aggression recommendations",
        },
        "institutional_behavior_memory": {
            "smart_money_footprints": liquidity.get("smart_money_footprints", {}),
            "smart_money_pressure": micro.get("smart_money_pressure", {}),
            "long_horizon_lesson": "institutional participation requires confirmation from both volume zones and microstructure pressure",
        },
        "manipulation_memory": {
            "stop_loss_clusters": liquidity.get("stop_loss_clusters", {}),
            "breakout_trap_zones": liquidity.get("breakout_trap_zones", {}),
            "spoof_like_detection": micro.get("spoof_like_detection", {}),
            "long_horizon_lesson": "trap evidence should create caution bias, never direct execution control",
        },
        "confidence_reliability_memory": {
            "current_calibration": {
                "score": confidence.get("calibrated_confidence_score"),
                "warning": confidence.get("calibration_warning"),
                "sample_size": confidence.get("predicted_vs_actual", {}).get("sample_size"),
            },
            "historical_patterns": real_memory.get("confidence_failure_patterns", []),
            "long_horizon_lesson": "confidence reliability is conditional on realized sample size and regime-specific evidence",
        },
        "safety_scope": "read_only_recommendation_only",
    }
    atomic_write_json(output_path, expansion)
    return expansion


if __name__ == "__main__":
    run_world_model_expansion()
