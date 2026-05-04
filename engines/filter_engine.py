import math


def passes_quality_filters(
    setup=None,
    final_score=None,
    volume_score=None,
    strength_score=None,
    compression_score=None
):
    """
    TITAN safety quality filter.

    This filter should NOT block all setups.
    Main selection is handled by:
    - trend
    - momentum
    - structure
    - entry
    - confluence
    - levels
    - RR

    This only blocks invalid/broken values.
    """

    if isinstance(setup, dict):
        final_score = setup.get("score", 0)
        volume_score = setup.get("volume_x", 0)
        strength_score = setup.get("strength", 0)
        compression_score = setup.get("compression", 0)

    final_score = 0 if final_score is None else float(final_score)
    volume_score = 0 if volume_score is None else float(volume_score)
    strength_score = 0 if strength_score is None else float(strength_score)
    compression_score = 0 if compression_score is None else float(compression_score)

    values = [final_score, volume_score, strength_score, compression_score]

    for value in values:
        if math.isnan(value) or math.isinf(value):
            return False

    if final_score < -10:
        return False

    if compression_score < -10:
        return False

    return True