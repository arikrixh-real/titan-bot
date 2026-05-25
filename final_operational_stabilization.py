import json
from datetime import datetime, timezone
from pathlib import Path

from advisory_mutation_containment import run_batch10_mutation_containment
from dashboard_truth_foundation import run_batch11_dashboard_truth_foundation
from integrity_monitor import build_titan_integrity_monitor
from memory_health import run_memory_health_check
from ranking_integrity import build_ranking_integrity_status
from runtime_artifact_registry import run_batch7_artifact_isolation
from runtime_dependency_graph import SAFETY_FLAGS, build_runtime_dependency_graph
from runtime_topology import build_runtime_topology
from runtime_watchdog import run_batch8_runtime_watchdog
from utils.market_hours import IST, as_ist_datetime


RUNTIME_DIR = Path("data") / "runtime"

TITAN_FINAL_OPERATIONAL_AUDIT_PATH = RUNTIME_DIR / "titan_final_operational_audit.json"
TITAN_STABILITY_SCORE_PATH = RUNTIME_DIR / "titan_stability_score.json"
TITAN_DEPENDENCY_CERTIFICATION_PATH = RUNTIME_DIR / "titan_dependency_certification.json"
TITAN_RUNTIME_CERTIFICATION_PATH = RUNTIME_DIR / "titan_runtime_certification.json"
CLOCK_SKEW_TOLERANCE_SECONDS = 60


def _path_key(path):
    return str(Path(path)).replace("\\", "/")


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _status_from_issues(failures, warnings):
    if failures:
        return "FAIL"
    if warnings:
        return "WARNING"
    return "PASS"


def _score_status(score, warning_threshold=80.0, fail_threshold=50.0):
    score = _safe_float(score)
    if score < fail_threshold:
        return "FAIL"
    if score < warning_threshold:
        return "WARNING"
    return "PASS"


def _average_scores(scores):
    values = [_safe_float(score) for score in scores if score is not None]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _parse_timestamp(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).astimezone(IST)
    if isinstance(value, str):
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            return as_ist_datetime(parsed)
        except ValueError:
            try:
                return datetime.fromtimestamp(float(value), tz=timezone.utc).astimezone(IST)
            except (OverflowError, ValueError):
                return None
    return None


def _payload_timestamp(payload):
    if not isinstance(payload, dict):
        return None
    for key in (
        "generated_at_ist",
        "timestamp_ist",
        "last_seen_ist",
        "last_completed_at_ist",
        "updated_at",
        "timestamp",
    ):
        parsed = _parse_timestamp(payload.get(key))
        if parsed:
            return parsed
    return None


def _file_timestamp(path):
    try:
        return datetime.fromtimestamp(Path(path).stat().st_mtime, tz=timezone.utc).astimezone(IST)
    except (FileNotFoundError, OSError, OverflowError):
        return None


def _artifact_clock_skew_report(now_ist, runtime_dir=None):
    runtime_dir = Path(runtime_dir or RUNTIME_DIR)
    timestamps = []
    future_count = 0
    if runtime_dir.exists():
        for artifact_path in runtime_dir.glob("*.json"):
            payload = {}
            try:
                payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            artifact_timestamps = [
                timestamp
                for timestamp in (_payload_timestamp(payload), _file_timestamp(artifact_path))
                if timestamp
            ]
            if not artifact_timestamps:
                continue
            timestamp = max(artifact_timestamps)
            timestamps.append(timestamp)
            if (timestamp - now_ist).total_seconds() > CLOCK_SKEW_TOLERANCE_SECONDS:
                future_count += 1

    max_timestamp = max(timestamps) if timestamps else None
    skew_detected = future_count > 0
    return {
        "runtime_clock_ist": now_ist.isoformat(),
        "max_artifact_timestamp_ist": max_timestamp.isoformat() if max_timestamp else None,
        "clock_skew_detected": skew_detected,
        "future_artifact_count": future_count,
        "clock_skew_warning": "CLOCK_SKEW_WARNING" if skew_detected else None,
        "freshness_certification_reliable": not skew_detected,
    }


def build_titan_dependency_certification(graph=None, topology=None, path=None, now=None):
    path = path or TITAN_DEPENDENCY_CERTIFICATION_PATH
    now_ist = as_ist_datetime(now)
    graph = graph if isinstance(graph, dict) else build_runtime_dependency_graph(now=now_ist)
    topology = topology if isinstance(topology, dict) else build_runtime_topology(now=now_ist)
    disconnected = graph.get("disconnected_engines") or []
    stale = graph.get("stale_engines") or []
    dependency_score = _safe_float(graph.get("dependency_integrity_score"))
    topology_health = topology.get("topology_health")
    failures = []
    warnings = []
    if graph.get("dependency_status") == "FAIL":
        failures.append("dependency_graph_fail")
    if disconnected:
        warnings.append("disconnected_engine_visible")
    if stale:
        warnings.append("stale_engine_visible")
    if _score_status(dependency_score) != "PASS":
        warnings.append("dependency_integrity_score_below_pass_threshold")
    if topology_health != "PASS":
        warnings.append("topology_health_not_pass")

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "titan_dependency_certification_status": _status_from_issues(failures, warnings),
        "dependency_integrity_score": round(dependency_score, 2),
        "topology_health": topology_health,
        "dependency_status": graph.get("dependency_status"),
        "connected_engine_count": len(graph.get("connected_engines") or []),
        "disconnected_engine_count": len(disconnected),
        "stale_engine_count": len(stale),
        "disconnected_engines": disconnected,
        "stale_engines": stale,
        "dependency_chain_stable": not failures and not disconnected,
        "warnings": warnings,
        "failures": failures,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_titan_runtime_certification(topology=None, watchdog=None, artifact_isolation=None, path=None, now=None):
    path = path or TITAN_RUNTIME_CERTIFICATION_PATH
    now_ist = as_ist_datetime(now)
    topology = topology if isinstance(topology, dict) else build_runtime_topology(now=now_ist)
    watchdog = watchdog if isinstance(watchdog, dict) else run_batch8_runtime_watchdog(now=now_ist)
    artifact_isolation = artifact_isolation if isinstance(artifact_isolation, dict) else run_batch7_artifact_isolation(now=now_ist)
    runtime_score = _safe_float(topology.get("runtime_integrity_score"))
    consistency_score = _safe_float(topology.get("runtime_consistency_score"))
    stale_sources = topology.get("stale_runtime_sources") or []
    conflicts = topology.get("runtime_conflicts") or []
    critical_status = (artifact_isolation.get("summary") or {}).get("runtime_critical_chain_status")
    failures = []
    warnings = []
    if watchdog.get("status") == "FAIL":
        failures.append("runtime_watchdog_fail")
    if runtime_score < 50:
        warnings.append("runtime_integrity_score_low")
    if stale_sources:
        warnings.append("stale_runtime_sources_visible")
    if conflicts:
        warnings.append("runtime_conflicts_visible")
    if critical_status != "PASS":
        warnings.append("runtime_critical_chain_not_pass")
    if watchdog.get("summary", {}).get("automatic_restart_allowed"):
        failures.append("automatic_restart_allowed")
    if watchdog.get("summary", {}).get("automatic_process_kill_allowed"):
        failures.append("automatic_process_kill_allowed")

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "titan_runtime_certification_status": _status_from_issues(failures, warnings),
        "runtime_integrity_score": round(runtime_score, 2),
        "runtime_consistency_score": round(consistency_score, 2),
        "runtime_owner": (watchdog.get("summary") or {}).get("runtime_owner"),
        "authoritative_pid": (watchdog.get("summary") or {}).get("authoritative_pid"),
        "owner_confidence": (watchdog.get("summary") or {}).get("owner_confidence"),
        "topology_health": topology.get("topology_health"),
        "runtime_critical_chain_status": critical_status,
        "stale_runtime_sources": stale_sources,
        "runtime_conflicts": conflicts,
        "runtime_stable": not failures and not stale_sources and not conflicts,
        "automatic_restart_allowed": bool((watchdog.get("summary") or {}).get("automatic_restart_allowed")),
        "automatic_process_kill_allowed": bool((watchdog.get("summary") or {}).get("automatic_process_kill_allowed")),
        "auto_healing_mutation_allowed": bool((watchdog.get("summary") or {}).get("auto_healing_mutation_allowed")),
        "warnings": warnings,
        "failures": failures,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_titan_stability_score(topology=None, dependency=None, runtime=None, ranking=None, memory=None, mutation=None, dashboard=None, path=None, now=None):
    path = path or TITAN_STABILITY_SCORE_PATH
    now_ist = as_ist_datetime(now)
    topology = topology if isinstance(topology, dict) else build_runtime_topology(now=now_ist)
    dependency = dependency if isinstance(dependency, dict) else build_titan_dependency_certification(topology=topology, now=now_ist)
    runtime = runtime if isinstance(runtime, dict) else build_titan_runtime_certification(topology=topology, now=now_ist)
    ranking = ranking if isinstance(ranking, dict) else build_ranking_integrity_status(now=now_ist)
    memory = memory if isinstance(memory, dict) else run_memory_health_check(now=now_ist)
    mutation = mutation if isinstance(mutation, dict) else run_batch10_mutation_containment(now=now_ist)
    dashboard = dashboard if isinstance(dashboard, dict) else run_batch11_dashboard_truth_foundation(now=now_ist)

    runtime_integrity_score = _safe_float(runtime.get("runtime_integrity_score"))
    topology_score = 100.0 if topology.get("topology_health") == "PASS" else 75.0 if topology.get("topology_health") == "WARNING" else 25.0
    dependency_integrity_score = _safe_float(dependency.get("dependency_integrity_score"))
    ranking_integrity_score = _safe_float(ranking.get("ranking_integrity_score"))
    memory_integrity_score = _safe_float(memory.get("memory_integrity_score"))
    mutation_score = 100.0 if mutation.get("status") == "PASS" else 70.0 if mutation.get("status") == "WARNING" else 0.0
    dashboard_score = 100.0 if dashboard.get("status") == "PASS" else 70.0 if dashboard.get("status") == "WARNING" else 0.0
    stability_score = _average_scores(
        [
            runtime_integrity_score,
            topology_score,
            dependency_integrity_score,
            ranking_integrity_score,
            memory_integrity_score,
            mutation_score,
            dashboard_score,
        ]
    )
    warnings = []
    failures = []
    if _score_status(stability_score) == "FAIL":
        failures.append("stability_score_fail_threshold")
    elif _score_status(stability_score) == "WARNING":
        warnings.append("stability_score_warning_threshold")
    if runtime.get("titan_runtime_certification_status") != "PASS":
        warnings.append("runtime_certification_not_pass")
    if dependency.get("titan_dependency_certification_status") != "PASS":
        warnings.append("dependency_certification_not_pass")
    if ranking.get("authoritative_owner") != "final_decision_engine":
        failures.append("ranking_owner_changed")
    clock_skew = _artifact_clock_skew_report(now_ist)
    if clock_skew["clock_skew_detected"]:
        warnings.append("CLOCK_SKEW_WARNING")

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "titan_stability_score_status": _status_from_issues(failures, warnings),
        **clock_skew,
        "runtime_integrity_score": round(runtime_integrity_score, 2),
        "topology_health": topology.get("topology_health"),
        "topology_score": round(topology_score, 2),
        "stability_score": stability_score,
        "dependency_integrity_score": round(dependency_integrity_score, 2),
        "ranking_integrity_score": round(ranking_integrity_score, 2),
        "memory_integrity_score": round(memory_integrity_score, 2),
        "mutation_containment_score": round(mutation_score, 2),
        "dashboard_truth_score": round(dashboard_score, 2),
        "score_weights": "equal_weight_visibility_certification",
        "warnings": warnings,
        "failures": failures,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_titan_final_operational_audit(path=None, now=None):
    path = path or TITAN_FINAL_OPERATIONAL_AUDIT_PATH
    now_ist = as_ist_datetime(now)
    topology = build_runtime_topology(now=now_ist)
    graph = build_runtime_dependency_graph(now=now_ist)
    memory = run_memory_health_check(now=now_ist)
    ranking = build_ranking_integrity_status(now=now_ist)
    integrity = build_titan_integrity_monitor(now=now_ist)
    artifact_isolation = run_batch7_artifact_isolation(now=now_ist)
    watchdog = run_batch8_runtime_watchdog(now=now_ist)
    mutation = run_batch10_mutation_containment(now=now_ist)
    dashboard = run_batch11_dashboard_truth_foundation(now=now_ist)
    dependency_cert = build_titan_dependency_certification(graph=graph, topology=topology, now=now_ist)
    runtime_cert = build_titan_runtime_certification(
        topology=topology,
        watchdog=watchdog,
        artifact_isolation=artifact_isolation,
        now=now_ist,
    )
    stability = build_titan_stability_score(
        topology=topology,
        dependency=dependency_cert,
        runtime=runtime_cert,
        ranking=ranking,
        memory=memory,
        mutation=mutation,
        dashboard=dashboard,
        now=now_ist,
    )

    failures = []
    warnings = []
    component_statuses = {
        "runtime": runtime_cert.get("titan_runtime_certification_status"),
        "dependency": dependency_cert.get("titan_dependency_certification_status"),
        "memory": memory.get("overall_status"),
        "ranking": "PASS" if ranking.get("ranking_chain_valid") and ranking.get("authoritative_owner") == "final_decision_engine" else "FAIL",
        "mutation": mutation.get("status"),
        "topology": topology.get("topology_health"),
        "runtime_critical_chain": (artifact_isolation.get("summary") or {}).get("runtime_critical_chain_status"),
        "integrity_monitor": integrity.get("integrity_monitor_status"),
        "dashboard_truth": dashboard.get("status"),
        "stability_score": stability.get("titan_stability_score_status"),
    }
    for name, status in component_statuses.items():
        if status == "FAIL":
            failures.append(f"{name}_fail")
        elif status == "WARNING":
            warnings.append(f"{name}_warning")
    if ranking.get("authoritative_owner") != "final_decision_engine":
        failures.append("ranking_owner_changed")
    if ranking.get("dangerous_live_overrides"):
        failures.append("dangerous_ranking_override_detected")
    if mutation.get("summary", {}).get("unsafe_live_mutation_vector_count"):
        warnings.append("unsafe_advisory_mutation_vector_visible")
    if stability.get("clock_skew_warning"):
        warnings.append(stability["clock_skew_warning"])

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "titan_final_operational_audit_status": _status_from_issues(failures, warnings),
        "audit_mode": "advisory_visibility_only",
        "component_statuses": component_statuses,
        "runtime_integrity_score": stability.get("runtime_integrity_score"),
        "topology_health": stability.get("topology_health"),
        "stability_score": stability.get("stability_score"),
        "dependency_integrity_score": stability.get("dependency_integrity_score"),
        "ranking_integrity_score": stability.get("ranking_integrity_score"),
        "memory_integrity_score": stability.get("memory_integrity_score"),
        "runtime_clock_ist": stability.get("runtime_clock_ist"),
        "max_artifact_timestamp_ist": stability.get("max_artifact_timestamp_ist"),
        "clock_skew_detected": stability.get("clock_skew_detected"),
        "future_artifact_count": stability.get("future_artifact_count"),
        "clock_skew_warning": stability.get("clock_skew_warning"),
        "freshness_certification_reliable": stability.get("freshness_certification_reliable"),
        "final_runtime_audit": {
            "runtime_owner": runtime_cert.get("runtime_owner"),
            "authoritative_pid": runtime_cert.get("authoritative_pid"),
            "owner_confidence": runtime_cert.get("owner_confidence"),
            "stale_runtime_sources": runtime_cert.get("stale_runtime_sources"),
            "runtime_conflicts": runtime_cert.get("runtime_conflicts"),
        },
        "final_dependency_audit": {
            "connected_engine_count": dependency_cert.get("connected_engine_count"),
            "disconnected_engine_count": dependency_cert.get("disconnected_engine_count"),
            "stale_engine_count": dependency_cert.get("stale_engine_count"),
        },
        "final_memory_audit": {
            "overall_status": memory.get("overall_status"),
            "stale_memory_files": memory.get("stale_memory_files"),
            "orphan_memory_files": memory.get("orphan_memory_files"),
            "corrupted_memory_files": memory.get("corrupted_memory_files"),
            "lineage_integrity_score": memory.get("lineage_integrity_score"),
        },
        "final_ranking_audit": {
            "authoritative_owner": ranking.get("authoritative_owner"),
            "ranking_chain_valid": ranking.get("ranking_chain_valid"),
            "dangerous_live_overrides": ranking.get("dangerous_live_overrides") or [],
        },
        "final_mutation_audit": {
            "status": mutation.get("status"),
            "unsafe_live_mutation_vector_count": (mutation.get("summary") or {}).get("unsafe_live_mutation_vector_count"),
            "leaking_system_count": (mutation.get("summary") or {}).get("leaking_system_count"),
        },
        "final_topology_audit": {
            "topology_health": topology.get("topology_health"),
            "observability_score": topology.get("observability_score"),
            "runtime_consistency_score": topology.get("runtime_consistency_score"),
        },
        "final_runtime_critical_chain_audit": {
            "status": (artifact_isolation.get("summary") or {}).get("runtime_critical_chain_status"),
            "dead_chains": (artifact_isolation.get("summary") or {}).get("dead_chains"),
            "isolated_advisory_dead_chains": (artifact_isolation.get("summary") or {}).get("isolated_advisory_dead_chains"),
        },
        "certification_artifacts": {
            "titan_stability_score": _path_key(TITAN_STABILITY_SCORE_PATH),
            "titan_dependency_certification": _path_key(TITAN_DEPENDENCY_CERTIFICATION_PATH),
            "titan_runtime_certification": _path_key(TITAN_RUNTIME_CERTIFICATION_PATH),
        },
        "warnings": warnings,
        "failures": failures,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def run_batch12_final_operational_stabilization(now=None):
    audit = build_titan_final_operational_audit(now=now)
    return {
        "generated_at_ist": audit.get("generated_at_ist"),
        "batch": "BATCH_12_FINAL_OPERATIONAL_STABILIZATION",
        "status": audit.get("titan_final_operational_audit_status"),
        "artifacts": {
            "titan_final_operational_audit": _path_key(TITAN_FINAL_OPERATIONAL_AUDIT_PATH),
            "titan_stability_score": _path_key(TITAN_STABILITY_SCORE_PATH),
            "titan_dependency_certification": _path_key(TITAN_DEPENDENCY_CERTIFICATION_PATH),
            "titan_runtime_certification": _path_key(TITAN_RUNTIME_CERTIFICATION_PATH),
        },
        "summary": {
            "runtime_integrity_score": audit.get("runtime_integrity_score"),
            "topology_health": audit.get("topology_health"),
            "stability_score": audit.get("stability_score"),
            "dependency_integrity_score": audit.get("dependency_integrity_score"),
            "ranking_integrity_score": audit.get("ranking_integrity_score"),
            "memory_integrity_score": audit.get("memory_integrity_score"),
            "runtime_clock_ist": audit.get("runtime_clock_ist"),
            "max_artifact_timestamp_ist": audit.get("max_artifact_timestamp_ist"),
            "clock_skew_detected": audit.get("clock_skew_detected"),
            "future_artifact_count": audit.get("future_artifact_count"),
            "clock_skew_warning": audit.get("clock_skew_warning"),
            "freshness_certification_reliable": audit.get("freshness_certification_reliable"),
            "component_statuses": audit.get("component_statuses"),
        },
        "warnings": audit.get("warnings") or [],
        "failures": audit.get("failures") or [],
        "safety_flags": dict(SAFETY_FLAGS),
    }


if __name__ == "__main__":
    print(json.dumps(run_batch12_final_operational_stabilization(), indent=2, sort_keys=True))
