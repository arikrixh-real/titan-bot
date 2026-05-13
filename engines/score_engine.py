from titan_brain.supabase_client import supabase


DEFAULT_WEIGHTS = {
    "volume_weight": 1.0,
    "strength_weight": 1.0,
    "compression_weight": 1.0,
}

_WARNED_WEIGHT_ERRORS = set()


def get_latest_strategy_weights():
    """
    Fetch latest active strategy weights from Supabase.
    If Supabase fails or no weights exist, TITAN safely uses default weights.
    """
    if supabase is None:
        return DEFAULT_WEIGHTS

    try:
        result = (
            supabase
            .table("strategy_weights")
            .select("*")
            .eq("active", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not result.data:
            return DEFAULT_WEIGHTS

        weights = result.data[0]

        return {
            "volume_weight": weights.get("volume_weight") or 1.0,
            "strength_weight": weights.get("strength_weight") or 1.0,
            "compression_weight": weights.get("compression_weight") or 1.0,
        }

    except Exception as e:
        text = str(e)
        if "WinError 10013" in text:
            if "socket" not in _WARNED_WEIGHT_ERRORS:
                _WARNED_WEIGHT_ERRORS.add("socket")
                print("[ADAPTIVE SCORE WARN] Supabase socket unavailable; using default weights.")
        else:
            print(f"[ADAPTIVE SCORE ERROR] Using default weights: {e}")
        return DEFAULT_WEIGHTS


def normalize_weight(weight):
    """
    Keeps adaptive weights safe.
    Prevents extreme learning values from breaking TITAN.
    """
    try:
        if weight is None:
            return 1.0

        weight = float(weight)

        if weight < 0.5:
            return 0.5

        if weight > 2.0:
            return 2.0

        return weight

    except Exception:
        return 1.0


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def final_signal_score(
    volume_score=0,
    strength_score=0,
    compression_score=0,
    momentum_ok=None,
    trap_ok=None,
    relative_strength_ok=None,
    entry_ok=None,
    structure_ok=None,
    **kwargs
):
    """
    TITAN adaptive final score.

    IMPORTANT:
    This function is now backward-compatible with your setup_engine.py.

    It accepts:
    - volume_score
    - strength_score
    - compression_score

    It also safely accepts extra old arguments:
    - momentum_ok
    - trap_ok
    - relative_strength_ok
    - entry_ok
    - structure_ok

    Extra arguments will NOT crash TITAN.
    """

    try:
        volume_score = safe_float(volume_score)
        strength_score = safe_float(strength_score)
        compression_score = safe_float(compression_score)

        weights = get_latest_strategy_weights()

        volume_weight = normalize_weight(weights.get("volume_weight", 1.0))
        strength_weight = normalize_weight(weights.get("strength_weight", 1.0))
        compression_weight = normalize_weight(weights.get("compression_weight", 1.0))

        weighted_score = (
            (volume_score * volume_weight) +
            (strength_score * strength_weight) +
            (compression_score * compression_weight)
        )

        total_weight = volume_weight + strength_weight + compression_weight

        if total_weight == 0:
            base_score = 0
        else:
            base_score = weighted_score / total_weight

        bonus = 0

        if momentum_ok is True:
            bonus += 0.5

        if trap_ok is True:
            bonus += 0.5

        if relative_strength_ok is True:
            bonus += 0.5

        if entry_ok is True:
            bonus += 0.5

        if structure_ok is True:
            bonus += 0.5

        final_score = base_score + bonus

        return round(final_score, 2)

    except Exception as e:
        print(f"[FINAL SCORE ERROR] {e}")
        return 0
