# TITAN MASTER BRAIN - CONTEXT BUILDER
# STEP 3: Converts raw data into meaning.
# This is where TITAN starts interpreting, not just reading.

def _extract_market_ok(market_data):
    if isinstance(market_data, dict):
        return bool(market_data.get("market_ok", False))
    return False


def _extract_market_reason(market_data):
    if isinstance(market_data, dict):
        return str(market_data.get("reason", "UNKNOWN"))
    return "UNKNOWN"


def build_context(master_input):
    market_packet = master_input.get("market", {})
    setup_packet = master_input.get("setups", {})
    memory_packet = master_input.get("memory", {})

    market_data = market_packet.get("data", {})
    setup_count = setup_packet.get("count", 0)
    memory_analysis = memory_packet.get("analysis", {})

    market_ok = _extract_market_ok(market_data)
    market_reason = _extract_market_reason(market_data)

    context = {
        "market_type": "UNKNOWN",
        "trading_mode": "OBSERVATION",
        "risk_level": "UNKNOWN",
        "setup_environment": "UNKNOWN",
        "learning_environment": "UNKNOWN",
        "context_confidence": "LOW",
        "why": [],
        "recommended_stance": [],
        "next_questions": []
    }

    # Market interpretation
    if market_packet.get("status") != "OK":
        context["market_type"] = "MARKET_DATA_ERROR"
        context["risk_level"] = "HIGH"
        context["trading_mode"] = "DEFENSIVE"
        context["why"].append("Market data connection failed.")
        context["recommended_stance"].append("Do not trust setup quality until market data is restored.")

    elif market_ok:
        context["market_type"] = "MARKET_ALLOWED_LEVEL_1"
        context["risk_level"] = "MEDIUM"
        context["trading_mode"] = "SELECTIVE"
        context["why"].append(f"Market filter allows trading: {market_reason}")
        context["recommended_stance"].append("Trade only high-quality setups with confirmation.")
    else:
        context["market_type"] = "MARKET_NOT_ALLOWED"
        context["risk_level"] = "HIGH"
        context["trading_mode"] = "DEFENSIVE"
        context["why"].append(f"Market filter does not allow trading: {market_reason}")
        context["recommended_stance"].append("Reject weak setups and preserve capital.")

    # Setup interpretation
    if setup_packet.get("status") != "OK":
        context["setup_environment"] = "SETUP_ENGINE_ERROR"
        context["why"].append(f"Setup engine error: {setup_packet.get('error')}")
        context["recommended_stance"].append("Fix setup engine before ranking trades.")
    elif setup_count == 0:
        context["setup_environment"] = "NO_SETUP_PHASE"
        context["why"].append("No setup candidates detected this cycle.")
        context["recommended_stance"].append("Patience is correct. Do not force trades.")
        context["next_questions"].extend([
            "Are filters too strict or is market structure genuinely weak?",
            "Is this no-setup phase caused by low volume, sideways movement, or lack of momentum?",
            "Should I wait for sector confirmation before scanning aggressively?"
        ])
    elif setup_count <= 3:
        context["setup_environment"] = "LOW_SETUP_PHASE"
        context["why"].append(f"Only {setup_count} setup candidate(s) detected.")
        context["recommended_stance"].append("Few setups means be selective and demand strong confluence.")
    elif setup_count <= 15:
        context["setup_environment"] = "NORMAL_SETUP_PHASE"
        context["why"].append(f"{setup_count} setup candidate(s) detected.")
        context["recommended_stance"].append("Rank setups carefully and avoid average-quality trades.")
    else:
        context["setup_environment"] = "MANY_SETUP_PHASE"
        context["why"].append(f"{setup_count} setup candidate(s) detected, which can create noise.")
        context["recommended_stance"].append("Use elite selection. Many setups does not mean many good trades.")

    # Memory interpretation
    bias = memory_analysis.get("bias", "INSUFFICIENT_DATA")
    confirmed = memory_analysis.get("confirmed_outcomes", 0)

    if bias == "INSUFFICIENT_DATA":
        context["learning_environment"] = "LEARNING_NOT_READY"
        context["why"].append(f"Only {confirmed} confirmed outcomes available for learning.")
        context["recommended_stance"].append("Do not change scoring weights from memory yet.")
    elif bias == "FAVORABLE":
        context["learning_environment"] = "RECENT_MEMORY_FAVORABLE"
        context["why"].append("Recent confirmed outcomes are favorable.")
        context["recommended_stance"].append("Allow strong setups, but keep normal confirmation rules.")
    elif bias == "UNFAVORABLE":
        context["learning_environment"] = "RECENT_MEMORY_WEAK"
        context["why"].append("Recent confirmed outcomes are weak.")
        context["recommended_stance"].append("Reduce confidence until setup quality improves.")
    else:
        context["learning_environment"] = "RECENT_MEMORY_NEUTRAL"
        context["why"].append("Recent confirmed outcomes are mixed.")
        context["recommended_stance"].append("Keep confidence neutral.")

    # Overall confidence
    if market_packet.get("status") == "OK" and setup_packet.get("status") == "OK":
        context["context_confidence"] = "MEDIUM"

    if market_ok and setup_count > 0 and confirmed >= 5:
        context["context_confidence"] = "HIGH"

    return context