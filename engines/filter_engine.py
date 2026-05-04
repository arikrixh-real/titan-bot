def passes_quality_filters(
    setup=None,
    final_score=None,
    volume_score=None,
    strength_score=None,
    compression_score=None
):
    """
    Final quality filter for trade selection.
    Supports both:
    1. setup dict format
    2. keyword argument format used by setup_engine.py
    """

    # -------------------------
    # FORMAT 1: setup dictionary
    # -------------------------
    if isinstance(setup, dict):
        score = setup.get("score", 0)
        rr = setup.get("rr", 2)
        volume = setup.get("volume_x", 0)
        compression = setup.get("compression", 0)

        if score < 55:
            return False

        if rr < 1.5:
            return False

        if volume < 1.3:
            return False

        if compression < 5:
            return False

        return True

    # -------------------------
    # FORMAT 2: setup_engine keyword inputs
    # -------------------------
    final_score = final_score or 0
    volume_score = volume_score or 0
    strength_score = strength_score or 0
    compression_score = compression_score or 0

    if final_score < 55:
        return False

    if volume_score < 20:
        return False

    if strength_score < 20:
        return False

    if compression_score < 20:
        return False

    return True