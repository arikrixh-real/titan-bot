from pathlib import Path

from consciousness_core.experience_utils import load_json
from consciousness_core.institutional_utils import CORE_DIR, clamp, text_blob
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = CORE_DIR / "institutional_infrastructure_awareness.json"


def run_institutional_infrastructure_awareness(output_path=OUTPUT_PATH, **_kwargs):
    data_quality = load_json(CORE_DIR / "data_quality_intelligence.json", {})
    runtime_health = load_json(Path("data") / "runtime" / "titan_runtime_status.json", {})
    worker_health = load_json(Path("data") / "runtime" / "worker_health.json", {})
    liquidity = load_json(CORE_DIR / "liquidity_intelligence.json", {})
    validation = load_json(CORE_DIR / "validation_depth.json", {})
    confidence = load_json(CORE_DIR / "confidence_recalibration.json", {})

    data_score = float(data_quality.get("data_quality_score") or 0)
    validation_score = float(validation.get("validation_depth_score") or 0)
    proxy_seen = "proxy" in text_blob(data_quality, liquidity, runtime_health, worker_health)
    worker_blob = text_blob(worker_health)
    worker_unreliable = any(term in worker_blob for term in ("error", "failed", "stale", "not_implemented"))

    infra_score = round(data_score * 0.35 + validation_score * 0.35 + (0 if proxy_seen else 15) + (0 if worker_unreliable else 15), 2)
    gap_score = clamp(100 - infra_score, 0, 100)
    if infra_score >= 80:
        level = "ADVANCED_ADVISORY"
    elif infra_score >= 55:
        level = "RESEARCH_GRADE_ADVISORY"
    else:
        level = "DEVELOPING_RESEARCH_INFRA"

    missing_capabilities = []
    if proxy_seen:
        missing_capabilities.append("real low-latency liquidity/depth data instead of proxy modes")
    if validation_score < 75:
        missing_capabilities.append("large out-of-sample paper validation with regime segmentation")
    if data_score < 75:
        missing_capabilities.append("complete fresh runtime, OHLC, news, no-trade, and backtesting reports")
    if int(confidence.get("predicted_vs_actual", {}).get("sample_size") or 0) < 50:
        missing_capabilities.append("institutional-scale confidence calibration sample")

    payload = {
        "generated_at": now_ist(),
        "safety_scope": "read_only_recommendation_only",
        "current_infra_level": level,
        "institutional_gap_score": round(gap_score, 2),
        "missing_capabilities": missing_capabilities,
        "highest_impact_infra_upgrades": [
            "replace proxy liquidity and microstructure inputs with live-quality historical depth data",
            "build larger paper-test and out-of-sample validation sets before any promotion review",
            "add freshness monitoring for OHLC, news, no-trade, and runtime reports",
            "segment validation by regime, liquidity, volatility, and news contradiction states",
        ],
        "compute_data_runtime_bottlenecks": {
            "data_quality_score": data_score,
            "validation_depth_score": validation_score,
            "proxy_or_insufficient_data_seen": proxy_seen,
            "worker_reliability_warning": worker_unreliable,
            "runtime_status": runtime_health.get("status"),
        },
        "realism_notes": [
            "This module is advisory and does not change execution, risk, broker, Telegram, Supabase, or master-brain behavior.",
            "Institutional parity requires stronger data lineage, lower latency, larger samples, and independent validation.",
            "Current outputs can guide research priorities but cannot justify live risk override.",
        ],
    }
    atomic_write_json(output_path, payload)
    return payload
