def volume_anomaly_score(df, lookback=20):
    if len(df) < lookback + 1:
        return 0

    latest_volume = df["Volume"].iloc[-1]
    avg_volume = df["Volume"].iloc[-lookback - 1:-1].mean()

    if avg_volume == 0:
        return 0

    ratio = latest_volume / avg_volume
    return round(float(ratio), 2)