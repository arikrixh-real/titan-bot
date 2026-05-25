from runtime_topology import build_runtime_topology


def build_runtime_observability(now=None):
    topology = build_runtime_topology(now=now)
    graph = topology.get("dependency_graph") or {}
    return {
        "generated_at_ist": topology.get("generated_at_ist"),
        "topology_health": topology.get("topology_health"),
        "runtime_integrity_score": topology.get("runtime_integrity_score"),
        "dependency_integrity_score": topology.get("dependency_integrity_score"),
        "observability_score": topology.get("observability_score"),
        "runtime_consistency_score": topology.get("runtime_consistency_score"),
        "runtime_conflicts": topology.get("runtime_conflicts") or [],
        "stale_runtime_sources": topology.get("stale_runtime_sources") or [],
        "disconnected_engines": graph.get("disconnected_engines") or [],
        "safety_flags": topology.get("safety_flags") or {},
    }
