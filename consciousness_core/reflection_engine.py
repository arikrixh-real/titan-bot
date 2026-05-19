def reflect(observation_packet, previous_state=None, beliefs=None):
    observations = observation_packet.get("observations", [])
    previous_hash = (previous_state or {}).get("last_observation_hash")
    current_hash = observation_packet.get("observation_hash")
    missing = observation_packet.get("missing_patterns", [])
    lessons = []
    mistakes = []
    confirmations = []
    contradictions = []
    confidence_warnings = []
    regime_warnings = []

    if observation_packet.get("observation_count", 0) == 0:
        lessons.append("No new changed observations were processed this cycle; retain prior conclusions without adding evidence weight.")
    elif current_hash == previous_hash:
        lessons.append("Recent observations are unchanged; avoid over-learning from duplicate data.")
    else:
        lessons.append("New runtime evidence is available and should be reconciled with prior memory.")

    if missing:
        mistakes.append(f"{len(missing)} expected data source patterns are missing.")

    error_sources = [
        observation["source"]
        for observation in observations
        if observation.get("status") != "ok" or observation.get("error")
    ]
    if error_sources:
        mistakes.append(f"{len(error_sources)} observation sources could not be read cleanly.")

    if observations:
        confirmations.append(f"{len(observations)} TITAN data sources were processed without direct mutation.")

    disputed = [
        belief.get("statement")
        for belief in (beliefs or {}).values()
        if belief.get("status") == "DISPUTED"
    ]
    if disputed:
        contradictions.extend(disputed[:5])
        confidence_warnings.append("Some beliefs have more contradictions than evidence.")

    for observation in observations:
        source = observation.get("source", "")
        if "confidence_calibration" in source:
            confidence_warnings.append("Confidence calibration data should be checked before increasing trade trust.")
        if "no_trade" in source or "market_regime" in source:
            regime_warnings.append("No-trade and regime evidence should constrain strategy aggressiveness.")

    return {
        "lessons": lessons,
        "mistakes": mistakes,
        "confirmations": confirmations,
        "contradictions": contradictions,
        "confidence_warnings": list(dict.fromkeys(confidence_warnings)),
        "regime_warnings": list(dict.fromkeys(regime_warnings)),
    }
