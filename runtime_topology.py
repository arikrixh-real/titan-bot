import json
from datetime import datetime, timezone
from pathlib import Path

from memory_health import run_memory_health_check
from ranking_integrity import build_ranking_integrity_status
from runtime_dependency_graph import SAFETY_FLAGS, build_runtime_dependency_graph
from runtime_engine_health import build_master_brain_runtime_health, build_setup_engine_runtime_health
from runtime_fallback_resolver import run_runtime_fallback_resolution
from runtime_mode_resolver import build_canonical_runtime_mode, build_runtime_warning_resolution_status
from scanner_publication_health import run_scanner_publication_health_check
from utils.market_hours import IST, as_ist_datetime


TOPOLOGY_PATH = Path("data") / "runtime" / "titan_runtime_topology.json"
VISIBILITY_AUDIT_PATH = Path("data") / "runtime" / "runtime_visibility_audit.json"
RUNTIME_PRIORITY_ORDER = [
    "runtime_health",
    "market_data_health",
    "scanner_status",
    "scanner_publication_health",
    "runtime_fallback_resolution",
    "master_brain_runtime_health",
    "setup_engine_runtime_health",
    "master_brain_status",
    "dashboard_sync_status",
    "roadmap_sidecars",
]
FRESH_SECONDS = 15 * 60
ADVISORY_FRESH_SECONDS = 24 * 60 * 60

RUNTIME_SOURCES = {
    "runtime_health": Path("data") / "runtime" / "titan_authoritative_runtime_health.json",
    "market_data_health": Path("data") / "runtime" / "titan_market_data_health.json",
    "scanner_status": Path("data") / "runtime" / "scanner_status.json",
    "scanner_publication_health": Path("data") / "runtime" / "scanner_publication_health.json",
    "scanner_runtime_heartbeat": Path("data") / "runtime" / "scanner_runtime_heartbeat.json",
    "master_brain_runtime_health": Path("data") / "runtime" / "master_brain_runtime_health.json",
    "setup_engine_runtime_health": Path("data") / "runtime" / "setup_engine_runtime_health.json",
    "runtime_fallback_resolution": Path("data") / "runtime" / "runtime_fallback_resolution.json",
    "master_brain_status": Path("data") / "runtime" / "master_brain_status.json",
    "setup_engine_status": Path("data") / "runtime" / "setup_engine_status.json",
    "dashboard_sync_status": Path("data") / "runtime" / "dashboard_sync_status.json",
    "runtime_status": Path("data") / "runtime" / "titan_runtime_status.json",
    "daemon_health": Path("data") / "runtime" / "daemon_health.json",
    "heartbeat": Path("data") / "runtime" / "titan_heartbeat.json",
    "daemon_lock": Path("data") / "runtime" / "locks" / "titan_daemon.lock",
}


def _read_json_safe(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": str(exc)}
    return payload if isinstance(payload, dict) else {"_read_error": "json_root_not_object"}


def _parse_timestamp(value):
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc).astimezone(IST)
        text = str(value).strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed.astimezone(IST)
    except Exception:
        return None


def _payload_timestamp(payload):
    for key in (
        "generated_at_ist",
        "timestamp_ist",
        "scan_finished_at_ist",
        "last_completed_at_ist",
        "timestamp",
        "updated_at",
        "created_at",
    ):
        parsed = _parse_timestamp(payload.get(key))
        if parsed is not None:
            return parsed
    return None


def _file_timestamp(path):
    try:
        path = Path(path)
        if not path.exists():
            return None
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone(IST)
    except OSError:
        return None


def _source_record(name, path, now_ist, fresh_seconds=FRESH_SECONDS):
    payload = _read_json_safe(path)
    timestamp = _payload_timestamp(payload) or _file_timestamp(path)
    age = max(0.0, (now_ist - timestamp).total_seconds()) if timestamp else None
    present = Path(path).exists()
    stale = (not present) or age is None or age > fresh_seconds
    return {
        "name": name,
        "path": str(path).replace("\\", "/"),
        "present": present,
        "status": payload.get("overall_status") or payload.get("status") or ("PRESENT" if present else "MISSING"),
        "mode": payload.get("mode") or payload.get("current_mode") or payload.get("scanner_mode"),
        "timestamp_ist": timestamp.isoformat() if timestamp else None,
        "age_seconds": round(age, 3) if age is not None else None,
        "fresh": bool(present and not stale),
        "stale": stale,
        "runtime_owner": payload.get("runtime_owner"),
        "pid": payload.get("pid") or payload.get("daemon_pid"),
    }


def _roadmap_sidecar_sources(now_ist):
    records = {}
    for path in sorted((Path("data") / "runtime").glob("*_status.json")):
        stem = path.stem
        if stem in {Path(source).stem for source in RUNTIME_SOURCES.values()}:
            continue
        if any(marker in stem for marker in ("phase", "intelligence", "learning", "genome", "regime")):
            records[stem] = _source_record(stem, path, now_ist, fresh_seconds=ADVISORY_FRESH_SECONDS)
    return records


def _memory_visibility(now_ist):
    memory = {}
    for path in sorted((Path("data") / "memory").glob("*.json")):
        memory[path.stem] = _source_record(path.stem, path, now_ist, fresh_seconds=ADVISORY_FRESH_SECONDS)
    return memory


def detect_runtime_conflicts(runtime_sources, canonical_runtime_mode=None):
    conflicts = []
    downgraded_conflicts = []
    heartbeat = runtime_sources.get("heartbeat", {})
    daemon = runtime_sources.get("daemon_health", {})
    runtime_health = runtime_sources.get("runtime_health", {})
    scanner = runtime_sources.get("scanner_status", {})
    market = runtime_sources.get("market_data_health", {})

    if heartbeat.get("status") == "ALIVE" and daemon.get("status") == "STOPPED":
        conflicts.append("heartbeat_alive_but_daemon_stopped")
    if runtime_health.get("runtime_owner") == "stale_lock_only" and heartbeat.get("status") == "ALIVE":
        conflicts.append("runtime_owner_stale_lock_but_heartbeat_alive")
    modes = {
        name: source.get("mode")
        for name, source in runtime_sources.items()
        if source.get("mode") and name in {"runtime_status", "scanner_status", "daemon_health", "heartbeat"}
    }
    if len(set(modes.values())) > 1:
        if (canonical_runtime_mode or {}).get("topology_warning_reduction_allowed"):
            downgraded_conflicts.append("conflicting_runtime_modes")
        else:
            conflicts.append("conflicting_runtime_modes")
    if scanner.get("fresh") and market.get("fresh") and scanner.get("timestamp_ist") and market.get("timestamp_ist"):
        if scanner["timestamp_ist"] > market["timestamp_ist"]:
            conflicts.append("scanner_newer_than_market_data_health")
    return conflicts, downgraded_conflicts


def _duplicate_source_detection(runtime_sources):
    groups = {
        "runtime_owner": ["runtime_health", "daemon_health", "heartbeat", "daemon_lock"],
        "market_data": ["market_data_health", "scanner_status"],
        "dashboard_visibility": ["runtime_status", "dashboard_sync_status"],
    }
    duplicates = []
    for group, names in groups.items():
        present = [name for name in names if runtime_sources.get(name, {}).get("present")]
        if len(present) > 1:
            duplicates.append({"group": group, "sources": present})
    return duplicates


def _visibility_audit(dependency_graph, runtime_sources, memory_visibility, now_ist):
    nodes = dependency_graph.get("nodes") or {}
    engines_not_reporting = [
        name
        for name in ("execution_engine", "replay", "reinforcement_learning", "dashboard_sync")
        if not nodes.get(name, {}).get("connected")
    ]
    stale_memory = [name for name, item in memory_visibility.items() if item.get("stale")]
    disconnected = dependency_graph.get("disconnected_engines") or []
    duplicated = _duplicate_source_detection(runtime_sources)
    phases_contributing_nothing = [
        name
        for name, item in nodes.items()
        if name.startswith("roadmap_") and not item.get("connected")
    ]
    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "engines_not_reporting_status": engines_not_reporting,
        "engines_with_stale_memory": stale_memory[:100],
        "engines_disconnected_from_runtime_chain": disconnected,
        "visibility_only_connected_engines": [
            name for name, node in nodes.items() if node.get("connected_visibility_only")
        ],
        "phases_contributing_nothing": phases_contributing_nothing,
        "duplicated_runtime_visibility_paths": duplicated,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    VISIBILITY_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    VISIBILITY_AUDIT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def _score(runtime_sources, dependency_graph, conflicts, visibility_audit, downgraded_conflicts=None):
    downgraded_conflicts = downgraded_conflicts or []
    total_sources = len(runtime_sources) or 1
    fresh_sources = sum(1 for source in runtime_sources.values() if source.get("fresh"))
    runtime_consistency_score = max(0.0, 100.0 - (len(conflicts) * 15.0))
    runtime_integrity_score = round((fresh_sources / total_sources) * 100, 2)
    dependency_integrity_score = dependency_graph.get("dependency_integrity_score", 0.0)
    disconnected_count = len(visibility_audit.get("engines_disconnected_from_runtime_chain") or [])
    stale_memory_count = len(visibility_audit.get("engines_with_stale_memory") or [])
    observability_score = max(
        0.0,
        round((runtime_consistency_score + runtime_integrity_score + dependency_integrity_score) / 3 - disconnected_count - min(stale_memory_count, 20) * 0.5, 2),
    )
    return {
        "runtime_integrity_score": round(runtime_integrity_score, 2),
        "dependency_integrity_score": round(dependency_integrity_score, 2),
        "runtime_consistency_score": round(runtime_consistency_score, 2),
        "downgraded_conflict_count": len(downgraded_conflicts),
        "observability_score": round(observability_score, 2),
    }


def build_runtime_topology(path=TOPOLOGY_PATH, now=None):
    now_ist = as_ist_datetime(now)
    try:
        build_master_brain_runtime_health(now=now_ist)
        build_setup_engine_runtime_health(now=now_ist)
        runtime_fallback_resolution = run_runtime_fallback_resolution(now=now_ist)
    except Exception as exc:
        runtime_fallback_resolution = {"overall_status": "FAIL", "error": str(exc)}
    try:
        scanner_publication_health = run_scanner_publication_health_check(now=now_ist)
    except Exception as exc:
        scanner_publication_health = {"overall_status": "FAIL", "publish_health": "UNAVAILABLE", "error": str(exc)}
    runtime_sources = {
        name: _source_record(name, source_path, now_ist)
        for name, source_path in RUNTIME_SOURCES.items()
    }
    roadmap_sources = _roadmap_sidecar_sources(now_ist)
    memory_visibility = _memory_visibility(now_ist)
    dependency_graph = build_runtime_dependency_graph(now=now_ist)
    try:
        memory_health = run_memory_health_check(now=now_ist)
    except Exception as exc:
        memory_health = {
            "overall_status": "FAIL",
            "error": str(exc),
            "safety_flags": dict(SAFETY_FLAGS),
        }
    try:
        ranking_integrity = build_ranking_integrity_status(now=now_ist)
    except Exception as exc:
        ranking_integrity = {
            "ranking_integrity_score": 0.0,
            "authoritative_owner": "final_decision_engine",
            "conflicting_mutators": [],
            "duplicate_rank_writers": {},
            "dangerous_live_overrides": [{"error": str(exc)}],
            "ranking_chain_valid": False,
            "safety_flags": dict(SAFETY_FLAGS),
        }
    canonical_runtime_mode = build_canonical_runtime_mode(now=now_ist)
    runtime_warning_resolution = build_runtime_warning_resolution_status(
        canonical=canonical_runtime_mode,
        now=now_ist,
    )
    runtime_conflicts, downgraded_runtime_conflicts = detect_runtime_conflicts(
        runtime_sources,
        canonical_runtime_mode=canonical_runtime_mode,
    )
    stale_runtime_sources = [
        name for name, source in runtime_sources.items() if source.get("stale")
    ]
    visibility_audit = _visibility_audit(dependency_graph, runtime_sources, memory_visibility, now_ist)
    scores = _score(
        runtime_sources,
        dependency_graph,
        runtime_conflicts,
        visibility_audit,
        downgraded_conflicts=downgraded_runtime_conflicts,
    )

    topology_health = "PASS"
    if any(not runtime_sources.get(name, {}).get("present") for name in ("runtime_health", "market_data_health", "scanner_status")):
        topology_health = "FAIL"
    elif runtime_conflicts or stale_runtime_sources or dependency_graph.get("disconnected_engines"):
        topology_health = "WARNING"

    authoritative_owner = runtime_sources.get("runtime_health", {}).get("runtime_owner") or "runtime_health"
    heartbeat = runtime_sources.get("heartbeat", {})
    authoritative_heartbeat = "heartbeat" if heartbeat.get("present") else None

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "authoritative_runtime_owner": authoritative_owner,
        "authoritative_heartbeat": authoritative_heartbeat,
        "runtime_layers": {
            "authority": ["runtime_health"],
            "market_data": ["market_data_health", "scanner_status", "runtime_fallback_resolution"],
            "decision_visibility": [
                "master_brain_runtime_health",
                "setup_engine_runtime_health",
                "master_brain_status",
                "setup_engine_status",
            ],
            "delivery_visibility": ["dashboard_sync_status", "runtime_status"],
            "sidecars": sorted(roadmap_sources.keys()),
        },
        "engine_connectivity": {
            name: {
                "connected": node.get("connected"),
                "fresh": node.get("fresh"),
                "status": node.get("status"),
                "mode": node.get("mode"),
                "connected_visibility_only": node.get("connected_visibility_only", False),
                "stale": node.get("stale", False),
                "visibility_classification": node.get("visibility_classification"),
            }
            for name, node in (dependency_graph.get("nodes") or {}).items()
        },
        "dependency_graph": {
            "path": "data/runtime/runtime_dependency_graph.json",
            "dependency_status": dependency_graph.get("dependency_status"),
            "dependency_integrity_score": dependency_graph.get("dependency_integrity_score"),
            "connected_count": len(dependency_graph.get("connected_engines") or []),
            "disconnected_engines": dependency_graph.get("disconnected_engines") or [],
            "stale_engines": dependency_graph.get("stale_engines") or [],
        },
        "runtime_sources": runtime_sources,
        "master_brain_runtime_health": _read_json_safe(RUNTIME_SOURCES["master_brain_runtime_health"]),
        "setup_engine_runtime_health": _read_json_safe(RUNTIME_SOURCES["setup_engine_runtime_health"]),
        "runtime_fallback_resolution": runtime_fallback_resolution,
        "scanner_publication_health": scanner_publication_health,
        "scanner_loop_health": scanner_publication_health.get("runtime_scheduler_health"),
        "publish_cadence_seconds": scanner_publication_health.get("publish_cadence_seconds"),
        "scan_age_seconds": scanner_publication_health.get("scan_age_seconds"),
        "scanner_writer_heartbeat": scanner_publication_health.get("scanner_writer_heartbeat"),
        "stale_cycle_detected": scanner_publication_health.get("stale_cycle_detected"),
        "scanner_confidence": runtime_fallback_resolution.get("scanner_confidence"),
        "fallback_truthfulness": runtime_fallback_resolution.get("fallback_truthfulness"),
        "off_hours_runtime_continuity": runtime_fallback_resolution.get("off_hours_runtime_continuity"),
        "master_brain_research_freshness": runtime_fallback_resolution.get("master_brain_research_freshness"),
        "setup_engine_research_freshness": runtime_fallback_resolution.get("setup_engine_research_freshness"),
        "canonical_runtime_mode": canonical_runtime_mode,
        "runtime_warning_resolution": runtime_warning_resolution,
        "runtime_conflicts": runtime_conflicts,
        "downgraded_runtime_conflicts": downgraded_runtime_conflicts,
        "raw_runtime_mode_conflicts": canonical_runtime_mode.get("raw_conflicts_visible") or [],
        "stale_runtime_sources": stale_runtime_sources,
        "runtime_priority_order": list(RUNTIME_PRIORITY_ORDER),
        "engine_visibility": visibility_audit,
        "memory_visibility": {
            "total_memory_artifacts": len(memory_visibility),
            "stale_memory_count": len(visibility_audit.get("engines_with_stale_memory") or []),
            "sample": dict(list(memory_visibility.items())[:20]),
        },
        "memory_health": {
            "path": "data/runtime/titan_memory_health.json",
            "overall_status": memory_health.get("overall_status"),
            "total_memory_files": memory_health.get("total_memory_files"),
            "stale_memory_files": memory_health.get("stale_memory_files"),
            "orphan_memory_files": memory_health.get("orphan_memory_files"),
            "corrupted_memory_files": memory_health.get("corrupted_memory_files"),
            "missing_expected_memory_files": memory_health.get("missing_expected_memory_files"),
            "memory_freshness_score": memory_health.get("memory_freshness_score"),
            "memory_integrity_score": memory_health.get("memory_integrity_score"),
            "legacy_visibility_score": memory_health.get("legacy_visibility_score"),
            "archive_candidate_count": memory_health.get("archive_candidate_count"),
            "stale_legacy_memory_count": memory_health.get("stale_legacy_memory_count"),
            "lineage_integrity_score": memory_health.get("lineage_integrity_score"),
            "missing_visibility_summary": memory_health.get("missing_visibility_summary") or [],
            "memory_cleanup_summary": memory_health.get("memory_cleanup_summary") or {},
            "memory_lineage_summary": memory_health.get("memory_lineage_summary") or {},
            "memory_contribution_summary": memory_health.get("memory_contribution_summary") or {},
        },
        "ranking_integrity": {
            "path": "data/runtime/ranking_integrity_status.json",
            "ranking_integrity_score": ranking_integrity.get("ranking_integrity_score"),
            "authoritative_owner": ranking_integrity.get("authoritative_owner"),
            "conflicting_mutators": ranking_integrity.get("conflicting_mutators") or [],
            "duplicate_rank_writers": ranking_integrity.get("duplicate_rank_writers") or {},
            "advisory_only_mutators": ranking_integrity.get("advisory_only_mutators") or [],
            "dangerous_live_overrides": ranking_integrity.get("dangerous_live_overrides") or [],
            "ranking_chain_valid": ranking_integrity.get("ranking_chain_valid"),
        },
        "observability_score": scores["observability_score"],
        "runtime_integrity_score": scores["runtime_integrity_score"],
        "dependency_integrity_score": scores["dependency_integrity_score"],
        "runtime_consistency_score": scores["runtime_consistency_score"],
        "topology_health": topology_health,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(build_runtime_topology(), indent=2, sort_keys=True))
