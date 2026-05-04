def passes_quality_filters(
    setup=None,
    final_score=None,
    volume_score=None,
    strength_score=None,
    compression_score=None
):
    """
    TITAN balanced quality filter.
    Supports both:
    1. setup dictionary
    2. keyword arguments from setup_engine.py
    """

    # -------------------------
    # MODE 1: setup dictionary
    # -------------------------
    if isinstance(setup, dict):
        score = setup.get("score", 0)
        rr = setup.get("rr", 2)
        volume_x = setup.get("volume_x", 1.5)
        compression = setup.get("compression", 5)

        if score < 45:
            return False

        if rr < 1.5:
            return False

        if volume_x < 1.2:
            return False

        if compression < 4:
            return False

        return True

    # -------------------------
    # MODE 2: setup_engine inputs
    # -------------------------
    final_score = final_score or 0
    volume_score = volume_score or 0
    strength_score = strength_score or 0
    compression_score = compression_score or 0

    if final_score < 35:
        return False

    if volume_score < 5:
        return False

    if strength_score < 5:
        return False

    if compression_score < 5:
        return False

    return True