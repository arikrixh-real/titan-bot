import time
from pathlib import Path

from consciousness_core.belief_graph import (
    decay_stale_beliefs,
    get_last_beliefs_consolidated,
    load_beliefs,
    reset_belief_consolidation_count,
    save_beliefs,
    update_belief,
    update_beliefs_from_weaknesses,
)
from consciousness_core.causal_reasoning import run_causal_reasoning
from consciousness_core.confidence_recalibration import run_confidence_recalibration
from consciousness_core.data_collector import collect_observations
from consciousness_core.daily_review_engine import run_daily_review_engine
from consciousness_core.evolution_bridge import get_last_bridge_dedup_count, write_evolution_bridge_queue
from consciousness_core.experience_clustering import run_experience_clustering
from consciousness_core.experience_memory import update_experience_memory
from consciousness_core.goal_manager import update_goals
from consciousness_core.improvement_planner import create_improvement_proposals, get_last_consolidated_proposals
from consciousness_core.internal_question_engine import generate_internal_questions
from consciousness_core.learning_engine import run_learning_engine
from consciousness_core.meta_learning import run_meta_learning
from consciousness_core.promotion_gate import run_promotion_gate
from consciousness_core.real_experience_memory import run_real_experience_memory
from consciousness_core.reflection_engine import reflect
from consciousness_core.report import write_report
from consciousness_core.research_lab import run_research_lab
from consciousness_core.research_mission_generator import generate_research_missions, get_last_consolidated_missions
from consciousness_core.sandbox_evolution import run_sandbox_evolution
from consciousness_core.safety_gate import evaluate_proposal
from consciousness_core.state import atomic_write_json, load_state, now_ist, save_state
from consciousness_core.stock_personality import run_stock_personality
from consciousness_core.strategy_mutation_lab import run_strategy_mutation_lab
from consciousness_core.thought_memory import (
    append_internal_narrative,
    append_reflection,
    append_thought,
)
from consciousness_core.weakness_hunter import get_last_duplicates_merged, hunt_weaknesses
from consciousness_core.world_model_memory import run_world_model_memory
from consciousness_core.world_graph import update_world_graph


HEALTH_PATH = Path("data") / "consciousness_core" / "consciousness_health.json"
CONTEXT_PATH = Path("data") / "consciousness_core" / "consciousness_context.json"


def _summary(observation_packet, reflection, weaknesses, proposals, approved_count):
    return (
        f"Processed {observation_packet.get('observation_count', 0)} sources; "
        f"found {len(weaknesses)} weaknesses; "
        f"created {len(proposals)} proposals; "
        f"{approved_count} approved for test. "
        f"Lessons: {'; '.join(reflection.get('lessons', [])[:2])}"
    )


def _write_health(payload):
    atomic_write_json(HEALTH_PATH, payload)


def _write_context(state, weaknesses, beliefs, missions, approved_queue, phase2=None, phase3=None):
    phase2 = phase2 or {}
    phase3 = phase3 or {}
    top_beliefs = sorted(
        beliefs.values(),
        key=lambda belief: float(belief.get("confidence") or 0),
        reverse=True,
    )[:10]
    no_trade_warnings = [
        weakness for weakness in weaknesses if weakness.get("type") in {"no_trade_warning", "regime_warning"}
    ]
    confidence_warnings = [
        weakness
        for weakness in weaknesses
        if weakness.get("type") in {"weak_confidence_calibration", "high_confidence_loss", "confidence_warning"}
    ]
    context = {
        "current_focus": state.get("current_focus"),
        "active_regime_warnings": no_trade_warnings[:10],
        "top_weaknesses": weaknesses[:10],
        "active_beliefs": top_beliefs,
        "approved_test_proposals": approved_queue[:20],
        "research_priorities": missions[:10],
        "no_trade_warnings": no_trade_warnings[:10],
        "confidence_warnings": confidence_warnings[:10],
        "sandbox_results": phase2.get("sandbox_results", {}).get("results", [])[:10],
        "promotion_recommendations": phase2.get("promotion_recommendations", {}).get("recommendations", [])[:10],
        "causal_lessons": phase2.get("causal_reasoning", {}).get("causal_lessons", [])[:10],
        "experience_memory_highlights": {
            "repeated_failure_patterns": phase2.get("experience_memory", {}).get("repeated_failure_patterns", [])[:5],
            "repeated_success_patterns": phase2.get("experience_memory", {}).get("repeated_success_patterns", [])[:5],
            "weak_engines": phase2.get("experience_memory", {}).get("weak_engines", [])[:5],
            "strong_engines": phase2.get("experience_memory", {}).get("strong_engines", [])[:5],
        },
        "strategy_mutations": phase2.get("strategy_mutations", {}).get("mutations", [])[:10],
        "meta_learning": phase2.get("meta_learning", {}),
        "real_experience_memory": {
            "repeated_failure_patterns": phase3.get("real_experience_memory", {}).get("repeated_failure_patterns", [])[:5],
            "repeated_success_patterns": phase3.get("real_experience_memory", {}).get("repeated_success_patterns", [])[:5],
            "engine_reliability_memory": phase3.get("real_experience_memory", {}).get("engine_reliability_memory", [])[:5],
        },
        "daily_review": {
            "what_worked": phase3.get("daily_review", {}).get("what_worked", [])[:5],
            "what_failed": phase3.get("daily_review", {}).get("what_failed", [])[:5],
            "which_engines_were_weak": phase3.get("daily_review", {}).get("which_engines_were_weak", [])[:5],
            "what_to_study_next": phase3.get("daily_review", {}).get("what_to_study_next", [])[:5],
        },
        "learning_directives": phase3.get("learning_engine", {}).get("directives", [])[:10],
        "experience_clusters": phase3.get("experience_clustering", {}).get("clusters", [])[:10],
        "stock_personality": phase3.get("stock_personality", {}).get("symbols", {}),
        "confidence_recalibration": {
            "weak_calibration_evidence": phase3.get("confidence_recalibration", {}).get("weak_calibration_evidence", [])[:10],
            "sample_size_warning": phase3.get("confidence_recalibration", {}).get("sample_size_warning"),
            "approved_for_test_only": phase3.get("confidence_recalibration", {}).get("approved_for_test_only"),
        },
        "world_model_memory": {
            "market_laws": phase3.get("world_model_memory", {}).get("market_laws", [])[:10],
            "engine_memory": phase3.get("world_model_memory", {}).get("engine_memory", {}),
        },
    }
    atomic_write_json(CONTEXT_PATH, context)
    return context


def run_consciousness_core(state=None, state_path=None, intelligence_state=None):
    started = time.monotonic()
    core_state = None
    try:
        core_state, core_state_path = load_state()
        observation_packet = collect_observations()
        observations = observation_packet.get("observations", [])
        beliefs = decay_stale_beliefs(load_beliefs())
        reset_belief_consolidation_count()
        questions = generate_internal_questions(observation_packet, core_state)
        reflection = reflect(observation_packet, core_state, beliefs)
        update_world_graph(observations, reflection.get("lessons"))

        if observation_packet.get("observation_count", 0) > 0:
            for lesson in reflection.get("lessons", []):
                update_belief(
                    beliefs,
                    lesson,
                    evidence={"source": "reflection_engine", "cycle": core_state.get("consciousness_cycle")},
                )
        for contradiction in reflection.get("contradictions", []):
            update_belief(
                beliefs,
                contradiction,
                evidence={"source": "reflection_engine", "cycle": core_state.get("consciousness_cycle")},
                contradiction=True,
            )
        weaknesses = hunt_weaknesses(observation_packet, reflection)
        beliefs = update_beliefs_from_weaknesses(beliefs, weaknesses)
        save_beliefs(beliefs)
        goals = update_goals(weaknesses, reflection)
        missions = generate_research_missions(weaknesses, goals)
        proposals = create_improvement_proposals(weaknesses, goals, missions)
        safety_decisions = {
            proposal["proposal_id"]: evaluate_proposal(proposal) for proposal in proposals
        }
        approved_queue = write_evolution_bridge_queue(proposals, safety_decisions)
        sandbox_results = run_sandbox_evolution()
        experience_memory = update_experience_memory()
        causal_reasoning = run_causal_reasoning()
        research_experiments = run_research_lab()
        strategy_mutations = run_strategy_mutation_lab()
        promotion_recommendations = run_promotion_gate()
        meta_learning = run_meta_learning()
        phase2 = {
            "sandbox_results": sandbox_results,
            "experience_memory": experience_memory,
            "causal_reasoning": causal_reasoning,
            "research_experiments": research_experiments,
            "strategy_mutations": strategy_mutations,
            "promotion_recommendations": promotion_recommendations,
            "meta_learning": meta_learning,
        }
        real_experience_memory = run_real_experience_memory()
        daily_review = run_daily_review_engine()
        learning_directives = run_learning_engine()
        experience_clusters = run_experience_clustering()
        stock_personality = run_stock_personality()
        confidence_recalibration = run_confidence_recalibration()
        world_model_memory = run_world_model_memory()
        phase3 = {
            "real_experience_memory": real_experience_memory,
            "daily_review": daily_review,
            "learning_engine": learning_directives,
            "experience_clustering": experience_clusters,
            "stock_personality": stock_personality,
            "confidence_recalibration": confidence_recalibration,
            "world_model_memory": world_model_memory,
        }
        consolidation_stats = {
            "duplicates_merged": get_last_duplicates_merged(),
            "consolidated_missions": get_last_consolidated_missions(),
            "consolidated_proposals": get_last_consolidated_proposals() + get_last_bridge_dedup_count(),
            "consolidated_beliefs": get_last_beliefs_consolidated(),
        }
        context = _write_context(core_state, weaknesses, beliefs, missions, approved_queue, phase2=phase2, phase3=phase3)
        approved_count = len(approved_queue)
        rejected_count = list(safety_decisions.values()).count("REJECTED")
        summary = _summary(observation_packet, reflection, weaknesses, proposals, approved_count)

        append_thought(
            {
                "event_type": "consciousness_cycle",
                "cycle": core_state.get("consciousness_cycle"),
                "observation_hash": observation_packet.get("observation_hash"),
                "summary": summary,
                "questions": questions,
            }
        )
        append_reflection(
            {
                "event_type": "reflection",
                "cycle": core_state.get("consciousness_cycle"),
                "reflection": reflection,
            }
        )
        append_internal_narrative(
            {
                "event_type": "internal_narrative",
                "cycle": core_state.get("consciousness_cycle"),
                "narrative": summary,
                "next_focus": "verify weaknesses and promote only test-safe proposals",
            }
        )

        runtime_seconds = time.monotonic() - started
        core_state["run_count"] = int(core_state.get("run_count") or 0) + 1
        core_state["consciousness_cycle"] = int(core_state.get("consciousness_cycle") or 0) + 1
        core_state["current_mode"] = "OBSERVE_REFLECT_PROPOSE"
        core_state["current_focus"] = "verify weaknesses and promote only test-safe proposals"
        core_state["last_status"] = "OK"
        core_state["last_error"] = None
        core_state["cumulative_runtime_seconds"] = float(core_state.get("cumulative_runtime_seconds") or 0.0) + runtime_seconds
        core_state["memory_cursor"] = int(core_state.get("memory_cursor") or 0) + len(observations)
        core_state["thought_cursor"] = int(core_state.get("thought_cursor") or 0) + 1
        core_state["belief_generation"] = int(core_state.get("belief_generation") or 0) + 1
        core_state["evolution_generation"] = int(core_state.get("evolution_generation") or 0) + approved_count
        core_state["last_observation_hash"] = observation_packet.get("observation_hash")
        core_state["active_goals"] = [goal.get("title") for goal in goals if goal.get("status") == "ACTIVE"][:20]
        core_state["open_questions"] = questions
        core_state["active_weaknesses"] = weaknesses[:20]
        core_state["latest_summary"] = summary
        core_state = save_state(core_state, core_state_path)
        context = _write_context(core_state, weaknesses, beliefs, missions, approved_queue, phase2=phase2, phase3=phase3)

        report = write_report(
            core_state,
            reflection,
            weaknesses,
            goals,
            beliefs,
            missions,
            proposals,
            safety_decisions,
            observation_packet=observation_packet,
            approved_queue=approved_queue,
            consolidation_stats=consolidation_stats,
            phase2=phase2,
            phase3=phase3,
        )
        health = {
            "status": "OK",
            "last_run_at": now_ist(),
            "run_count": core_state.get("run_count"),
            "observations_processed": observation_packet.get("observation_count", 0),
            "beliefs_count": len(beliefs),
            "goals_count": len(goals),
            "weaknesses_count": len(weaknesses),
            "proposals_count": len(proposals),
            "duplicates_merged": consolidation_stats["duplicates_merged"],
            "consolidated_missions": consolidation_stats["consolidated_missions"],
            "consolidated_proposals": consolidation_stats["consolidated_proposals"],
            "consolidated_beliefs": consolidation_stats["consolidated_beliefs"],
            "approved_for_test_count": approved_count,
            "rejected_count": rejected_count,
            "context_path": str(CONTEXT_PATH),
            "last_error": None,
        }
        _write_health(health)

        if isinstance(state, dict):
            state["consciousness_core_state_path"] = str(core_state_path)
            state["consciousness_context_path"] = str(CONTEXT_PATH)
            state["consciousness_summary"] = summary
        if isinstance(intelligence_state, dict) and intelligence_state is not state:
            intelligence_state["consciousness_core_state_path"] = str(core_state_path)
            intelligence_state["consciousness_context_path"] = str(CONTEXT_PATH)
            intelligence_state["consciousness_summary"] = summary

        return {
            "status": "ok",
            "state_path": str(core_state_path),
            "health_path": str(HEALTH_PATH),
            "context_path": str(CONTEXT_PATH),
            "report": report,
        }
    except Exception as exc:
        if core_state is not None:
            core_state["last_status"] = "ERROR"
            core_state["last_error"] = str(exc)
            save_state(core_state)
        _write_health(
            {
                "status": "ERROR",
                "last_run_at": now_ist(),
                "run_count": (core_state or {}).get("run_count", 0),
                "observations_processed": 0,
                "beliefs_count": 0,
                "goals_count": 0,
                "weaknesses_count": 0,
                "proposals_count": 0,
                "approved_for_test_count": 0,
                "rejected_count": 0,
                "last_error": str(exc),
            }
        )
        return {"status": "error", "error": str(exc)}
