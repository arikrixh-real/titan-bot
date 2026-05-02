def final_signal_score(volume_score, strength_score, compression_score_value):
    score = 0

    # --- POSITIVE SCORING ---

    # Volume
    if volume_score >= 8:
        score += 40
    elif volume_score >= 5:
        score += 35
    elif volume_score >= 3:
        score += 30
    elif volume_score >= 2:
        score += 20
    elif volume_score >= 1.5:
        score += 10

    # Strength
    if strength_score >= 4:
        score += 30
    elif strength_score >= 3:
        score += 25
    elif strength_score >= 2:
        score += 20
    elif strength_score >= 1:
        score += 10

    # Compression
    if compression_score_value >= 9:
        score += 25
    elif compression_score_value >= 8:
        score += 20
    elif compression_score_value >= 6:
        score += 15
    elif compression_score_value >= 4:
        score += 8

    # --- PENALTY LOGIC (KEY UPGRADE) ---

    # Weak volume = bad breakout reliability
    if volume_score < 1.5:
        score -= 20

    # Weak strength = no real trend push
    if strength_score < 1:
        score -= 15

    # No compression = random move
    if compression_score_value < 4:
        score -= 15

    # --- FINAL NORMALIZATION ---
    score = max(0, min(score, 100))
    return score