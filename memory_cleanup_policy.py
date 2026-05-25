import json
from pathlib import Path

from memory_contribution_tracker import build_memory_contribution_status
from memory_freshness_audit import EXPECTED_MEMORY_ARTIFACTS, MEMORY_DIR, SAFETY_FLAGS, discover_memory_freshness
from memory_lineage import build_memory_lineage_graph
from utils.market_hours import as_ist_datetime


CLEANUP_POLICY_PATH = Path("data") / "runtime" / "memory_cleanup_policy.json"
BASELINE_EXPECTED_MEMORY = {
    "historical_adaptive_intelligence_state": "Historical adaptive intelligence baseline visibility.",
    "reinforcement_learning_memory": "Reinforcement learning baseline visibility.",
}
STALE_LEGACY_MEMORY = {
    "adaptive_intelligence_state",
    "cross_setup_memory",
    "lifecycle_memory",
    "master_shadow_memory",
    "strategy_family_memory",
}


def _write_baseline(path, name, now_ist):
    payload = {
        "status": "GENERATED_BASELINE",
        "memory_name": name,
        "generated_at_ist": now_ist.isoformat(),
        "last_updated_ist": now_ist.isoformat(),
        "source": "memory_cleanup_policy",
        "advisory_only": True,
        "generated_baseline": True,
        "no_fake_learning_history": True,
        "no_fake_performance_history": True,
        "records": [],
        "runtime_activity": False,
        "active_runtime_worker": False,
        "affects_live_ranking": False,
        "affects_execution": False,
        "broker_mutation": False,
        "telegram_mutation": False,
        "supabase_mutation": False,
        "live_order_behavior": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def ensure_missing_expected_memory_baselines(now=None):
    now_ist = as_ist_datetime(now)
    created = []
    for name in sorted(BASELINE_EXPECTED_MEMORY):
        path = MEMORY_DIR / f"{name}.json"
        if path.exists():
            continue
        _write_baseline(path, name, now_ist)
        created.append(name)
    return created


def _cleanup_class(item, lineage_node):
    classification = item.get("classification")
    name = item.get("name")
    if classification == "CORRUPTED":
        return "CORRUPTED"
    if classification == "MISSING":
        return "MISSING_EXPECTED"
    if item.get("source_type") == "runtime_status":
        return "GENERATED_RUNTIME"
    if name in BASELINE_EXPECTED_MEMORY and item.get("status") == "GENERATED_BASELINE":
        return "ACTIVE_ADVISORY"
    if name in STALE_LEGACY_MEMORY and classification == "STALE":
        return "LEGACY_VISIBLE"
    if classification == "STALE":
        return "ARCHIVE_CANDIDATE" if not lineage_node.get("runtime_dependency_present") else "STALE"
    if classification == "ORPHAN":
        return "ARCHIVE_CANDIDATE" if not lineage_node.get("contributors") else "ACTIVE_ADVISORY"
    if classification == "LEGACY_VISIBLE":
        return "LEGACY_VISIBLE"
    if lineage_node.get("runtime_dependency_present"):
        return "ACTIVE_RUNTIME"
    if classification == "ACTIVE":
        return "ACTIVE_ADVISORY"
    return classification or "ORPHAN"


def _recommended_action(cleanup_class, name):
    if cleanup_class == "CORRUPTED":
        return "manual_repair_required"
    if cleanup_class == "MISSING_EXPECTED":
        return "generate_advisory_baseline"
    if cleanup_class == "ARCHIVE_CANDIDATE":
        return "review_for_manual_archive"
    if cleanup_class == "LEGACY_VISIBLE" and name in STALE_LEGACY_MEMORY:
        return "keep_visible_mark_inactive_stale"
    if cleanup_class in {"ACTIVE_RUNTIME", "ACTIVE_ADVISORY", "GENERATED_RUNTIME"}:
        return "keep"
    return "monitor"


def build_memory_cleanup_policy(path=None, now=None):
    if path is None:
        path = CLEANUP_POLICY_PATH
    created_baselines = ensure_missing_expected_memory_baselines(now=now)
    freshness = discover_memory_freshness(now=now)
    lineage = build_memory_lineage_graph(now=now)
    contribution = build_memory_contribution_status(now=now)
    lineage_nodes = lineage.get("memory_nodes") or {}
    contributions = contribution.get("memory_contributions") or {}
    policy = {}
    counts = {}

    for item in freshness.get("artifacts") or []:
        if item.get("source_type") != "memory":
            continue
        name = item["name"]
        lineage_node = lineage_nodes.get(name) or {}
        cleanup_class = _cleanup_class(item, lineage_node)
        counts[cleanup_class] = counts.get(cleanup_class, 0) + 1
        policy[name] = {
            "path": item.get("path"),
            "source_classification": item.get("classification"),
            "cleanup_classification": cleanup_class,
            "recommended_action": _recommended_action(cleanup_class, name),
            "safe_to_archive": cleanup_class == "ARCHIVE_CANDIDATE",
            "runtime_dependency_present": bool(lineage_node.get("runtime_dependency_present")),
            "last_runtime_usage": item.get("timestamp_ist"),
            "contribution_visibility": (contributions.get(name) or {}).get("contribution_visibility", "NONE"),
            "contribution_score": (contributions.get(name) or {}).get("contribution_score", 0.0),
            "stale_but_visible": bool(name in STALE_LEGACY_MEMORY and item.get("classification") == "STALE"),
            "inactive_but_connected": bool(name in STALE_LEGACY_MEMORY and item.get("classification") == "STALE"),
            "advisory_only": True,
        }

    payload = {
        "generated_at_ist": freshness.get("generated_at_ist"),
        "overall_status": "WARNING" if counts.get("CORRUPTED") or counts.get("ARCHIVE_CANDIDATE") else "PASS",
        "created_baseline_memory": created_baselines,
        "classification_counts": counts,
        "archive_candidate_count": counts.get("ARCHIVE_CANDIDATE", 0),
        "stale_legacy_memory_count": sum(
            1 for item in policy.values() if item.get("stale_but_visible")
        ),
        "memory_policy": policy,
        "memory_lineage_summary": {
            "path": "data/runtime/memory_lineage_graph.json",
            "lineage_integrity_score": lineage.get("lineage_integrity_score"),
            "orphan_lineage_breaks": lineage.get("orphan_lineage_breaks") or [],
            "dead_memory_chains": lineage.get("dead_memory_chains") or [],
        },
        "memory_contribution_summary": {
            "path": "data/runtime/memory_contribution_status.json",
            "memory_files_contributing_nothing": contribution.get("memory_files_contributing_nothing") or [],
            "duplicate_memory_role_overlap": contribution.get("duplicate_memory_role_overlap") or {},
            "stale_advisory_only_chains": contribution.get("stale_advisory_only_chains") or [],
        },
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(build_memory_cleanup_policy(), indent=2, sort_keys=True))
