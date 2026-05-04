def passes_quality_filters(
    setup=None,
    final_score=None,
    volume_score=None,
    strength_score=None,
    compression_score=None
):
    """
    TITAN final quality filter with debug reason.
    """

    if isinstance(setup, dict):
        score = setup.get("score", 0)
        rr = setup.get("rr", 2)
        volume = setup.get("volume_x", 0)
        compression = setup.get("compression", 0)

        print(
            f"FINAL FILTER DEBUG | score={score} rr={rr} volume={volume} compression={compression}"
        )

        if score < 50:
            print("FINAL FILTER BLOCKED: SCORE_LOW")
            return False

        if rr < 1.5:
            print("FINAL FILTER BLOCKED: RR_LOW")
            return False

        if volume < 1.2:
            print("FINAL FILTER BLOCKED: VOLUME_LOW")
            return False

        if compression < 4:
            print("FINAL FILTER BLOCKED: COMPRESSION_LOW")
            return False

        print("FINAL FILTER PASSED")
        return True

    final_score = final_score or 0
    volume_score = volume_score or 0
    strength_score = strength_score or 0
    compression_score = compression_score or 0

    print(
        f"FINAL FILTER DEBUG | final={final_score} volume={volume_score} strength={strength_score} compression={compression_score}"
    )

    if final_score < 50:
        print("FINAL FILTER BLOCKED: FINAL_SCORE_LOW")
        return False

    if volume_score < 15:
        print("FINAL FILTER BLOCKED: VOLUME_SCORE_LOW")
        return False

    if strength_score < 15:
        print("FINAL FILTER BLOCKED: STRENGTH_SCORE_LOW")
        return False

    if compression_score < 15:
        print("FINAL FILTER BLOCKED: COMPRESSION_SCORE_LOW")
        return False

    print("FINAL FILTER PASSED")
    return True