from consciousness_core.experience_utils import load_json
from consciousness_core.institutional_utils import CORE_DIR, clamp, text_blob
from consciousness_core.state import atomic_write_json, now_ist, stable_hash


OUTPUT_PATH = CORE_DIR / "adaptive_attention.json"


def _item(focus_area, priority, reason, resource_weight, urgency, expected_impact):
    return {
        "focus_id": "focus_" + stable_hash([focus_area, reason])[:12],
        "focus_area": focus_area,
        "priority": priority,
        "reason": reason,
        "resource_weight": round(clamp(resource_weight), 2),
        "urgency": urgency,
        "expected_impact": expected_impact,
        "live_apply_allowed": False,
    }


def run_adaptive_attention_allocator(output_path=OUTPUT_PATH, **_kwargs):
    context = load_json(CORE_DIR / "consciousness_context.json", {})
    manipulation = load_json(CORE_DIR / "manipulation_intelligence.json", {})
    liquidity = load_json(CORE_DIR / "liquidity_intelligence.json", {})
    confidence = load_json(CORE_DIR / "confidence_recalibration.json", {})
    daily = load_json(CORE_DIR / "daily_review.json", {})
    research = load_json(CORE_DIR / "autonomous_research.json", {})
    institutional = load_json(CORE_DIR / "institutional_reasoning_summary.json", {})

    weaknesses = context.get("top_weaknesses", [])
    text = text_blob(weaknesses, daily, institutional)
    focus = []
    if weaknesses:
        focus.append(_item("weakness_research", "HIGH", "active weaknesses remain unresolved", 24, "HIGH", "better proposal quality"))
    if clamp(manipulation.get("suspicion_score")) >= 45 or "trap" in text:
        focus.append(_item("manipulation_caution", "HIGH", "trap or manipulation risk is elevated", 22, "HIGH", "fewer false breakouts"))
    stress = liquidity.get("liquidity_stress", {})
    if str(stress.get("state") or "").upper() in {"MEDIUM", "HIGH", "SEVERE"} or "liquidity" in text:
        focus.append(_item("liquidity_stress_testing", "HIGH", "liquidity stress can invalidate signals", 20, "MEDIUM", "lower slippage and trap exposure"))
    if confidence.get("sample_size_warning") or "confidence" in text:
        focus.append(_item("confidence_failure_analysis", "MEDIUM", "confidence failures need calibration evidence", 16, "MEDIUM", "better confidence sizing"))
    if daily.get("what_failed"):
        focus.append(_item("recurring_loss_patterns", "HIGH", "daily review found repeated failures", 18, "HIGH", "avoid repeated losing contexts"))
    if research.get("ranked_discoveries"):
        focus.append(_item("research_discovery_validation", "MEDIUM", "research produced discoveries needing paper validation", 12, "LOW", "convert discoveries into tests"))
    if not focus:
        focus.append(_item("baseline_recursive_monitoring", "LOW", "no dominant recursive attention demand", 10, "LOW", "maintain awareness"))

    total = sum(item["resource_weight"] for item in focus) or 1.0
    for item in focus:
        item["resource_weight"] = round((item["resource_weight"] / total) * 100, 2)

    primary = sorted(focus, key=lambda item: item["resource_weight"], reverse=True)[0]
    payload = {
        "generated_at": now_ist(),
        "attention_items": sorted(focus, key=lambda item: item["resource_weight"], reverse=True),
        "focus_area": primary.get("focus_area"),
        "priority": primary.get("priority"),
        "reason": primary.get("reason"),
        "resource_weight": primary.get("resource_weight"),
        "urgency": primary.get("urgency"),
        "expected_impact": primary.get("expected_impact"),
        "safety_scope": "read_only_recommendation_only",
    }
    atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    run_adaptive_attention_allocator()
