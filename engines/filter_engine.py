def passes_quality_filters(
    setup=None,
    final_score=None,
    volume_score=None,
    strength_score=None,
    compression_score=None
):
    """
    Balanced final filter (not too strict, not loose)
    """

    final_score = final_score or 0
    volume_score = volume_score or 0
    strength_score = strength_score or 0
    compression_score = compression_score or 0

    # 🔥 MAIN CHANGE: relaxed thresholds
    if final_score < 45:
        return False

    if volume_score < 10:
        return False

    if strength_score < 10:
        return False

    if compression_score < 10:
        return False

    return True