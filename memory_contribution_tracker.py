import json
from pathlib import Path

from memory_freshness_audit import SAFETY_FLAGS, discover_memory_freshness
from memory_lineage import build_memory_lineage_graph


CONTRIBUTION_PATH = Path("data") / "runtime" / "memory_contribution_status.json"


def _freshness_score(item):
    if item.get("classification") in {"CORRUPTED", "MISSING"}:
        return 0.0
    age = item.get("age_seconds")
    if age is None:
        return 25.0
    day = 24 * 60 * 60
    return round(max(0.0, min(100.0, 100.0 - (float(age) / day) * 10.0)), 2)


def _runtime_usage_score(lineage_node):
    if lineage_node.get("runtime_dependency_present"):
        return 80.0
    if lineage_node.get("legacy_engine"):
        return 45.0
    return 0.0


def build_memory_contribution_status(path=None, now=None):
    if path is None:
        path = CONTRIBUTION_PATH
    freshness = discover_memory_freshness(now=now)
    lineage = build_memory_lineage_graph(now=now)
    lineage_nodes = lineage.get("memory_nodes") or {}
    records = [item for item in freshness.get("artifacts") or [] if item.get("source_type") == "memory"]
    contributions = {}
    contributing_nothing = []
    stale_advisory_only_chains = []

    role_buckets = {}
    for item in records:
        name = item["name"]
        role = name.replace("_state", "").replace("_memory", "")
        role_buckets.setdefault(role, []).append(name)

    duplicate_memory_role_overlap = {
        role: sorted(names)
        for role, names in role_buckets.items()
        if len(names) > 1
    }

    for item in records:
        name = item["name"]
        lineage_node = lineage_nodes.get(name) or {}
        freshness_score = _freshness_score(item)
        runtime_usage_score = _runtime_usage_score(lineage_node)
        lineage_score = 100.0 if lineage_node.get("contributors") else 0.0
        if item.get("classification") == "CORRUPTED":
            contribution_score = 0.0
        else:
            contribution_score = round((freshness_score * 0.35) + (runtime_usage_score * 0.35) + (lineage_score * 0.30), 2)
        contribution_visibility = "NONE"
        if runtime_usage_score >= 80:
            contribution_visibility = "RUNTIME_VISIBLE"
        elif runtime_usage_score > 0:
            contribution_visibility = "ADVISORY_VISIBLE"

        contributions[name] = {
            "classification": item.get("classification"),
            "contribution_score": contribution_score,
            "runtime_usage_score": runtime_usage_score,
            "freshness_score": freshness_score,
            "lineage_integrity_score": lineage_score,
            "contribution_visibility": contribution_visibility,
            "runtime_dependency_present": lineage_node.get("runtime_dependency_present", False),
            "contributors": lineage_node.get("contributors") or [],
            "advisory_only": True,
        }
        if contribution_score <= 15.0:
            contributing_nothing.append(name)
        if item.get("classification") in {"STALE", "ORPHAN"} and contribution_visibility != "RUNTIME_VISIBLE":
            stale_advisory_only_chains.append(name)

    payload = {
        "generated_at_ist": freshness.get("generated_at_ist"),
        "lineage_integrity_score": lineage.get("lineage_integrity_score"),
        "memory_contributions": contributions,
        "memory_files_contributing_nothing": sorted(contributing_nothing),
        "duplicate_memory_role_overlap": duplicate_memory_role_overlap,
        "dead_memory_chains": lineage.get("dead_memory_chains") or [],
        "stale_advisory_only_chains": sorted(stale_advisory_only_chains),
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(build_memory_contribution_status(), indent=2, sort_keys=True))
