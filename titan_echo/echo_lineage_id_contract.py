"""Persistent lineage ID contract for TITAN outcome truth.

Design-only audit output. This script defines the target ID contract and the
writer adoption plan; it does not alter any runtime writer behavior.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
LINEAGE_SUMMARY_PATH = RUNTIME_ECHO_DIR / "outcome_lineage_summary.json"
CONTRACT_PATH = RUNTIME_ECHO_DIR / "lineage_id_contract.json"
ADOPTION_PLAN_PATH = RUNTIME_ECHO_DIR / "lineage_writer_adoption_plan.json"
SUMMARY_PATH = RUNTIME_ECHO_DIR / "lineage_id_contract_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))

STANDARD_IDS = (
    "setup_id",
    "decision_id",
    "trace_id",
    "trade_id",
    "outcome_id",
    "learning_event_id",
    "evolution_event_id",
)

WRITER_CATEGORIES = (
    "setup writer",
    "scanner/final_validated_setups writer",
    "Master Brain decision writer",
    "Unified Brain shadow trace writer",
    "paper/live trade journal writer",
    "outcome tracker writer",
    "learning writer",
    "evolution writer",
)

ID_FIELD_PATTERN = re.compile(
    r"\b(setup_id|signal_id|decision_id|trace_id|trade_id|paper_trade_id|outcome_id|"
    r"learning_event_id|evolution_event_id|candidate_id|scan_id)\b"
)


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def fields_found(paths: list[str]) -> list[str]:
    found: set[str] = set()
    for item in paths:
        path = REPO_ROOT / item
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        found.update(match.group(1) for match in ID_FIELD_PATTERN.finditer(text))
    return sorted(found)


def id_contract() -> dict[str, dict[str, Any]]:
    return {
        "setup_id": {
            "purpose": "Stable root identifier for a validated setup before any decision, trade, or learning record exists.",
            "required_fields": ["symbol", "direction", "setup_timestamp_ist", "strategy_family", "timeframe"],
            "generation_rule": "setup-{sha256(symbol|direction|setup_timestamp_ist|strategy_family|timeframe)[:16]}",
            "parent_id": None,
            "child_ids": ["decision_id", "trace_id"],
            "owning_writer": "setup writer",
            "required_downstream_readers": [
                "scanner/final_validated_setups writer",
                "Master Brain decision writer",
                "Unified Brain shadow trace writer",
                "paper/live trade journal writer",
            ],
        },
        "decision_id": {
            "purpose": "Stable identifier for a Master Brain decision made against one setup.",
            "required_fields": ["setup_id", "decision_timestamp_ist", "decision_action", "decision_engine_version"],
            "generation_rule": "decision-{sha256(setup_id|decision_timestamp_ist|decision_action|decision_engine_version)[:16]}",
            "parent_id": "setup_id",
            "child_ids": ["trade_id", "trace_id"],
            "owning_writer": "Master Brain decision writer",
            "required_downstream_readers": [
                "paper/live trade journal writer",
                "Unified Brain shadow trace writer",
                "outcome tracker writer",
            ],
        },
        "trace_id": {
            "purpose": "Stable identifier for a shadow-only reasoning/replay trace linked to setup and decision evidence.",
            "required_fields": ["setup_id", "decision_id", "trace_timestamp_ist", "trace_source", "symbol"],
            "generation_rule": "trace-{sha256(setup_id|decision_id|trace_timestamp_ist|trace_source|symbol)[:16]}",
            "parent_id": "decision_id",
            "child_ids": ["outcome_id", "learning_event_id"],
            "owning_writer": "Unified Brain shadow trace writer",
            "required_downstream_readers": [
                "outcome tracker writer",
                "learning writer",
                "evolution writer",
            ],
        },
        "trade_id": {
            "purpose": "Stable identifier for a paper or live trade journal row created from a decision.",
            "required_fields": ["decision_id", "symbol", "side", "entry", "stop_loss", "target", "opened_at_ist"],
            "generation_rule": "trade-{sha256(decision_id|symbol|side|entry|stop_loss|target|opened_at_ist)[:16]}",
            "parent_id": "decision_id",
            "child_ids": ["outcome_id"],
            "owning_writer": "paper/live trade journal writer",
            "required_downstream_readers": [
                "outcome tracker writer",
                "learning writer",
                "evolution writer",
            ],
        },
        "outcome_id": {
            "purpose": "Stable identifier for the realized result of one trade or exact replay trace.",
            "required_fields": ["trade_id", "trace_id", "outcome_timestamp_ist", "result", "exit_price"],
            "generation_rule": "outcome-{sha256((trade_id or trace_id)|outcome_timestamp_ist|result|exit_price)[:16]}",
            "parent_id": "trade_id or trace_id",
            "child_ids": ["learning_event_id"],
            "owning_writer": "outcome tracker writer",
            "required_downstream_readers": ["learning writer", "evolution writer"],
        },
        "learning_event_id": {
            "purpose": "Stable identifier for one learning update produced from outcome evidence.",
            "required_fields": ["outcome_id", "learning_timestamp_ist", "learning_type", "model_scope"],
            "generation_rule": "learn-{sha256(outcome_id|learning_timestamp_ist|learning_type|model_scope)[:16]}",
            "parent_id": "outcome_id",
            "child_ids": ["evolution_event_id"],
            "owning_writer": "learning writer",
            "required_downstream_readers": ["evolution writer", "audit/reporting readers"],
        },
        "evolution_event_id": {
            "purpose": "Stable identifier for one evolution proposal, parameter change request, or self-improvement event.",
            "required_fields": ["learning_event_id", "evolution_timestamp_ist", "proposal_type", "target_component"],
            "generation_rule": "evolve-{sha256(learning_event_id|evolution_timestamp_ist|proposal_type|target_component)[:16]}",
            "parent_id": "learning_event_id",
            "child_ids": [],
            "owning_writer": "evolution writer",
            "required_downstream_readers": ["audit/reporting readers"],
        },
    }


def writer_specs() -> list[dict[str, Any]]:
    specs = [
        {
            "writer_category": "setup writer",
            "file_module": ["engines/setup_engine.py"],
            "required_ids": ["setup_id"],
            "adoption_risk": "LOW",
            "required_future_patch": "Add setup_id forward-only when a setup object is first materialized; do not alter ranking, filtering, or trade selection.",
            "verification_test_needed": "Generate a dry-run setup fixture and assert setup_id is stable for identical normalized setup fields.",
        },
        {
            "writer_category": "scanner/final_validated_setups writer",
            "file_module": [
                "data/runtime/final_validated_setups.json",
                "dashboard_truth_foundation.py",
            ],
            "required_ids": ["setup_id"],
            "adoption_risk": "LOW",
            "required_future_patch": "Persist setup_id into final_validated_setups records forward-only while preserving existing scan_id/candidate_id fields.",
            "verification_test_needed": "Assert every new final_validated_setups row has setup_id and no duplicate setup_id within the write batch.",
        },
        {
            "writer_category": "Master Brain decision writer",
            "file_module": [
                "data/runtime/master_brain_status.json",
                "data/runtime/truth_gate_status.json",
            ],
            "required_ids": ["setup_id", "decision_id"],
            "adoption_risk": "MEDIUM",
            "required_future_patch": "Attach decision_id to decision records using setup_id as parent; keep decision verdict and gating behavior unchanged.",
            "verification_test_needed": "Replay one decision fixture and assert decision_id persists to all decision status/report outputs.",
        },
        {
            "writer_category": "Unified Brain shadow trace writer",
            "file_module": [
                "unified_brain/unified_brain_trace_experiment.py",
                "unified_brain/unified_brain_exact_trace_replay_expansion.py",
            ],
            "required_ids": ["setup_id", "decision_id", "trace_id"],
            "adoption_risk": "LOW",
            "required_future_patch": "Carry setup_id and decision_id into shadow traces; keep trace_id shadow-only and keep live_decision_allowed false.",
            "verification_test_needed": "Assert each new trace has setup_id, decision_id, trace_id, and no execution/influence fields are introduced.",
        },
        {
            "writer_category": "paper/live trade journal writer",
            "file_module": [
                "journal/trade_journal.py",
                "journal/trade_execution_layer.py",
                "engines/paper_trading_engine.py",
            ],
            "required_ids": ["setup_id", "decision_id", "trade_id"],
            "adoption_risk": "HIGH",
            "required_future_patch": "Extend journal rows with setup_id and decision_id while preserving canonical trade_id and paper_trade_id compatibility.",
            "verification_test_needed": "Write paper-trade fixture and assert trade_id links to exactly one decision_id and one setup_id.",
        },
        {
            "writer_category": "outcome tracker writer",
            "file_module": ["journal/outcome_tracker.py"],
            "required_ids": ["setup_id", "decision_id", "trace_id", "trade_id", "outcome_id"],
            "adoption_risk": "HIGH",
            "required_future_patch": "Create outcome_id when closing a paper/live trade or exact replay outcome; mark legacy_unlinked when no safe parent ID exists.",
            "verification_test_needed": "Close one fixture trade and assert one outcome_id, one parent trade_id or trace_id, and zero ambiguous parent links.",
        },
        {
            "writer_category": "learning writer",
            "file_module": [
                "engines/adaptive_memory_builder.py",
                "engines/strategy_family_memory.py",
                "engines/accuracy_validation_framework.py",
                "data/learning/reinforcement_learning_reports.jsonl",
            ],
            "required_ids": ["outcome_id", "learning_event_id"],
            "adoption_risk": "HIGH",
            "required_future_patch": "Emit learning_event_id per learning update and require outcome_id for non-legacy learning records.",
            "verification_test_needed": "Run a learning fixture and assert learning_event_id joins to exactly one outcome_id.",
        },
        {
            "writer_category": "evolution writer",
            "file_module": [
                "learning_evolution_truth.py",
                "data/evolution/proposals/self_improvement_proposals.json",
                "data/runtime/evolution_engine_status.json",
            ],
            "required_ids": ["learning_event_id", "evolution_event_id"],
            "adoption_risk": "HIGH",
            "required_future_patch": "Emit evolution_event_id for proposals and carry parent learning_event_id; legacy proposals remain legacy_unlinked if unsafe.",
            "verification_test_needed": "Create a proposal fixture and assert evolution_event_id joins to exactly one learning_event_id.",
        },
    ]
    for spec in specs:
        current = fields_found(spec["file_module"])
        required = set(spec["required_ids"])
        spec["current_id_fields_found"] = current
        spec["missing_id_fields"] = sorted(required - set(current))
    return specs


def safety_rules() -> list[str]:
    return [
        "Do not create duplicate IDs.",
        "Do not overwrite old records.",
        "Add IDs forward-only.",
        "Preserve backward compatibility.",
        "Existing old records should be marked legacy_unlinked if no safe link exists.",
        "Never infer a parent link from symbol-only or date-only matches.",
        "Require deterministic normalized fields for every generated ID.",
        "Keep ID adoption separate from ranking, execution, risk, and live decision behavior.",
    ]


def build_outputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    lineage_summary = read_json(LINEAGE_SUMMARY_PATH, {})
    contract = {
        "schema": "titan.echo.lineage_id_contract.v1",
        "timestamp_ist": timestamp_ist(),
        "source_evidence": {
            "batch1_summary_path": rel(LINEAGE_SUMMARY_PATH),
            "lineage_completeness_score": lineage_summary.get("lineage_completeness_score"),
            "traceability_score": lineage_summary.get("traceability_score"),
            "learning_linkage_score": lineage_summary.get("learning_linkage_score"),
            "evolution_linkage_score": lineage_summary.get("evolution_linkage_score"),
            "orphan_count": lineage_summary.get("orphan_count"),
            "duplicate_id_count": lineage_summary.get("duplicate_id_count"),
            "ambiguous_link_count": lineage_summary.get("ambiguous_link_count"),
        },
        "standard_ids": id_contract(),
        "safety_rules": safety_rules(),
    }
    writers = writer_specs()
    high_risk = [item["writer_category"] for item in writers if item["adoption_risk"] == "HIGH"]
    recommended_order = [
        "setup writer",
        "scanner/final_validated_setups writer",
        "Master Brain decision writer",
        "Unified Brain shadow trace writer",
        "paper/live trade journal writer",
        "outcome tracker writer",
        "learning writer",
        "evolution writer",
    ]
    adoption_plan = {
        "schema": "titan.echo.lineage_writer_adoption_plan.v1",
        "timestamp_ist": contract["timestamp_ist"],
        "writer_adoption_plan": writers,
        "adoption_principles": [
            "Patch one writer tier at a time from root to leaves.",
            "Each patch must be forward-only and schema-compatible.",
            "Each patch must ship with a lineage join test before the next tier is touched.",
            "Legacy records remain readable but cannot become truth links without deterministic parent IDs.",
        ],
    }
    summary = {
        "schema": "titan.echo.lineage_id_contract_summary.v1",
        "timestamp_ist": contract["timestamp_ist"],
        "required_id_count": len(STANDARD_IDS),
        "required_ids": list(STANDARD_IDS),
        "writer_count": len(WRITER_CATEGORIES),
        "writer_categories": list(WRITER_CATEGORIES),
        "high_risk_writers": high_risk,
        "lowest_risk_first_patch": "setup writer: add setup_id forward-only at setup creation and final_validated_setups persistence.",
        "recommended_patch_order": recommended_order,
        "expected_lineage_score_after_adoption": 92.0,
        "expected_lineage_score_basis": "Assumes all new records carry the full parent chain and old unsafe records are marked legacy_unlinked instead of force-linked.",
        "current_batch1_baseline": {
            "lineage_completeness_score": lineage_summary.get("lineage_completeness_score"),
            "traceability_score": lineage_summary.get("traceability_score"),
            "orphan_count": lineage_summary.get("orphan_count"),
            "duplicate_id_count": lineage_summary.get("duplicate_id_count"),
            "ambiguous_link_count": lineage_summary.get("ambiguous_link_count"),
        },
        "safety_rules": safety_rules(),
        "verdict": "CONTRACT_READY_FOR_REVIEW",
        "recommended_next_action": "Implement writer adoption in the recommended order, with no behavior changes beyond forward-only ID persistence.",
    }
    return contract, adoption_plan, summary


def main() -> None:
    contract, adoption_plan, summary = build_outputs()
    write_json(CONTRACT_PATH, contract)
    write_json(ADOPTION_PLAN_PATH, adoption_plan)
    write_json(SUMMARY_PATH, summary)
    print("Lineage ID contract generated.")
    print(f"required_ids={summary['required_ids']}")
    print(f"writer_count={summary['writer_count']}")
    print(f"high_risk_writers={summary['high_risk_writers']}")
    print(f"expected_lineage_score_after_adoption={summary['expected_lineage_score_after_adoption']}")


if __name__ == "__main__":
    main()
