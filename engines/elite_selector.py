def _safe_float(value, default=0.0):
    try:
        return float(value)
    except:
        return default


def _clamp(value, low, high):
    return max(low, min(high, value))


def calculate_elite_probability_score(setup):
    score = _safe_float(setup.get("score"), 0)
    rr = _safe_float(setup.get("rr"), 0)

    adaptive = _safe_float(setup.get("adaptive_multiplier"), 1)
    pattern = _safe_float(setup.get("pattern_multiplier"), 1)
    confidence = _safe_float(setup.get("pattern_confidence"), 0)
    regime = _safe_float(setup.get("regime_multiplier"), 1)
    phase3_confidence = _safe_float(setup.get("adaptive_confidence_score"), 50)
    cluster_quality = _safe_float(setup.get("cluster_quality_score"), 50)

    rr_component = _clamp(rr, 0, 3) * 8
    confidence_component = confidence * 10
    phase3_component = _clamp((phase3_confidence - 50) / 50, -0.2, 0.2) * 5
    cluster_component = _clamp((cluster_quality - 50) / 50, -0.2, 0.2) * 5

    combined_multiplier = adaptive * pattern * regime
    combined_multiplier = _clamp(combined_multiplier, 0.85, 1.15)

    elite_score = (
        score + rr_component + confidence_component + phase3_component + cluster_component
    ) * combined_multiplier
    return round(_clamp(elite_score, 0, 150), 2)


def apply_elite_selection(setup):
    setup = dict(setup)
    elite_score = calculate_elite_probability_score(setup)

    setup["elite_probability_score"] = elite_score
    setup["rank_score"] = elite_score

    return setup


def rank_elite_setups(setups):
    ranked = [apply_elite_selection(s) for s in setups]

    ranked.sort(
        key=lambda x: _safe_float(x.get("elite_probability_score", 0)),
        reverse=True,
    )

    return ranked
