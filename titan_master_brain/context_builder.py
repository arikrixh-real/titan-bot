# TITAN MASTER BRAIN - CONTEXT BUILDER
# STEP 3: Converts raw data into meaning.
# This is where TITAN starts interpreting, not just reading.
from pathlib import Path


SELF_IMPROVEMENT_STATUS_PATH = Path("data") / "runtime" / "self_improvement_status.json"

def _extract_market_ok(market_data):
    if isinstance(market_data, dict):
        return bool(market_data.get("market_ok", False))
    return False


def _extract_market_reason(market_data):
    if isinstance(market_data, dict):
        return str(market_data.get("reason", "UNKNOWN"))
    return "UNKNOWN"


def _source_summary(advisory, name):
    if not isinstance(advisory, dict):
        return {}
    sources = advisory.get("sources")
    if not isinstance(sources, dict):
        return {}
    source = sources.get(name)
    return source if isinstance(source, dict) else {}


def _summary_payload(source):
    payload = source.get("summary") if isinstance(source, dict) else {}
    return payload if isinstance(payload, dict) else {}


def _safe_self_improvement_summary(self_improvement):
    safe_default = {
        "mode": "SHADOW_ONLY_CONTROLLED_SELF_IMPROVEMENT",
        "status": "SHADOW_INACTIVE",
        "proposal_count": 0,
        "paper_test_count": 0,
        "blocked_count": 0,
        "promoted_count": 0,
        "top_safe_improvement_ideas": [],
        "proposals_path": None,
        "runtime_status_path": str(SELF_IMPROVEMENT_STATUS_PATH).replace("\\", "/"),
        "live_apply_allowed": False,
        "direct_scoring_change": False,
        "strategy_weight_mutation": False,
        "broker_orders": False,
        "telegram_changes": False,
    }
    if not isinstance(self_improvement, dict) or not self_improvement:
        if SELF_IMPROVEMENT_STATUS_PATH.exists():
            return safe_default
        unavailable = dict(safe_default)
        unavailable["status"] = "UNAVAILABLE"
        return unavailable

    summary = dict(safe_default)
    summary.update(
        {
            "status": self_improvement.get("status") or safe_default["status"],
            "proposal_count": int(self_improvement.get("proposal_count") or 0),
            "paper_test_count": int(self_improvement.get("paper_test_count") or 0),
            "blocked_count": int(self_improvement.get("blocked_count") or 0),
            "promoted_count": int(self_improvement.get("promoted_count") or 0),
            "top_safe_improvement_ideas": (self_improvement.get("top_safe_improvement_ideas") or [])[:5],
            "proposals_path": self_improvement.get("proposals_path"),
            "runtime_status_path": self_improvement.get("runtime_status_path") or safe_default["runtime_status_path"],
            "live_apply_allowed": False,
        }
    )
    return summary


def _append_advisory_context(context, advisory):
    sources = advisory.get("sources") if isinstance(advisory, dict) else {}
    sources = sources if isinstance(sources, dict) else {}

    consciousness = _summary_payload(_source_summary(advisory, "consciousness"))
    report_vault = _summary_payload(_source_summary(advisory, "report_vault"))
    experience_vault = _summary_payload(_source_summary(advisory, "experience_vault"))
    knowledge_vault = _summary_payload(_source_summary(advisory, "knowledge_vault"))
    safety_council = advisory.get("safety_council") if isinstance(advisory, dict) else {}
    safety_council = safety_council if isinstance(safety_council, dict) else {}
    pyramid_governance = advisory.get("pyramid_governance") if isinstance(advisory, dict) else {}
    pyramid_governance = pyramid_governance if isinstance(pyramid_governance, dict) else {}
    governance = pyramid_governance.get("governance") if isinstance(pyramid_governance.get("governance"), dict) else {}
    strategy_workflow = advisory.get("strategy_improvement_workflow") if isinstance(advisory, dict) else {}
    strategy_workflow = strategy_workflow if isinstance(strategy_workflow, dict) else {}
    self_improvement = advisory.get("controlled_self_improvement") if isinstance(advisory, dict) else {}
    self_improvement = self_improvement if isinstance(self_improvement, dict) else {}
    self_improvement_summary = _safe_self_improvement_summary(self_improvement)
    contradiction_summaries = report_vault.get("contradiction_resolution_summaries") or []
    experience_reliability = experience_vault.get("experience_intelligence_summary") or {}

    stale_or_missing = []
    neural_schema = {}
    for name, source in sources.items():
        status = str(source.get("status") or "UNKNOWN").upper() if isinstance(source, dict) else "UNKNOWN"
        warning = source.get("warning") if isinstance(source, dict) else None
        neural = source.get("neural_schema") if isinstance(source, dict) else None
        if isinstance(neural, dict):
            neural_schema[name] = {
                "source": neural.get("source"),
                "freshness": neural.get("freshness"),
                "confidence": neural.get("confidence"),
                "risk": neural.get("risk"),
                "warnings": neural.get("warnings") or [],
                "memory_type": neural.get("memory_type"),
                "trust_level": neural.get("trust_level"),
                "validation_status": neural.get("validation_status"),
                "action_permission": neural.get("action_permission"),
                "live_apply_allowed": bool(neural.get("live_apply_allowed", False)),
            }
        if status in {"STALE", "MISSING", "CORRUPT"}:
            stale_or_missing.append(
                {
                    "source": name,
                    "status": status,
                    "path": source.get("path") if isinstance(source, dict) else None,
                    "warning": warning,
                }
            )

    no_trade_warnings = consciousness.get("no_trade_warnings") or []
    safety_warnings = []
    if report_vault.get("conflicts"):
        safety_warnings.append("Report vault conflicts are present.")
    if stale_or_missing:
        safety_warnings.append("One or more advisory intelligence packets are stale, missing, or corrupt.")
    if no_trade_warnings:
        safety_warnings.append("Consciousness no-trade warnings are present.")
    if safety_council.get("stale_data", {}).get("scanner_stale_data_warning"):
        safety_warnings.append("Scanner reports stale data.")
    if safety_council.get("broker_safety", {}).get("execution_allowed") is True:
        safety_warnings.append("Broker safety unexpectedly reports execution allowed; keep advisory context read-only.")

    context["advisory_intelligence"] = {
        "mode": "READ_ONLY_ADVISORY",
        "status": advisory.get("status") if isinstance(advisory, dict) else "UNAVAILABLE",
        "status_path": "data/runtime/advisory_intelligence_status.json",
        "direct_score_changes": False,
        "alert_changes": False,
        "execution_changes": False,
        "journal_writes": False,
        "strategy_weight_mutation": False,
        "strategy_replacement": False,
        "live_apply_allowed": False,
        "neural_schema_v1": neural_schema,
        "consciousness_warnings": {
            "top_weaknesses": consciousness.get("top_weaknesses") or [],
            "active_regime_warnings": consciousness.get("active_regime_warnings") or [],
            "no_trade_warnings": no_trade_warnings,
            "confidence_warnings": consciousness.get("confidence_warnings") or [],
            "current_focus": consciousness.get("current_focus"),
        },
        "report_vault_conflicts": report_vault.get("conflicts") or [],
        "report_vault_missing_data": report_vault.get("missing_data") or [],
        "experience_vault_lesson_count": experience_vault.get("lesson_count", 0),
        "experience_vault_lessons": experience_vault.get("sample_lessons") or [],
        "experience_vault_trust_level": experience_vault.get("trust_level"),
        "experience_reliability_summaries": experience_reliability,
        "knowledge_vault_observation_count": knowledge_vault.get("observation_count", 0),
        "knowledge_vault_observations": knowledge_vault.get("sample_observations") or [],
        "knowledge_vault_belief_count": knowledge_vault.get("belief_count", 0),
        "stale_or_missing_packet_warnings": stale_or_missing,
        "strategy_improvement_workflow": {
            "mode": strategy_workflow.get("mode", "SHADOW_PROPOSAL_ONLY"),
            "shadow_recommendation_path": strategy_workflow.get("shadow_recommendation_path"),
            "proposal_queue_path": strategy_workflow.get("proposal_queue_path"),
            "direct_live_mutation": False,
            "direct_scoring_change": False,
            "direct_strategy_replacement": False,
            "recommendations": (strategy_workflow.get("recommendations") or [])[:10],
        },
        "controlled_self_improvement": self_improvement_summary,
        "safety_council": {
            "broker_safety": safety_council.get("broker_safety") or {},
            "promotion_gate": safety_council.get("promotion_gate") or {},
            "stale_data": safety_council.get("stale_data") or {},
            "no_trade_risk": safety_council.get("no_trade_risk") or {},
            "market_hour_status": safety_council.get("market_hour_status") or {},
            "duplicate_risk": safety_council.get("duplicate_risk") or {},
            "warnings": safety_council.get("warnings") or [],
            "live_apply_allowed": False,
        },
        "governance_decision": governance.get("decision") or advisory.get("governance_decision"),
        "governance_warnings": governance.get("warnings") or advisory.get("governance_warnings") or [],
        "stale_intelligence_warnings": governance.get("stale_intelligence_warnings") or stale_or_missing,
        "degraded_intelligence_warnings": governance.get("degraded_intelligence_warnings") or [],
        "contradiction_risk_summaries": contradiction_summaries,
        "pyramid_governance_status_path": "data/runtime/pyramid_governance_status.json",
        "pyramid_governance_status": pyramid_governance.get("status"),
        "safety_warnings": safety_warnings,
    }
    context["self_improvement"] = self_improvement_summary

    if governance.get("decision"):
        context["governance_decision"] = governance.get("decision")
        context["governance_warnings"] = governance.get("warnings") or []
        context["stale_intelligence_warnings"] = governance.get("stale_intelligence_warnings") or []
        context["degraded_intelligence_warnings"] = governance.get("degraded_intelligence_warnings") or []
        context["contradiction_risk_summaries"] = contradiction_summaries
        context["experience_reliability_summaries"] = experience_reliability
        context["why"].append(
            f"Safety Council governance decision: {governance.get('decision')}."
        )
    if stale_or_missing:
        context["why"].append(
            f"Advisory intelligence has {len(stale_or_missing)} stale/missing/corrupt packet warning(s)."
        )
    if report_vault.get("conflicts"):
        context["why"].append(
            f"Report vault advisory detected {len(report_vault.get('conflicts') or [])} conflict(s)."
        )
    if no_trade_warnings:
        context["recommended_stance"].append(
            "Advisory no-trade warnings are present; keep them advisory until hard gates consume them."
        )
    if self_improvement:
        context["why"].append(
            "Controlled self-improvement visible: "
            f"proposals={self_improvement.get('proposal_count', 0)} "
            f"paper_tests={self_improvement.get('paper_test_count', 0)} "
            f"blocked={self_improvement.get('blocked_count', 0)} "
            f"promoted={self_improvement.get('promoted_count', 0)}."
        )
        context["recommended_stance"].append(
            "Self-improvement proposals remain shadow-only; do not mutate scoring or strategy weights."
        )
    promotion = safety_council.get("promotion_gate") if isinstance(safety_council, dict) else {}
    if isinstance(promotion, dict):
        context["why"].append(
            "Promotion gate visible: "
            f"status={promotion.get('status')} "
            f"live_influence={promotion.get('any_live_influence')} "
            f"live_weight={promotion.get('recommended_live_weight')}."
        )
    broker = safety_council.get("broker_safety") if isinstance(safety_council, dict) else {}
    if isinstance(broker, dict):
        context["why"].append(
            "Broker safety visible: "
            f"mode={broker.get('broker_execution_mode')} "
            f"execution_allowed={broker.get('execution_allowed')}."
        )


def build_context(master_input):
    market_packet = master_input.get("market", {})
    setup_packet = master_input.get("setups", {})
    memory_packet = master_input.get("memory", {})
    advisory_packet = master_input.get("advisory_intelligence", {})

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
        "advisory_intelligence": {
            "mode": "READ_ONLY_ADVISORY",
            "status": "UNAVAILABLE",
            "direct_score_changes": False,
            "alert_changes": False,
            "execution_changes": False,
            "journal_writes": False,
        },
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

    _append_advisory_context(context, advisory_packet)

    return context
