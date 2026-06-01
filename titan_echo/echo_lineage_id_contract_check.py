"""Checker for the TITAN lineage ID contract outputs."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
CONTRACT_PATH = RUNTIME_ECHO_DIR / "lineage_id_contract.json"
ADOPTION_PLAN_PATH = RUNTIME_ECHO_DIR / "lineage_writer_adoption_plan.json"
SUMMARY_PATH = RUNTIME_ECHO_DIR / "lineage_id_contract_summary.json"

REQUIRED_IDS = {
    "setup_id",
    "decision_id",
    "trace_id",
    "trade_id",
    "outcome_id",
    "learning_event_id",
    "evolution_event_id",
}

REQUIRED_WRITERS = {
    "setup writer",
    "scanner/final_validated_setups writer",
    "Master Brain decision writer",
    "Unified Brain shadow trace writer",
    "paper/live trade journal writer",
    "outcome tracker writer",
    "learning writer",
    "evolution writer",
}

ALLOWED_CHANGED_FILES = {
    "titan_echo/echo_lineage_id_contract.py",
    "titan_echo/echo_lineage_id_contract_check.py",
    "data/runtime/echo/lineage_id_contract.json",
    "data/runtime/echo/lineage_writer_adoption_plan.json",
    "data/runtime/echo/lineage_id_contract_summary.json",
}

PROTECTED_PREFIXES = (
    "scanner/",
    "master_brain/",
    "unified_brain/",
    "consciousness_core/",
    "broker/",
    "risk/",
)

PROTECTED_FILES = {
    "journal/outcome_tracker.py",
    "journal/trade_execution_layer.py",
    "journal/trade_journal.py",
    "engines/paper_trading_engine.py",
}


def load_json(path: Path) -> Any:
    if not path.exists():
        raise AssertionError(f"missing output: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AssertionError(f"invalid JSON: {path}: {exc}") from exc


def git_changed_files() -> set[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return set()
    names = set()
    for output in (result.stdout, staged.stdout):
        for line in output.splitlines():
            normalized = line.strip().replace("\\", "/")
            if normalized:
                names.add(normalized)
    return names


def assert_no_runtime_behavior_changed() -> None:
    changed = git_changed_files()
    forbidden = []
    for name in changed:
        if name in ALLOWED_CHANGED_FILES:
            continue
        if name in PROTECTED_FILES or any(name.startswith(prefix) for prefix in PROTECTED_PREFIXES):
            forbidden.append(name)
    if forbidden:
        raise AssertionError(f"protected runtime behavior files changed: {sorted(forbidden)}")


def main() -> None:
    contract = load_json(CONTRACT_PATH)
    adoption = load_json(ADOPTION_PLAN_PATH)
    summary = load_json(SUMMARY_PATH)

    standard_ids = set((contract.get("standard_ids") or {}).keys())
    missing_ids = sorted(REQUIRED_IDS - standard_ids)
    if missing_ids:
        raise AssertionError(f"missing standard IDs: {missing_ids}")

    for id_name, spec in (contract.get("standard_ids") or {}).items():
        for field in (
            "purpose",
            "required_fields",
            "generation_rule",
            "parent_id",
            "child_ids",
            "owning_writer",
            "required_downstream_readers",
        ):
            if field not in spec:
                raise AssertionError(f"{id_name} missing contract field {field}")

    plan_items = adoption.get("writer_adoption_plan") or []
    writers = {item.get("writer_category") for item in plan_items if isinstance(item, dict)}
    missing_writers = sorted(REQUIRED_WRITERS - writers)
    if missing_writers:
        raise AssertionError(f"missing writer categories: {missing_writers}")

    for item in plan_items:
        for field in (
            "file_module",
            "current_id_fields_found",
            "missing_id_fields",
            "adoption_risk",
            "required_future_patch",
            "verification_test_needed",
        ):
            if field not in item:
                raise AssertionError(f"{item.get('writer_category')} missing adoption field {field}")

    if summary.get("required_id_count") != len(REQUIRED_IDS):
        raise AssertionError("summary required_id_count does not match required ID set")
    if summary.get("writer_count") != len(REQUIRED_WRITERS):
        raise AssertionError("summary writer_count does not match writer set")

    safety_rules = contract.get("safety_rules") or []
    required_rule_fragments = [
        "Do not create duplicate IDs.",
        "Do not overwrite old records.",
        "Add IDs forward-only.",
        "Preserve backward compatibility.",
        "legacy_unlinked",
    ]
    missing_rules = [
        fragment
        for fragment in required_rule_fragments
        if not any(fragment in str(rule) for rule in safety_rules)
    ]
    if missing_rules:
        raise AssertionError(f"missing safety rules: {missing_rules}")

    assert_no_runtime_behavior_changed()

    print("Lineage ID contract check passed.")
    print(f"required_ids={summary.get('required_ids')}")
    print(f"writer_adoption_count={len(plan_items)}")
    print(f"high_risk_writers={summary.get('high_risk_writers')}")
    print(f"recommended_patch_order={summary.get('recommended_patch_order')}")
    print(f"expected_lineage_score_after_adoption={summary.get('expected_lineage_score_after_adoption')}")


if __name__ == "__main__":
    main()
