def passes_quality_filters(
    setup=None,
    final_score=None,
    volume_score=None,
    strength_score=None,
    compression_score=None
):

    final_score = final_score or 0
    volume_score = volume_score or 0
    strength_score = strength_score or 0
    compression_score = compression_score or 0

    if final_score < 2:
        return False

    if volume_score < 0:
        return False

    if strength_score < -2:
        return False

    if compression_score < 3:
        return False

    return True