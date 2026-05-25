from runtime_topology import build_runtime_topology


def build_runtime_observability(now=None):
    topology = build_runtime_topology(now=now)
    graph = topology.get("dependency_graph") or {}
    memory_health = topology.get("memory_health") or {}
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
        "visibility_only_connected_engines": (topology.get("engine_visibility") or {}).get("visibility_only_connected_engines") or [],
        "memory_health": memory_health,
        "legacy_engine_visibility": memory_health.get("legacy_engine_visibility") or {},
        "memory_freshness_score": memory_health.get("memory_freshness_score"),
        "memory_integrity_score": memory_health.get("memory_integrity_score"),
        "stale_memory_count": memory_health.get("stale_memory_files"),
        "orphan_memory_count": memory_health.get("orphan_memory_files"),
        "corrupted_memory_count": memory_health.get("corrupted_memory_files"),
        "missing_visibility_count": len(memory_health.get("missing_visibility_summary") or []),
        "safety_flags": topology.get("safety_flags") or {},
    }
