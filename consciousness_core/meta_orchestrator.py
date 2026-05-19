import time
from pathlib import Path

from consciousness_core.belief_graph import (
    decay_stale_beliefs,
    load_beliefs,
    save_beliefs,
    update_belief,
    update_beliefs_from_weaknesses,
)
from consciousness_core.data_collector import collect_observations
from consciousness_core.evolution_bridge import write_evolution_bridge_queue
from consciousness_core.goal_manager import update_goals
from consciousness_core.improvement_planner import create_improvement_proposals
from consciousness_core.internal_question_engine import generate_internal_questions
from consciousness_core.reflection_engine import reflect
from consciousness_core.report import write_report
from consciousness_core.research_mission_generator import generate_research_missions
from consciousness_core.safety_gate import evaluate_proposal
from consciousness_core.state import atomic_write_json, load_state, now_ist, save_state
from consciousness_core.thought_memory import (
    append_internal_narrative,
    append_reflection,
    append_thought,
)
from consciousness_core.weakness_hunter import hunt_weaknesses
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


def _write_context(state, weaknesses, beliefs, missions, approved_queue):
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
        context = _write_context(core_state, weaknesses, beliefs, missions, approved_queue)
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
        context = _write_context(core_state, weaknesses, beliefs, missions, approved_queue)

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
