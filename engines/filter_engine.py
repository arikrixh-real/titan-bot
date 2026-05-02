def passes_quality_filters(setup):
    """
    Final quality filter for trade selection
    """

    if setup["score"] < 60:
        return False

    if setup["rr"] < 1.5:
        return False

    if setup["volume_x"] < 1.8:
        return False

    if setup["compression"] < 7:
        return False

    return True