def build_reason(setup):
    reasons = []

    if setup["volume_x"] >= 3:
        reasons.append("huge volume spike")
    elif setup["volume_x"] >= 1.8:
        reasons.append("strong volume")

    if setup["compression"] >= 8:
        reasons.append("tight compression")

    if setup["score"] >= 80:
        reasons.append("elite score")
    elif setup["score"] >= 60:
        reasons.append("high score")

    reasons.append("trend aligned")
    reasons.append("relative strength confirmed")
    reasons.append("breakout ready")

    return " + ".join(reasons)