import json
from pathlib import Path

from legacy_engine_visibility import LEGACY_ENGINES
from memory_freshness_audit import EXPECTED_MEMORY_ARTIFACTS, MEMORY_DIR, RUNTIME_DIR, SAFETY_FLAGS, discover_memory_freshness


LINEAGE_PATH = Path("data") / "runtime" / "memory_lineage_graph.json"


def _runtime_status_candidates(memory_name):
    base = memory_name
    for suffix in ("_state", "_memory"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    candidates = [
        RUNTIME_DIR / f"{base}_status.json",
        RUNTIME_DIR / f"{memory_name}_status.json",
    ]
    return [path for path in candidates if path.exists()]


def _legacy_engine_for_memory(memory_name):
    expected_path = (MEMORY_DIR / f"{memory_name}.json").as_posix()
    for engine, spec in LEGACY_ENGINES.items():
        memory_path = spec.get("memory")
        if memory_path and Path(memory_path).as_posix() == expected_path:
            return engine
    if memory_name in EXPECTED_MEMORY_ARTIFACTS:
        return memory_name.replace("_state", "").replace("_memory", "")
    return None


def build_memory_lineage_graph(path=None, now=None):
    if path is None:
        path = LINEAGE_PATH
    freshness = discover_memory_freshness(now=now)
    records = [item for item in freshness.get("artifacts") or [] if item.get("source_type") == "memory"]
    nodes = {}
    edges = []
    orphan_breaks = []
    unused_memory_chains = []
    advisory_contributors = []
    runtime_contributors = []

    for item in records:
        name = item["name"]
        status_paths = _runtime_status_candidates(name)
        legacy_engine = _legacy_engine_for_memory(name)
        contributors = []
        if legacy_engine:
            contributors.append(legacy_engine)
        if status_paths:
            contributors.extend(path.stem.replace("_status", "") for path in status_paths)

        node = {
            "memory": name,
            "path": item.get("path"),
            "classification": item.get("classification"),
            "present": item.get("present"),
            "runtime_dependency_present": bool(status_paths),
            "runtime_status_paths": [str(path).replace("\\", "/") for path in status_paths],
            "legacy_engine": legacy_engine,
            "contributors": sorted(set(contributors)),
            "advisory_only": True,
        }
        nodes[name] = node

        if legacy_engine:
            edges.append({"from": legacy_engine, "to": name, "type": "engine_memory", "advisory_only": True})
            advisory_contributors.append(legacy_engine)
        for status_path in status_paths:
            contributor = status_path.stem.replace("_status", "")
            edges.append({"from": contributor, "to": name, "type": "runtime_status_memory_visibility", "advisory_only": True})
            runtime_contributors.append(contributor)
        if not contributors and item.get("classification") not in {"MISSING", "CORRUPTED"}:
            orphan_breaks.append(name)
        if item.get("classification") in {"STALE", "ORPHAN"} and not status_paths:
            unused_memory_chains.append(name)

    total = len(records) or 1
    connected = sum(1 for item in nodes.values() if item.get("contributors"))
    lineage_integrity_score = round((connected / total) * 100, 2)
    payload = {
        "generated_at_ist": freshness.get("generated_at_ist"),
        "lineage_integrity_score": lineage_integrity_score,
        "memory_nodes": nodes,
        "edges": edges,
        "runtime_contributors": sorted(set(runtime_contributors)),
        "advisory_contributors": sorted(set(advisory_contributors)),
        "orphan_lineage_breaks": sorted(orphan_breaks),
        "unused_memory_chains": sorted(unused_memory_chains),
        "dead_memory_chains": sorted(set(orphan_breaks) & set(unused_memory_chains)),
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(build_memory_lineage_graph(), indent=2, sort_keys=True))
