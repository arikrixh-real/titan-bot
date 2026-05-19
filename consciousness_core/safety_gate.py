IMMUTABLE_CONSTITUTION = (
    "never bypass risk engine",
    "never mutate live trading code directly",
    "never change broker/Telegram behavior",
    "never apply untested strategy changes",
    "require backtest/paper validation",
    "preserve rollback",
    "prefer capital protection over trade frequency",
    "prefer truth over confidence",
)

BLOCKED_TARGETS = ("broker", "telegram", "live_order", "live_execution", "supabase")
UNSAFE_PHRASES = (
    "bypass risk",
    "disable risk",
    "disable no-trade",
    "disable no trade",
    "mutate live",
    "change live",
    "increase risk",
    "broker behavior",
    "telegram behavior",
)
SAFE_TARGETS = {
    "confidence_calibration",
    "setup_engine",
    "no_trade",
    "backtesting",
    "evolution_engine",
    "research_pipeline",
    "runtime_continuous_workers",
    "runtime_registry",
    "consciousness_core",
    "market_regime_update",
    "strategy_memory",
    "auto_repair",
}


def evaluate_proposal(proposal):
    text = " ".join(
        str(proposal.get(key, ""))
        for key in ("title", "reason", "target_engine", "suggested_action", "parameter_hint")
    ).lower()
    target = str(proposal.get("target_engine") or "").lower()
    risk_level = str(proposal.get("risk_level") or "").upper()
    evidence = proposal.get("evidence")
    if any(target_token in text for target_token in BLOCKED_TARGETS):
        return "REJECTED"
    if "risk_engine" in text and "bypass" in text:
        return "REJECTED"
    if any(phrase in text for phrase in UNSAFE_PHRASES):
        return "REJECTED"
    if not proposal.get("requires_backtest"):
        return "REJECTED"
    if risk_level not in {"LOW", "MEDIUM"}:
        return "NEEDS_MORE_EVIDENCE"
    if "live" in text and "paper" not in text and "backtest" not in text:
        return "REJECTED"
    if not evidence:
        return "NEEDS_MORE_EVIDENCE"
    if target not in SAFE_TARGETS and not target.startswith("runtime_"):
        return "NEEDS_MORE_EVIDENCE"
    return "APPROVED_FOR_TEST"
