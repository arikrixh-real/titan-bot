def to_float(value):
    try:
        if hasattr(value, "iloc"):
            return float(value.iloc[0])
        return float(value)
    except Exception:
        return 0.0


def volume_anomaly_score(df, lookback=20):
    if len(df) < lookback + 1:
        return 0

    latest_volume = to_float(df["Volume"].iloc[-1])
    avg_volume = to_float(df["Volume"].iloc[-lookback - 1:-1].mean())

    if avg_volume == 0:
        return 0

    ratio = latest_volume / avg_volume
    return round(float(ratio), 2)