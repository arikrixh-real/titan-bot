import json
from pathlib import Path

from memory_health import run_memory_health_check
from ranking_integrity import build_ranking_integrity_status
from runtime_artifact_registry import build_runtime_artifact_registry
from runtime_dependency_graph import SAFETY_FLAGS, build_runtime_dependency_graph
from runtime_engine_health import build_master_brain_runtime_health, build_setup_engine_runtime_health
from runtime_fallback_resolver import run_runtime_fallback_resolution
from runtime_watchdog import build_titan_runtime_watchdog
from utils.market_hours import as_ist_datetime


RUNTIME_DIR = Path("data") / "runtime"

TITAN_INTEGRITY_MONITOR_PATH = RUNTIME_DIR / "titan_integrity_monitor.json"
RUNTIME_REGRESSION_AUDIT_PATH = RUNTIME_DIR / "runtime_regression_audit.json"
DEPENDENCY_REGRESSION_STATUS_PATH = RUNTIME_DIR / "dependency_regression_status.json"
RANKING_REGRESSION_STATUS_PATH = RUNTIME_DIR / "ranking_regression_status.json"
MEMORY_REGRESSION_STATUS_PATH = RUNTIME_DIR / "memory_regression_status.json"

RUNTIME_STALE_WARNING_LIMIT = 3
DEPENDENCY_SCORE_WARNING = 80.0
RANKING_SCORE_WARNING = 95.0
MEMORY_SCORE_WARNING = 80.0
LINEAGE_SCORE_WARNING = 80.0


def _path_key(path):
    return str(Path(path)).replace("\\", "/")


def _status_from_warnings(failures=None, warnings=None):
    failures = failures or []
    warnings = warnings or []
    if failures:
        return "FAIL"
    if warnings:
        return "WARNING"
    return "PASS"


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_runtime_regression_audit(watchdog=None, registry=None, path=None, now=None):
    path = path or RUNTIME_REGRESSION_AUDIT_PATH
    now_ist = as_ist_datetime(now)
    watchdog = watchdog if isinstance(watchdog, dict) else build_titan_runtime_watchdog(now=now_ist)
    registry = registry if isinstance(registry, dict) else build_runtime_artifact_registry(now=now_ist)
    artifacts = registry.get("artifacts") or []
    runtime_artifacts = [
        item
        for item in artifacts
        if item.get("scope") in {"runtime_critical_chain", "runtime_visibility"}
    ]
    stale_runtime_artifacts = [
        item
        for item in runtime_artifacts
        if item.get("stale")
    ]
    stale_critical_artifacts = [
        item
        for item in stale_runtime_artifacts
        if item.get("runtime_critical")
    ]
    contradictions = watchdog.get("remaining_contradictions") or watchdog.get("heartbeat_daemon_inconsistencies") or []
    failures = []
    warnings = []
    if watchdog.get("runtime_owner") == "none_confirmed":
        warnings.append("runtime_owner_none_confirmed")
    if contradictions:
        warnings.append("runtime_heartbeat_daemon_contradictions_visible")
    if len(stale_runtime_artifacts) > RUNTIME_STALE_WARNING_LIMIT:
        warnings.append("stale_runtime_artifact_regression")
    if stale_critical_artifacts:
        warnings.append("stale_runtime_critical_artifact_regression")

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "runtime_regression_status": _status_from_warnings(failures, warnings),
        "runtime_owner": watchdog.get("runtime_owner"),
        "authoritative_pid": watchdog.get("authoritative_pid"),
        "owner_confidence": watchdog.get("owner_confidence"),
        "runtime_ownership_deterministic": watchdog.get("runtime_ownership_deterministic"),
        "heartbeat_daemon_inconsistencies": contradictions,
        "stale_writer_count": watchdog.get("stale_writer_count"),
        "runtime_artifact_count": len(runtime_artifacts),
        "stale_runtime_artifact_count": len(stale_runtime_artifacts),
        "stale_runtime_critical_artifact_count": len(stale_critical_artifacts),
        "stale_runtime_artifacts": [
            {
                "path": item.get("path"),
                "role": item.get("role"),
                "status": item.get("status"),
                "age_seconds": item.get("age_seconds"),
                "fresh_seconds": item.get("fresh_seconds"),
            }
            for item in stale_runtime_artifacts[:100]
        ],
        "runtime_drift_detection": {
            "owner_drift_detected": watchdog.get("runtime_owner") == "none_confirmed",
            "stale_writer_regression_detected": bool(watchdog.get("stale_writer_count")),
            "heartbeat_daemon_drift_detected": bool(contradictions),
        },
        "warnings": warnings,
        "failures": failures,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_dependency_regression_status(graph=None, path=None, now=None):
    path = path or DEPENDENCY_REGRESSION_STATUS_PATH
    now_ist = as_ist_datetime(now)
    graph = graph if isinstance(graph, dict) else build_runtime_dependency_graph(now=now_ist)
    disconnected = graph.get("disconnected_engines") or []
    stale = graph.get("stale_engines") or []
    dependency_score = _safe_float(graph.get("dependency_integrity_score"))
    failures = []
    warnings = []
    if graph.get("dependency_status") == "FAIL":
        failures.append("dependency_graph_fail")
    if disconnected:
        warnings.append("disconnected_engine_regression")
    if stale:
        warnings.append("stale_engine_regression")
    if dependency_score < DEPENDENCY_SCORE_WARNING:
        warnings.append("dependency_integrity_score_below_threshold")

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "dependency_regression_status": _status_from_warnings(failures, warnings),
        "dependency_status": graph.get("dependency_status"),
        "dependency_integrity_score": dependency_score,
        "connected_engine_count": len(graph.get("connected_engines") or []),
        "disconnected_engine_count": len(disconnected),
        "stale_engine_count": len(stale),
        "disconnected_engines": disconnected,
        "stale_engines": stale,
        "dependency_graph_integrity": {
            "disconnected_engine_regression_detected": bool(disconnected),
            "stale_engine_regression_detected": bool(stale),
            "dependency_score_threshold": DEPENDENCY_SCORE_WARNING,
        },
        "warnings": warnings,
        "failures": failures,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_ranking_regression_status(ranking=None, path=None, now=None):
    path = path or RANKING_REGRESSION_STATUS_PATH
    now_ist = as_ist_datetime(now)
    ranking = ranking if isinstance(ranking, dict) else build_ranking_integrity_status(now=now_ist)
    score = _safe_float(ranking.get("ranking_integrity_score"))
    dangerous = ranking.get("dangerous_live_overrides") or []
    conflicting = ranking.get("conflicting_mutators") or []
    duplicate = ranking.get("duplicate_rank_writers") or {}
    failures = []
    warnings = []
    if ranking.get("authoritative_owner") != "final_decision_engine":
        failures.append("authoritative_ranking_owner_changed")
    if dangerous:
        failures.append("dangerous_live_ranking_override_detected")
    if not ranking.get("ranking_chain_valid"):
        failures.append("ranking_chain_invalid")
    if conflicting:
        warnings.append("conflicting_rank_mutator_regression")
    if score < RANKING_SCORE_WARNING:
        warnings.append("ranking_integrity_score_below_threshold")

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "ranking_regression_status": _status_from_warnings(failures, warnings),
        "ranking_integrity_score": score,
        "authoritative_owner": ranking.get("authoritative_owner"),
        "ranking_chain_valid": ranking.get("ranking_chain_valid"),
        "conflicting_mutators": conflicting,
        "dangerous_live_overrides": dangerous,
        "duplicate_rank_writer_fields": sorted(duplicate.keys()),
        "ranking_integrity_regression_detection": {
            "authoritative_owner_expected": "final_decision_engine",
            "authoritative_owner_valid": ranking.get("authoritative_owner") == "final_decision_engine",
            "dangerous_override_detected": bool(dangerous),
            "ranking_chain_invalid": not bool(ranking.get("ranking_chain_valid")),
        },
        "warnings": warnings,
        "failures": failures,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_memory_regression_status(memory=None, path=None, now=None):
    path = path or MEMORY_REGRESSION_STATUS_PATH
    now_ist = as_ist_datetime(now)
    memory = memory if isinstance(memory, dict) else run_memory_health_check(now=now_ist)
    memory_score = _safe_float(memory.get("memory_integrity_score"))
    freshness_score = _safe_float(memory.get("memory_freshness_score"))
    lineage_score = _safe_float(memory.get("lineage_integrity_score"))
    stale = memory.get("stale_memory_files") or 0
    orphan = memory.get("orphan_memory_files") or 0
    corrupted = memory.get("corrupted_memory_files") or 0
    missing = memory.get("missing_expected_memory_files") or 0
    failures = []
    warnings = []
    if corrupted:
        failures.append("corrupted_memory_regression")
    if missing:
        failures.append("missing_expected_memory_regression")
    if memory_score < MEMORY_SCORE_WARNING:
        warnings.append("memory_integrity_score_below_threshold")
    if lineage_score < LINEAGE_SCORE_WARNING:
        warnings.append("memory_lineage_score_below_threshold")
    if stale:
        warnings.append("stale_memory_regression")
    if orphan:
        warnings.append("orphan_memory_regression")

    lineage = memory.get("memory_lineage_summary") or {}
    contribution = memory.get("memory_contribution_summary") or {}
    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "memory_regression_status": _status_from_warnings(failures, warnings),
        "memory_integrity_score": memory_score,
        "memory_freshness_score": freshness_score,
        "lineage_integrity_score": lineage_score,
        "stale_memory_files": stale,
        "orphan_memory_files": orphan,
        "corrupted_memory_files": corrupted,
        "missing_expected_memory_files": missing,
        "dead_memory_chains": lineage.get("dead_memory_chains") or [],
        "orphan_lineage_breaks": lineage.get("orphan_lineage_breaks") or [],
        "memory_files_contributing_nothing": contribution.get("memory_files_contributing_nothing") or [],
        "memory_lineage_integrity_detection": {
            "lineage_score_threshold": LINEAGE_SCORE_WARNING,
            "lineage_regression_detected": lineage_score < LINEAGE_SCORE_WARNING,
            "dead_chain_regression_detected": bool(lineage.get("dead_memory_chains")),
            "orphan_lineage_regression_detected": bool(lineage.get("orphan_lineage_breaks")),
        },
        "warnings": warnings,
        "failures": failures,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_titan_integrity_monitor(now=None):
    now_ist = as_ist_datetime(now)
    graph = build_runtime_dependency_graph(now=now_ist)
    watchdog = build_titan_runtime_watchdog(now=now_ist)
    registry = build_runtime_artifact_registry(now=now_ist)
    ranking = build_ranking_integrity_status(now=now_ist)
    memory = run_memory_health_check(now=now_ist)
    master_runtime_health = build_master_brain_runtime_health(now=now_ist)
    setup_runtime_health = build_setup_engine_runtime_health(now=now_ist)
    fallback_resolution = run_runtime_fallback_resolution(now=now_ist)

    runtime_regression = build_runtime_regression_audit(watchdog=watchdog, registry=registry, now=now_ist)
    dependency_regression = build_dependency_regression_status(graph=graph, now=now_ist)
    ranking_regression = build_ranking_regression_status(ranking=ranking, now=now_ist)
    memory_regression = build_memory_regression_status(memory=memory, now=now_ist)

    statuses = {
        "runtime": runtime_regression.get("runtime_regression_status"),
        "dependency": dependency_regression.get("dependency_regression_status"),
        "ranking": ranking_regression.get("ranking_regression_status"),
        "memory": memory_regression.get("memory_regression_status"),
    }
    failures = [name for name, status in statuses.items() if status == "FAIL"]
    warnings = [name for name, status in statuses.items() if status == "WARNING"]
    monitor_status = _status_from_warnings(failures, warnings)
    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "integrity_monitor_status": monitor_status,
        "continuous_validation_mode": "advisory_visibility_only",
        "monitored_domains": [
            "runtime_freshness",
            "dependency_graph_integrity",
            "ranking_ownership",
            "memory_lineage_integrity",
            "stale_artifact_regression",
            "disconnected_engine_regression",
        ],
        "status_by_domain": statuses,
        "runtime_regression_audit_path": _path_key(RUNTIME_REGRESSION_AUDIT_PATH),
        "dependency_regression_status_path": _path_key(DEPENDENCY_REGRESSION_STATUS_PATH),
        "ranking_regression_status_path": _path_key(RANKING_REGRESSION_STATUS_PATH),
        "memory_regression_status_path": _path_key(MEMORY_REGRESSION_STATUS_PATH),
        "runtime_freshness": {
            "runtime_owner": runtime_regression.get("runtime_owner"),
            "stale_runtime_artifact_count": runtime_regression.get("stale_runtime_artifact_count"),
            "stale_runtime_critical_artifact_count": runtime_regression.get("stale_runtime_critical_artifact_count"),
            "master_brain_runtime_health": master_runtime_health.get("master_brain_runtime_health"),
            "setup_runtime_health": setup_runtime_health.get("setup_runtime_health"),
            "fallback_truthfulness": fallback_resolution.get("fallback_truthfulness"),
            "scanner_confidence": fallback_resolution.get("scanner_confidence"),
        },
        "dependency_graph_integrity": {
            "dependency_integrity_score": dependency_regression.get("dependency_integrity_score"),
            "disconnected_engine_count": dependency_regression.get("disconnected_engine_count"),
            "stale_engine_count": dependency_regression.get("stale_engine_count"),
        },
        "ranking_integrity": {
            "authoritative_owner": ranking_regression.get("authoritative_owner"),
            "ranking_integrity_score": ranking_regression.get("ranking_integrity_score"),
            "ranking_chain_valid": ranking_regression.get("ranking_chain_valid"),
        },
        "memory_integrity": {
            "memory_integrity_score": memory_regression.get("memory_integrity_score"),
            "memory_freshness_score": memory_regression.get("memory_freshness_score"),
            "lineage_integrity_score": memory_regression.get("lineage_integrity_score"),
        },
        "regression_detection": {
            "runtime_drift_detected": runtime_regression.get("runtime_drift_detection", {}).get("owner_drift_detected"),
            "dependency_regression_detected": dependency_regression.get("dependency_regression_status") != "PASS",
            "ranking_regression_detected": ranking_regression.get("ranking_regression_status") != "PASS",
            "memory_regression_detected": memory_regression.get("memory_regression_status") != "PASS",
        },
        "warnings": warnings,
        "failures": failures,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    TITAN_INTEGRITY_MONITOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    TITAN_INTEGRITY_MONITOR_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def run_batch9_integrity_monitor(now=None):
    monitor = build_titan_integrity_monitor(now=now)
    return {
        "generated_at_ist": monitor.get("generated_at_ist"),
        "batch": "BATCH_9_CONTINUOUS_VALIDATION_INTEGRITY_MONITORING",
        "status": monitor.get("integrity_monitor_status"),
        "artifacts": {
            "titan_integrity_monitor": _path_key(TITAN_INTEGRITY_MONITOR_PATH),
            "runtime_regression_audit": _path_key(RUNTIME_REGRESSION_AUDIT_PATH),
            "dependency_regression_status": _path_key(DEPENDENCY_REGRESSION_STATUS_PATH),
            "ranking_regression_status": _path_key(RANKING_REGRESSION_STATUS_PATH),
            "memory_regression_status": _path_key(MEMORY_REGRESSION_STATUS_PATH),
        },
        "summary": {
            "status_by_domain": monitor.get("status_by_domain"),
            "runtime_freshness": monitor.get("runtime_freshness"),
            "dependency_graph_integrity": monitor.get("dependency_graph_integrity"),
            "ranking_integrity": monitor.get("ranking_integrity"),
            "memory_integrity": monitor.get("memory_integrity"),
            "regression_detection": monitor.get("regression_detection"),
        },
        "safety_flags": dict(SAFETY_FLAGS),
    }


if __name__ == "__main__":
    print(json.dumps(run_batch9_integrity_monitor(), indent=2, sort_keys=True))
