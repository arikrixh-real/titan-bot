from pathlib import Path

from consciousness_core.deduplication import SEVERITY_RANK, append_evidence, proposal_key, stronger_label
from consciousness_core.state import atomic_write_json, now_ist, stable_hash


QUEUE_PATH = Path("data") / "consciousness_core" / "improvement_queue.json"
LAST_CONSOLIDATED_PROPOSALS = 0


def get_last_consolidated_proposals():
    return LAST_CONSOLIDATED_PROPOSALS


def load_improvement_queue(path=QUEUE_PATH):
    try:
        import json

        with Path(path).open("r", encoding="utf-8") as queue_file:
            payload = json.load(queue_file)
        if isinstance(payload, list):
            return payload
    except Exception:
        pass
    return []


def _proposal(title, reason, evidence, risk_level, target_engine, suggested_action, parameter_hint):
    return {
        "proposal_id": "proposal_" + stable_hash([title, target_engine, reason])[:16],
        "title": title,
        "reason": reason,
        "evidence": evidence,
        "risk_level": risk_level,
        "target_engine": target_engine,
        "suggested_action": suggested_action,
        "parameter_hint": parameter_hint,
        "requires_backtest": True,
        "status": "PROPOSED",
        "created_at": now_ist(),
        "updated_at": now_ist(),
    }


def create_improvement_proposals(weaknesses, goals, missions, path=QUEUE_PATH):
    global LAST_CONSOLIDATED_PROPOSALS
    LAST_CONSOLIDATED_PROPOSALS = 0
    proposals = []
    for weakness in weaknesses[:30]:
        weakness_type = weakness.get("type")
        evidence = weakness.get("evidence", [])
        reason = weakness.get("recommended_investigation") or weakness.get("proposed_action") or weakness_type
        if weakness_type in {"weak_confidence_calibration", "confidence_warning"}:
            proposals.append(
                _proposal(
                    "Reduce weak confidence contribution",
                    reason,
                    evidence,
                    "MEDIUM",
                    "confidence_calibration",
                    "reduce confidence contribution from weak calibration or weak news score during backtest/paper validation",
                    {"confidence_weight_delta": -0.05, "minimum_calibration_sample_size": 20},
                )
            )
        elif weakness_type == "high_confidence_loss":
            proposals.append(
                _proposal(
                    "Require sector confirmation after failed high-confidence trades",
                    reason,
                    evidence,
                    "MEDIUM",
                    "setup_engine",
                    "require sector confirmation after similar failed high-confidence trades in test mode",
                    {"require_sector_confirmation": True, "scope": "paper_or_backtest"},
                )
            )
        elif weakness_type in {"no_trade_warning", "regime_warning"}:
            proposals.append(
                _proposal(
                    "Tighten filter in CHOPPY_NO_EDGE or contradictory regimes",
                    reason,
                    evidence,
                    "MEDIUM",
                    "no_trade",
                    "increase no-trade protection when contradiction or choppy-no-edge evidence is high",
                    {"choppy_no_edge_threshold_delta": -0.05, "contradiction_warning_weight_delta": 0.1},
                )
            )
        elif weakness_type in {"worker_failure", "repeated_worker_failures"}:
            proposals.append(
                _proposal(
                    "Investigate worker reliability before consuming its output",
                    reason,
                    evidence,
                    "LOW",
                    weakness.get("affected_engine") or "runtime_continuous_workers",
                    "add diagnostics and mark stale/failed worker output as low-trust for downstream intelligence",
                    {"trust_multiplier_delta": -0.2, "requires_runtime_health_check": True},
                )
            )
        elif weakness_type == "placeholder_important_worker":
            proposals.append(
                _proposal(
                    "Investigate placeholder worker replacement",
                    reason,
                    evidence,
                    "LOW",
                    weakness.get("affected_engine") or "runtime_registry",
                    "replace placeholder with a read-only real implementation or explicitly reduce coverage assumptions",
                    {"coverage_assumption": "unavailable_until_implemented"},
                )
            )
        elif weakness_type == "poor_backtesting_validation":
            proposals.append(
                _proposal(
                    "Require validation before promotion",
                    reason,
                    evidence,
                    "LOW",
                    "backtesting",
                    "block strategy parameter promotion unless backtest/paper validation has non-zero sample coverage",
                    {"minimum_backtest_sample_size": 20, "minimum_walk_forward_windows": 3},
                )
            )
        elif weakness_type in {"missing_critical_report", "missing_optional_data"}:
            proposals.append(
                _proposal(
                    "Improve evidence availability",
                    reason,
                    evidence,
                    "LOW",
                    "research_pipeline",
                    "study missing source before drawing strategy conclusions",
                    {"missing_source_policy": "insufficient_evidence"},
                )
            )
        elif weakness_type == "evolution_stagnation":
            proposals.append(
                _proposal(
                    "Keep evolution conservative until sample grows",
                    reason,
                    evidence,
                    "LOW",
                    "evolution_engine",
                    "hold changes in proposal queue until closed trade sample size improves",
                    {"minimum_closed_trades": 5},
                )
            )
        elif weakness_type == "strategy_underperformance":
            proposals.append(
                _proposal(
                    "Tighten underperforming setup filters",
                    reason,
                    evidence,
                    "MEDIUM",
                    "setup_engine",
                    "tighten filters for underperforming setup clusters in backtest only",
                    {"filter_strictness_delta": 0.05, "apply_mode": "backtest_only"},
                )
            )
    if not proposals:
        proposals.append(
            _proposal(
                "Study before applying",
                "no high-severity weakness detected in current cycle",
                [],
                "LOW",
                "consciousness_core",
                "continue observation and avoid live strategy mutation",
                {"action": "observe_only"},
            )
        )
    existing = {}
    existing_by_key = {}
    for stored in load_improvement_queue(path):
        if not isinstance(stored, dict) or not stored.get("proposal_id"):
            continue
        key = proposal_key(stored)
        current = existing_by_key.get(key)
        if current:
            LAST_CONSOLIDATED_PROPOSALS += 1
            current["evidence"] = append_evidence(current.get("evidence"), stored.get("evidence"))
            current["risk_level"] = stronger_label(current.get("risk_level"), stored.get("risk_level"), SEVERITY_RANK)
            current["updated_at"] = now_ist()
            continue
        existing[stored["proposal_id"]] = stored
        existing_by_key[key] = stored
    unique_proposals = {}
    for proposal in proposals:
        key = proposal_key(proposal)
        current = existing_by_key.get(key)
        if current:
            LAST_CONSOLIDATED_PROPOSALS += 1
            current["evidence"] = append_evidence(current.get("evidence"), proposal.get("evidence"))
            current["risk_level"] = stronger_label(current.get("risk_level"), proposal.get("risk_level"), SEVERITY_RANK)
            current["reason"] = current.get("reason") or proposal.get("reason")
            current["updated_at"] = now_ist()
            unique_proposals[current["proposal_id"]] = current
            continue
        existing[proposal["proposal_id"]] = proposal
        existing_by_key[key] = proposal
        unique_proposals[proposal["proposal_id"]] = proposal
    queue = list(existing.values())[-200:]
    atomic_write_json(path, queue)
    return list(unique_proposals.values())
