from titan_brain.supabase_client import supabase


DEFAULT_WEIGHTS = {
    "volume_weight": 1.0,
    "strength_weight": 1.0,
    "compression_weight": 1.0,
}


def get_latest_strategy_weights():
    """
    Fetch latest active strategy weights from Supabase.
    If no weights exist yet, return default weights.
    """

    try:
        result = (
            supabase
            .table("strategy_weights")
            .select("*")
            .eq("active", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not result.data:
            return DEFAULT_WEIGHTS

        weights = result.data[0]

        return {
            "volume_weight": weights.get("volume_weight") or 1.0,
            "strength_weight": weights.get("strength_weight") or 1.0,
            "compression_weight": weights.get("compression_weight") or 1.0,
        }

    except Exception as e:
        print(f"[ADAPTIVE SCORE ERROR] Using default weights: {e}")
        return DEFAULT_WEIGHTS


def normalize_weight(weight):
    """
    Keeps adaptive weights safe.
    Prevents extreme learning from breaking TITAN.
    """

    if weight is None:
        return 1.0

    weight = float(weight)

    if weight < 0.5:
        return 0.5

    if weight > 2.0:
        return 2.0

    return weight


def final_signal_score(volume_score, strength_score, compression_score):
    """
    Adaptive final score.
    Uses learned weights if available.
    Falls back to default weights safely.
    """

    weights = get_latest_strategy_weights()

    volume_weight = normalize_weight(weights["volume_weight"])
    strength_weight = normalize_weight(weights["strength_weight"])
    compression_weight = normalize_weight(weights["compression_weight"])

    weighted_score = (
        (volume_score * volume_weight) +
        (strength_score * strength_weight) +
        (compression_score * compression_weight)
    )

    total_weight = volume_weight + strength_weight + compression_weight

    if total_weight == 0:
        return 0

    final_score = weighted_score / total_weight

    return round(final_score, 2)