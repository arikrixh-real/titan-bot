from pathlib import Path

from consciousness_core.state import atomic_write_json, now_ist


REPORT_JSON_PATH = Path("data") / "consciousness_core" / "latest_consciousness_report.json"
REPORT_TXT_PATH = Path("data") / "consciousness_core" / "latest_consciousness_report.txt"


def write_report(
    state,
    reflection,
    weaknesses,
    goals,
    beliefs,
    missions,
    proposals,
    safety_decisions,
    observation_packet=None,
    approved_queue=None,
    consolidation_stats=None,
    phase2=None,
    phase3=None,
    phase_a=None,
    phase_b=None,
    path_json=REPORT_JSON_PATH,
    path_txt=REPORT_TXT_PATH,
):
    observation_packet = observation_packet or {}
    approved_queue = approved_queue or []
    consolidation_stats = consolidation_stats or {}
    phase2 = phase2 or {}
    phase3 = phase3 or {}
    phase_a = phase_a or {}
    phase_b = phase_b or {}
    top_beliefs = sorted(
        beliefs.values(),
        key=lambda belief: float(belief.get("confidence") or 0),
        reverse=True,
    )[:10]
    report = {
        "generated_at": now_ist(),
        "current_understanding": state.get("latest_summary", ""),
        "real_evidence_found": observation_packet.get("observation_count", 0),
        "unchanged_observations_skipped": observation_packet.get("unchanged_observation_count", 0),
        "missing_data": observation_packet.get("missing_patterns", []),
        "weaknesses_detected": len(weaknesses),
        "duplicates_merged": int(consolidation_stats.get("duplicates_merged") or 0),
        "consolidated_missions": int(consolidation_stats.get("consolidated_missions") or 0),
        "consolidated_proposals": int(consolidation_stats.get("consolidated_proposals") or 0),
        "beliefs_changed": len(top_beliefs),
        "proposals_approved_for_testing": approved_queue,
        "proposals_rejected": [
            proposal_id for proposal_id, decision in safety_decisions.items() if decision == "REJECTED"
        ],
        "insufficient_evidence_areas": [
            proposal_id for proposal_id, decision in safety_decisions.items() if decision == "NEEDS_MORE_EVIDENCE"
        ],
        "active_weaknesses": weaknesses[:20],
        "active_goals": goals[:20],
        "top_beliefs": top_beliefs,
        "research_missions": missions[:20],
        "improvement_proposals": proposals[:20],
        "safety_decisions": safety_decisions,
        "sandbox_results": phase2.get("sandbox_results", {}).get("results", [])[:20],
        "promotion_recommendations": phase2.get("promotion_recommendations", {}).get("recommendations", [])[:20],
        "causal_lessons": phase2.get("causal_reasoning", {}).get("causal_lessons", [])[:20],
        "experience_memory_highlights": {
            "repeated_failure_patterns": phase2.get("experience_memory", {}).get("repeated_failure_patterns", [])[:10],
            "repeated_success_patterns": phase2.get("experience_memory", {}).get("repeated_success_patterns", [])[:10],
            "weak_engines": phase2.get("experience_memory", {}).get("weak_engines", [])[:10],
            "strong_engines": phase2.get("experience_memory", {}).get("strong_engines", [])[:10],
            "regime_lessons": phase2.get("experience_memory", {}).get("regime_lessons", [])[:10],
        },
        "strategy_mutations": phase2.get("strategy_mutations", {}).get("mutations", [])[:20],
        "research_experiments": phase2.get("research_experiments", {}).get("experiments", [])[:20],
        "meta_learning": phase2.get("meta_learning", {}),
        "phase3_real_experience_memory": {
            "repeated_failure_patterns": phase3.get("real_experience_memory", {}).get("repeated_failure_patterns", [])[:10],
            "repeated_success_patterns": phase3.get("real_experience_memory", {}).get("repeated_success_patterns", [])[:10],
            "engine_reliability_memory": phase3.get("real_experience_memory", {}).get("engine_reliability_memory", [])[:10],
        },
        "phase3_daily_review": {
            "what_worked": phase3.get("daily_review", {}).get("what_worked", [])[:10],
            "what_failed": phase3.get("daily_review", {}).get("what_failed", [])[:10],
            "what_was_missing": phase3.get("daily_review", {}).get("what_was_missing", [])[:10],
            "which_engines_were_weak": phase3.get("daily_review", {}).get("which_engines_were_weak", [])[:10],
            "what_to_study_next": phase3.get("daily_review", {}).get("what_to_study_next", [])[:10],
            "what_should_be_avoided_tomorrow": phase3.get("daily_review", {}).get("what_should_be_avoided_tomorrow", [])[:10],
            "what_needs_paper_testing": phase3.get("daily_review", {}).get("what_needs_paper_testing", [])[:10],
        },
        "phase3_learning_directives": phase3.get("learning_engine", {}).get("directives", [])[:20],
        "phase3_experience_clusters": phase3.get("experience_clustering", {}).get("clusters", [])[:20],
        "phase3_stock_personality_symbol_count": len(phase3.get("stock_personality", {}).get("symbols", {})),
        "phase3_confidence_recalibration": {
            "overconfidence_warnings": phase3.get("confidence_recalibration", {}).get("overconfidence_warnings", [])[:10],
            "weak_calibration_evidence": phase3.get("confidence_recalibration", {}).get("weak_calibration_evidence", [])[:10],
            "sample_size_warning": phase3.get("confidence_recalibration", {}).get("sample_size_warning"),
            "approved_for_test_only": phase3.get("confidence_recalibration", {}).get("approved_for_test_only"),
        },
        "phase3_world_model_memory": {
            "market_laws": phase3.get("world_model_memory", {}).get("market_laws", [])[:10],
            "engine_memory": phase3.get("world_model_memory", {}).get("engine_memory", {}),
        },
        "phase_a_institutional_reasoning": {
            "multi_agent_debate": {
                "final_debate_summary": phase_a.get("multi_agent_debate", {}).get("final_debate_summary"),
                "final_consensus": phase_a.get("multi_agent_debate", {}).get("final_consensus"),
                "contradiction_level": phase_a.get("multi_agent_debate", {}).get("contradiction_level"),
                "confidence_adjustment": phase_a.get("multi_agent_debate", {}).get("confidence_adjustment"),
                "suggested_action_bias": phase_a.get("multi_agent_debate", {}).get("suggested_action_bias"),
            },
            "deep_causal_reasoning": {
                "strongest_causal_chains": phase_a.get("deep_causal_reasoning", {}).get("strongest_causal_chains", [])[:10],
                "weakest_causal_links": phase_a.get("deep_causal_reasoning", {}).get("weakest_causal_links", [])[:10],
                "contradiction_chains": phase_a.get("deep_causal_reasoning", {}).get("contradiction_chains", [])[:10],
            },
            "manipulation_intelligence": {
                "suspicion_score": phase_a.get("manipulation_intelligence", {}).get("suspicion_score"),
                "manipulation_patterns": phase_a.get("manipulation_intelligence", {}).get("manipulation_patterns", [])[:10],
                "no_trade_recommendations": phase_a.get("manipulation_intelligence", {}).get("no_trade_recommendations", [])[:10],
            },
            "liquidity_intelligence": {
                "liquidity_regime": phase_a.get("liquidity_intelligence", {}).get("liquidity_regime"),
                "liquidity_stress": phase_a.get("liquidity_intelligence", {}).get("liquidity_stress", {}),
                "thin_liquidity": phase_a.get("liquidity_intelligence", {}).get("thin_liquidity"),
                "strong_participation": phase_a.get("liquidity_intelligence", {}).get("strong_participation"),
            },
            "autonomous_research": phase_a.get("autonomous_research", {}).get("ranked_discoveries", [])[:10],
            "world_model_expansion": {
                "macro_memory": phase_a.get("world_model_expansion", {}).get("macro_memory", {}),
                "liquidity_cycle_memory": phase_a.get("world_model_expansion", {}).get("liquidity_cycle_memory", {}),
                "confidence_reliability_memory": phase_a.get("world_model_expansion", {}).get("confidence_reliability_memory", {}),
            },
            "contradiction_arbitration": {
                "overall_severity": phase_a.get("contradiction_arbitration", {}).get("overall_severity"),
                "aggregate_confidence_adjustment": phase_a.get("contradiction_arbitration", {}).get("aggregate_confidence_adjustment"),
                "contradictions": phase_a.get("contradiction_arbitration", {}).get("contradictions", [])[:10],
            },
            "institutional_reasoning_summary": phase_a.get("institutional_reasoning_summary", {}),
        },
        "phase_b_recursive_intelligence": {
            "strategy_genome_survivors": phase_b.get("strategy_genome_evolution", {}).get("survivor_ranking", [])[:20],
            "recursive_meta_learning": phase_b.get("recursive_meta_learning", {}),
            "adaptive_attention": phase_b.get("adaptive_attention", {}).get("attention_items", [])[:20],
            "evolution_ecosystem": {
                "evolution_cycles": phase_b.get("evolution_ecosystem", {}).get("evolution_cycles"),
                "active_mutations": phase_b.get("evolution_ecosystem", {}).get("active_mutations", [])[:20],
                "retired_mutations": phase_b.get("evolution_ecosystem", {}).get("retired_mutations", [])[:20],
                "strongest_mutations": phase_b.get("evolution_ecosystem", {}).get("strongest_mutations", [])[:10],
                "weakest_mutations": phase_b.get("evolution_ecosystem", {}).get("weakest_mutations", [])[:10],
                "recurring_failures": phase_b.get("evolution_ecosystem", {}).get("recurring_failures", [])[:10],
                "recurring_successes": phase_b.get("evolution_ecosystem", {}).get("recurring_successes", [])[:10],
                "next_evolution_direction": phase_b.get("evolution_ecosystem", {}).get("next_evolution_direction"),
            },
            "intelligence_amplification": phase_b.get("intelligence_amplification", {}),
            "self_improvement_scoring": phase_b.get("self_improvement_scoring", {}),
            "autonomous_goal_hierarchy": {
                "top_goal": phase_b.get("autonomous_goal_hierarchy", {}).get("top_goal"),
                "ranked_goals": phase_b.get("autonomous_goal_hierarchy", {}).get("ranked_goals", [])[:20],
            },
            "recursive_world_model": {
                "macro_memory": phase_b.get("recursive_world_model", {}).get("macro_memory", {}),
                "liquidity_cycles": phase_b.get("recursive_world_model", {}).get("liquidity_cycles", {}),
                "volatility_cycles": phase_b.get("recursive_world_model", {}).get("volatility_cycles", {}),
                "manipulation_memory": phase_b.get("recursive_world_model", {}).get("manipulation_memory", {}),
                "adaptive_regime_memory": phase_b.get("recursive_world_model", {}).get("adaptive_regime_memory", {}),
            },
            "evolution_memory_civilization": {
                "short_term_memory": phase_b.get("evolution_memory_civilization", {}).get("short_term_memory", {}),
                "medium_term_memory": phase_b.get("evolution_memory_civilization", {}).get("medium_term_memory", {}),
                "long_term_memory": phase_b.get("evolution_memory_civilization", {}).get("long_term_memory", {}),
                "permanent_market_laws": phase_b.get("evolution_memory_civilization", {}).get("permanent_market_laws", [])[:20],
            },
            "recursive_intelligence_summary": phase_b.get("recursive_intelligence_summary", {}),
        },
        "next_focus": state.get("current_focus"),
    }
    atomic_write_json(path_json, report)
    lines = [
        "TITAN Consciousness Core v1",
        f"Generated: {report['generated_at']}",
        "",
        "Current understanding:",
        report["current_understanding"] or "No summary yet.",
        "",
        "Evidence:",
        f"- New evidence observations processed: {report['real_evidence_found']}",
        f"- Unchanged observations skipped by hash: {report['unchanged_observations_skipped']}",
        f"- Missing data patterns: {len(report['missing_data'])}",
        f"- Duplicate weaknesses merged: {report['duplicates_merged']}",
        f"- Missions consolidated: {report['consolidated_missions']}",
        f"- Proposals consolidated: {report['consolidated_proposals']}",
        "",
        "Active weaknesses:",
    ]
    if weaknesses:
        lines.extend(
            f"- {item.get('severity')} {item.get('type')} in {item.get('affected_engine')}: {item.get('recommended_investigation')}"
            for item in weaknesses[:10]
        )
    else:
        lines.append("- None detected from new evidence this cycle.")
    lines.append("")
    lines.append("Active goals:")
    lines.extend(f"- {goal.get('priority')}: {goal.get('title')}" for goal in goals[:10])
    lines.append("")
    lines.append("Top beliefs:")
    lines.extend(f"- {belief.get('confidence')}: {belief.get('statement')}" for belief in top_beliefs[:10])
    lines.append("")
    lines.append("Research missions:")
    lines.extend(f"- {mission.get('priority')}: {mission.get('title')}" for mission in missions[:10])
    lines.append("")
    lines.append("Improvement proposals:")
    lines.extend(
        f"- {proposal.get('proposal_id')}: {proposal.get('target_engine')} -> {proposal.get('suggested_action')}"
        for proposal in proposals[:10]
    )
    lines.append("")
    lines.append("Safety decisions:")
    lines.extend(f"- {proposal_id}: {decision}" for proposal_id, decision in safety_decisions.items())
    lines.append("")
    lines.append("Sandbox results:")
    if report["sandbox_results"]:
        lines.extend(
            f"- {item.get('proposal_id')}: {item.get('recommendation')} score={item.get('promotion_score')} risk={item.get('risk_score')}"
            for item in report["sandbox_results"][:10]
        )
    else:
        lines.append("- No sandbox evaluations this cycle.")
    lines.append("")
    lines.append("Promotion recommendations:")
    if report["promotion_recommendations"]:
        lines.extend(
            f"- {item.get('proposal_id')}: {item.get('status')} ({item.get('target_engine')})"
            for item in report["promotion_recommendations"][:10]
        )
    else:
        lines.append("- No promotion recommendations.")
    lines.append("")
    lines.append("Causal lessons:")
    if report["causal_lessons"]:
        lines.extend(
            f"- {item.get('cause_type')} -> {item.get('effect_type')}: {item.get('lesson')}"
            for item in report["causal_lessons"][:10]
        )
    else:
        lines.append("- No causal lessons yet.")
    lines.append("")
    lines.append("Experience memory highlights:")
    highlights = report["experience_memory_highlights"]
    lines.append(f"- Repeated failures: {len(highlights['repeated_failure_patterns'])}")
    lines.append(f"- Repeated successes: {len(highlights['repeated_success_patterns'])}")
    lines.append(f"- Weak engines: {', '.join(item.get('engine', '') for item in highlights['weak_engines']) or 'none'}")
    lines.append(f"- Strong engines: {', '.join(item.get('engine', '') for item in highlights['strong_engines']) or 'none'}")
    lines.append("")
    lines.append("Strategy mutations:")
    if report["strategy_mutations"]:
        lines.extend(
            f"- {item.get('mutation_id')}: {item.get('description')} [{item.get('apply_scope')}]"
            for item in report["strategy_mutations"][:10]
        )
    else:
        lines.append("- No mutation candidates.")
    lines.append("")
    lines.append("Meta-learning status:")
    meta = report["meta_learning"]
    if meta:
        lines.append(f"- Status: {meta.get('learning_status')}")
        lines.append(f"- Proposal quality: {meta.get('proposal_quality')}")
        lines.append(f"- Duplicate rate: {meta.get('duplicate_rate')}")
        lines.append(f"- Recurring weakness count: {meta.get('recurring_weakness_count')}")
    else:
        lines.append("- No meta-learning data yet.")
    lines.append("")
    lines.append("Phase 3 experiential intelligence:")
    phase3_review = report["phase3_daily_review"]
    lines.append(f"- Real experience failures: {len(report['phase3_real_experience_memory']['repeated_failure_patterns'])}")
    lines.append(f"- Daily review failures: {len(phase3_review['what_failed'])}")
    lines.append(f"- Learning directives: {len(report['phase3_learning_directives'])}")
    lines.append(f"- Experience clusters: {len(report['phase3_experience_clusters'])}")
    lines.append(f"- Stock personalities: {report['phase3_stock_personality_symbol_count']}")
    lines.append(f"- Confidence test-only: {report['phase3_confidence_recalibration'].get('approved_for_test_only')}")
    if phase3_review["what_to_study_next"]:
        lines.append("- Study next: " + "; ".join(phase3_review["what_to_study_next"][:5]))
    if report["phase3_world_model_memory"]["market_laws"]:
        lines.append("- Market law: " + report["phase3_world_model_memory"]["market_laws"][0])
    lines.append("")
    lines.append("Phase A institutional reasoning:")
    phase_a_report = report["phase_a_institutional_reasoning"]
    debate = phase_a_report["multi_agent_debate"]
    manipulation = phase_a_report["manipulation_intelligence"]
    liquidity = phase_a_report["liquidity_intelligence"]
    arbitration = phase_a_report["contradiction_arbitration"]
    institutional_summary = phase_a_report["institutional_reasoning_summary"]
    lines.append(f"- Debate consensus: {debate.get('final_consensus')}")
    lines.append(f"- Debate contradiction level: {debate.get('contradiction_level')}")
    lines.append(f"- Suggested action bias: {debate.get('suggested_action_bias')}")
    lines.append(f"- Liquidity regime: {liquidity.get('liquidity_regime')}")
    lines.append(f"- Liquidity stress: {liquidity.get('liquidity_stress', {}).get('state')} score={liquidity.get('liquidity_stress', {}).get('score')}")
    lines.append(f"- Manipulation suspicion: {manipulation.get('suspicion_score')}")
    lines.append(f"- Contradiction severity: {arbitration.get('overall_severity')} adjustment={arbitration.get('aggregate_confidence_adjustment')}")
    lines.append(f"- Research discoveries: {len(phase_a_report['autonomous_research'])}")
    lines.append(f"- Caution/aggression level: {institutional_summary.get('recommended_caution_aggression_level')}")
    if arbitration.get("contradictions"):
        lines.append("- Top contradiction: " + str(arbitration["contradictions"][0].get("type")))
    if institutional_summary.get("top_institutional_concerns"):
        lines.append("- Top concern: " + institutional_summary["top_institutional_concerns"][0])
    lines.append("- Safety: read-only, sandbox-safe, recommendation-only; no live mutation.")
    lines.append("")
    lines.append("Mega Phase B recursive intelligence:")
    phase_b_report = report["phase_b_recursive_intelligence"]
    meta_b = phase_b_report["recursive_meta_learning"]
    ecosystem_b = phase_b_report["evolution_ecosystem"]
    amplification_b = phase_b_report["intelligence_amplification"]
    score_b = phase_b_report["self_improvement_scoring"]
    summary_b = phase_b_report["recursive_intelligence_summary"]
    lines.append(f"- Recursive score: {score_b.get('overall_recursive_score')} status={score_b.get('recursive_growth_status')}")
    lines.append(f"- Meta self-improvement: {meta_b.get('self_improvement_score')} weakest={meta_b.get('weakest_meta_area')}")
    lines.append(f"- Evolution cycles: {ecosystem_b.get('evolution_cycles')} active={len(ecosystem_b.get('active_mutations', []))} retired={len(ecosystem_b.get('retired_mutations', []))}")
    lines.append(f"- Amplification: {amplification_b.get('amplification_score')} trend={amplification_b.get('improvement_trend')}")
    lines.append(f"- Recursive status: {summary_b.get('recursive_intelligence_status')}")
    if phase_b_report["adaptive_attention"]:
        top_attention = phase_b_report["adaptive_attention"][0]
        lines.append(f"- Top attention: {top_attention.get('focus_area')} weight={top_attention.get('resource_weight')} reason={top_attention.get('reason')}")
    if ecosystem_b.get("strongest_mutations"):
        top_mutation = ecosystem_b["strongest_mutations"][0]
        lines.append(f"- Strongest mutation: {top_mutation.get('genome_id')} score={top_mutation.get('sandbox_score')} risk={top_mutation.get('risk_score')}")
    if ecosystem_b.get("weakest_mutations"):
        weak_mutation = ecosystem_b["weakest_mutations"][0]
        lines.append(f"- Weakest mutation: {weak_mutation.get('genome_id')} score={weak_mutation.get('sandbox_score')} risk={weak_mutation.get('risk_score')}")
    lines.append("- Safety: Phase B is read-only, sandbox-safe, recommendation-only, and cannot mutate live strategies or execution.")
    lines.append("")
    lines.append("Insufficient evidence areas:")
    if report["insufficient_evidence_areas"]:
        lines.extend(f"- {proposal_id}" for proposal_id in report["insufficient_evidence_areas"])
    else:
        lines.append("- None from this cycle.")
    lines.append("")
    lines.append("Missing data:")
    if report["missing_data"]:
        lines.extend(f"- {pattern}" for pattern in report["missing_data"][:20])
    else:
        lines.append("- No configured source patterns missing.")
    lines.append("")
    lines.append(f"Next focus: {report['next_focus']}")
    path_txt.parent.mkdir(parents=True, exist_ok=True)
    path_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
