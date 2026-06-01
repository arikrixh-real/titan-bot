from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BASE = Path("data/runtime/echo")
PLAN_PATH = BASE / "runtime_repair_priority_plan.json"
SUMMARY_PATH = BASE / "runtime_repair_priority_summary.json"

REQUIRED_PLAN_KEYS = {
    "recommended_next_repair",
    "why_this_is_first",
    "what_not_to_touch",
    "expected_verification_after_repair",
    "ranked_repair_order",
    "separation",
    "forbidden_actions",
}
REQUIRED_SEPARATION_KEYS = {
    "already_repaired_but_waiting_for_runtime_regeneration",
    "real_current_failures",
    "stale_evidence_only",
    "external_config_issues",
    "low_value_repairs",
}
REQUIRED_ITEM_KEYS = {
    "rank",
    "subsystem",
    "evidence",
    "root_cause",
    "dependency_impact",
    "risk_level",
    "fix_complexity",
    "expected_improvement",
    "required_verification",
    "forbidden_actions",
    "recommended_codex_mission_prompt",
}
FORBIDDEN_PHRASES = {
    "Do not modify scanner.",
    "Do not modify workers.",
    "Do not modify Master Brain.",
    "Do not modify Unified Brain.",
    "Do not modify broker/risk.",
    "Do not restart TITAN.",
    "Do not deploy.",
    "Do not push.",
}


def load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fail(message: str) -> None:
    raise AssertionError(message)


def validate_item(item: dict[str, Any], label: str) -> None:
    missing = sorted(REQUIRED_ITEM_KEYS - set(item))
    if missing:
        fail(f"{label} missing required item keys: {', '.join(missing)}")
    forbidden = set(item.get("forbidden_actions") or [])
    missing_forbidden = sorted(FORBIDDEN_PHRASES - forbidden)
    if missing_forbidden:
        fail(f"{label} missing forbidden actions: {', '.join(missing_forbidden)}")
    if not item.get("evidence"):
        fail(f"{label} has no evidence")
    if not item.get("required_verification"):
        fail(f"{label} has no required verification")
    if not item.get("recommended_codex_mission_prompt"):
        fail(f"{label} has no recommended Codex mission prompt")


def validate_plan(plan: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_PLAN_KEYS - set(plan))
    if missing:
        fail(f"plan missing required keys: {', '.join(missing)}")

    forbidden = set(plan.get("forbidden_actions") or [])
    missing_forbidden = sorted(FORBIDDEN_PHRASES - forbidden)
    if missing_forbidden:
        fail(f"plan missing forbidden actions: {', '.join(missing_forbidden)}")

    separation = plan.get("separation")
    if not isinstance(separation, dict):
        fail("plan separation must be an object")
    missing_separation = sorted(REQUIRED_SEPARATION_KEYS - set(separation))
    if missing_separation:
        fail(f"plan separation missing categories: {', '.join(missing_separation)}")

    ranked = plan.get("ranked_repair_order")
    if not isinstance(ranked, list):
        fail("ranked_repair_order must be a list")
    for index, item in enumerate(ranked[:5], start=1):
        validate_item(item, f"ranked_repair_order[{index}]")

    recommended = plan.get("recommended_next_repair")
    if recommended is not None:
        validate_item(recommended, "recommended_next_repair")


def validate_summary(summary: dict[str, Any]) -> None:
    for key in (
        "recommended_next_repair",
        "top_5_repair_order",
        "safety_result",
        "next_codex_mission_prompt",
    ):
        if key not in summary:
            fail(f"summary missing {key}")

    safety = summary.get("safety_result") or {}
    if safety.get("status") != "PASS":
        fail("safety_result status must be PASS")
    if safety.get("read_only_planning_only") is not True:
        fail("read_only_planning_only must be true")
    if safety.get("forbidden_actions_preserved") is not True:
        fail("forbidden_actions_preserved must be true")

    top_5 = summary.get("top_5_repair_order")
    if not isinstance(top_5, list):
        fail("top_5_repair_order must be a list")
    for index, item in enumerate(top_5, start=1):
        validate_item(item, f"top_5_repair_order[{index}]")


def main() -> int:
    if not PLAN_PATH.exists():
        fail(f"missing generated plan: {PLAN_PATH}")
    if not SUMMARY_PATH.exists():
        fail(f"missing generated summary: {SUMMARY_PATH}")

    plan = load(PLAN_PATH)
    summary = load(SUMMARY_PATH)
    validate_plan(plan)
    validate_summary(summary)

    recommended = summary.get("recommended_next_repair") or {}
    print("recommended_next_repair:", recommended.get("title", "none"))
    print("top_5_repair_order:")
    for item in summary.get("top_5_repair_order", []):
        print(f"- {item['rank']}: {item['subsystem']} | {item['category']} | {item['title']}")
    print("safety_result:", summary["safety_result"]["status"])
    print("next_codex_mission_prompt:")
    print(summary["next_codex_mission_prompt"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
