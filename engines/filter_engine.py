def passes_quality_filters(setup):
    """
    Balanced final quality filter
    """

    score = setup.get("score", 0)
    rr = setup.get("rr", 0)
    volume_x = setup.get("volume_x", 0)
    compression = setup.get("compression", 0)

    # 🎯 RELAXED + REALISTIC CONDITIONS

    if score < 45:
        return False

    if rr < 1.5:
        return False

    if volume_x < 1.2:
        return False

    if compression < 4:
        return False

    return True