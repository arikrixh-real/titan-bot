import json
from datetime import datetime, timezone
from pathlib import Path

from runtime_dependency_graph import SAFETY_FLAGS
from utils.market_hours import IST, as_ist_datetime


RUNTIME_DIR = Path("data") / "runtime"

DASHBOARD_TRUTH_REGISTRY_PATH = RUNTIME_DIR / "dashboard_truth_registry.json"
METRIC_DEPENDENCY_GRAPH_PATH = RUNTIME_DIR / "metric_dependency_graph.json"
CANONICAL_METRIC_OWNERSHIP_PATH = RUNTIME_DIR / "canonical_metric_ownership.json"
DASHBOARD_RUNTIME_INTEGRITY_PATH = RUNTIME_DIR / "dashboard_runtime_integrity.json"

RUNTIME_FRESH_SECONDS = 15 * 60
ADVISORY_FRESH_SECONDS = 24 * 60 * 60
EXTERNAL_READONLY_FRESH_SECONDS = 15 * 60


DASHBOARD_METRIC_SPECS = {
    "deterministic_runtime_owner": {
        "owner": "titan_runtime_watchdog",
        "artifact_path": RUNTIME_DIR / "titan_runtime_watchdog.json",
        "field": "deterministic_runtime_owner",
        "classification": "runtime_critical",
        "fresh_seconds": RUNTIME_FRESH_SECONDS,
        "dependencies": ["daemon_health", "heartbeat", "daemon_lock", "visible_process"],
    },
    "authoritative_pid": {
        "owner": "titan_runtime_watchdog",
        "artifact_path": RUNTIME_DIR / "titan_runtime_watchdog.json",
        "field": "authoritative_pid",
        "classification": "runtime_critical",
        "fresh_seconds": RUNTIME_FRESH_SECONDS,
        "dependencies": ["daemon_health", "heartbeat", "daemon_lock", "visible_process"],
    },
    "runtime_mode": {
        "owner": "titan_runtime_status",
        "artifact_path": RUNTIME_DIR / "titan_runtime_status.json",
        "field": "mode",
        "classification": "runtime_critical",
        "fresh_seconds": RUNTIME_FRESH_SECONDS,
        "dependencies": ["authoritative_runtime_health", "scanner_status"],
    },
    "daemon_status": {
        "owner": "authoritative_runtime_health",
        "artifact_path": RUNTIME_DIR / "titan_authoritative_runtime_health.json",
        "field": "status",
        "classification": "runtime_critical",
        "fresh_seconds": RUNTIME_FRESH_SECONDS,
        "dependencies": ["daemon_health", "heartbeat", "daemon_lock"],
    },
    "heartbeat_status": {
        "owner": "heartbeat",
        "artifact_path": RUNTIME_DIR / "titan_heartbeat.json",
        "field": "status",
        "classification": "runtime_critical",
        "fresh_seconds": RUNTIME_FRESH_SECONDS,
        "dependencies": ["daemon_health"],
    },
    "scanner_status": {
        "owner": "scanner_status",
        "artifact_path": RUNTIME_DIR / "scanner_status.json",
        "field": "status",
        "classification": "runtime_critical",
        "fresh_seconds": RUNTIME_FRESH_SECONDS,
        "dependencies": ["authoritative_runtime_health", "market_data_health"],
    },
    "stocks_checked": {
        "owner": "scanner_status",
        "artifact_path": RUNTIME_DIR / "scanner_status.json",
        "field": "stocks_checked",
        "classification": "runtime_critical",
        "fresh_seconds": RUNTIME_FRESH_SECONDS,
        "dependencies": ["market_data_health"],
    },
    "final_passed": {
        "owner": "scanner_status",
        "artifact_path": RUNTIME_DIR / "scanner_status.json",
        "field": "final_passed",
        "classification": "runtime_critical",
        "fresh_seconds": RUNTIME_FRESH_SECONDS,
        "dependencies": ["final_decision_engine", "ranking_integrity"],
    },
    "telegram_alerts_this_scan": {
        "owner": "scanner_status",
        "artifact_path": RUNTIME_DIR / "scanner_status.json",
        "field": "alerts_sent",
        "classification": "runtime_critical",
        "fresh_seconds": RUNTIME_FRESH_SECONDS,
        "dependencies": ["scanner_status"],
    },
    "market_data_status": {
        "owner": "market_data_health",
        "artifact_path": RUNTIME_DIR / "titan_market_data_health.json",
        "field": "status",
        "classification": "runtime_critical",
        "fresh_seconds": RUNTIME_FRESH_SECONDS,
        "dependencies": ["ohlc_refresh_status", "live_price_status"],
    },
    "ranking_integrity_score": {
        "owner": "ranking_integrity",
        "artifact_path": RUNTIME_DIR / "ranking_integrity_status.json",
        "field": "ranking_integrity_score",
        "classification": "runtime_critical",
        "fresh_seconds": ADVISORY_FRESH_SECONDS,
        "dependencies": ["final_decision_engine"],
    },
    "authoritative_ranking_owner": {
        "owner": "ranking_integrity",
        "artifact_path": RUNTIME_DIR / "ranking_integrity_status.json",
        "field": "authoritative_owner",
        "classification": "runtime_critical",
        "fresh_seconds": ADVISORY_FRESH_SECONDS,
        "dependencies": ["final_decision_engine"],
    },
    "topology_health": {
        "owner": "runtime_topology",
        "artifact_path": RUNTIME_DIR / "titan_runtime_topology.json",
        "field": "topology_health",
        "classification": "advisory",
        "fresh_seconds": ADVISORY_FRESH_SECONDS,
        "dependencies": ["runtime_dependency_graph", "memory_health", "ranking_integrity"],
    },
    "dependency_integrity_score": {
        "owner": "runtime_dependency_graph",
        "artifact_path": RUNTIME_DIR / "runtime_dependency_graph.json",
        "field": "dependency_integrity_score",
        "classification": "advisory",
        "fresh_seconds": ADVISORY_FRESH_SECONDS,
        "dependencies": ["runtime_status", "scanner_status", "ranking_integrity"],
    },
    "memory_integrity_score": {
        "owner": "memory_health",
        "artifact_path": RUNTIME_DIR / "titan_memory_health.json",
        "field": "memory_integrity_score",
        "classification": "advisory",
        "fresh_seconds": ADVISORY_FRESH_SECONDS,
        "dependencies": ["memory_lineage_graph", "memory_contribution_status"],
    },
    "live_trades_count": {
        "owner": "supabase_trades_read_only",
        "artifact_path": None,
        "field": "open_trade_count",
        "classification": "external_readonly",
        "fresh_seconds": EXTERNAL_READONLY_FRESH_SECONDS,
        "dependencies": ["trade_execution_layer", "supabase_read_only_client"],
    },
    "closed_trade_performance": {
        "owner": "supabase_closed_trades_read_only",
        "artifact_path": None,
        "field": "closed_trade_performance",
        "classification": "external_readonly",
        "fresh_seconds": EXTERNAL_READONLY_FRESH_SECONDS,
        "dependencies": ["outcome_tracker", "supabase_read_only_client"],
    },
}


def _path_key(path):
    if path is None:
        return None
    return str(Path(path)).replace("\\", "/")


def _read_json_safe(path):
    if path is None:
        return {}
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
        if not text:
            return None
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
        "acquired_at_ist",
        "updated_at",
        "created_at",
        "timestamp",
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


def _artifact_freshness(path, fresh_seconds, now_ist):
    if path is None:
        return {
            "artifact_path": None,
            "present": False,
            "locally_verifiable": False,
            "timestamp_ist": None,
            "age_seconds": None,
            "fresh_seconds": fresh_seconds,
            "fresh": None,
            "stale": None,
            "status": "EXTERNAL_READONLY_NOT_LOCALLY_VERIFIED",
        }
    path = Path(path)
    payload = _read_json_safe(path)
    timestamp = _payload_timestamp(payload) or _file_timestamp(path)
    age = max(0.0, (now_ist - timestamp).total_seconds()) if timestamp else None
    present = path.exists()
    stale = (not present) or age is None or age > fresh_seconds
    status = payload.get("overall_status") or payload.get("status") or ("PRESENT" if present else "MISSING")
    return {
        "artifact_path": _path_key(path),
        "present": present,
        "locally_verifiable": True,
        "timestamp_ist": timestamp.isoformat() if timestamp else None,
        "age_seconds": round(age, 3) if age is not None else None,
        "fresh_seconds": fresh_seconds,
        "fresh": bool(present and not stale),
        "stale": bool(stale),
        "status": status,
    }


def _metric_record(name, spec, now_ist):
    freshness = _artifact_freshness(spec.get("artifact_path"), int(spec.get("fresh_seconds")), now_ist)
    classification = spec.get("classification")
    stale_critical = classification == "runtime_critical" and freshness.get("stale") is True
    return {
        "metric": name,
        "canonical_owner": spec.get("owner"),
        "artifact_path": freshness.get("artifact_path"),
        "field": spec.get("field"),
        "classification": classification,
        "runtime_critical": classification == "runtime_critical",
        "advisory": classification == "advisory",
        "external_readonly": classification == "external_readonly",
        "dependencies": list(spec.get("dependencies") or []),
        "freshness": freshness,
        "stale_metric_detected": freshness.get("stale") is True,
        "stale_runtime_critical_metric": stale_critical,
        "owner_contract": {
            "single_canonical_owner": True,
            "dashboard_may_render": True,
            "dashboard_may_mutate_owner": False,
            "advisory_only": True,
        },
    }


def _status_from_issues(failures, warnings):
    if failures:
        return "FAIL"
    if warnings:
        return "WARNING"
    return "PASS"


def build_canonical_metric_ownership(path=None, now=None, metric_specs=None):
    path = path or CANONICAL_METRIC_OWNERSHIP_PATH
    now_ist = as_ist_datetime(now)
    metric_specs = metric_specs or DASHBOARD_METRIC_SPECS
    metrics = {
        name: _metric_record(name, spec, now_ist)
        for name, spec in sorted(metric_specs.items())
    }
    duplicate_owner_fields = {}
    seen = {}
    for name, record in metrics.items():
        key = (record.get("canonical_owner"), record.get("field"))
        seen.setdefault(key, []).append(name)
    for key, names in seen.items():
        if len(names) > 1:
            duplicate_owner_fields[f"{key[0]}.{key[1]}"] = names

    warnings = []
    failures = []
    stale_critical = [name for name, record in metrics.items() if record.get("stale_runtime_critical_metric")]
    if duplicate_owner_fields:
        warnings.append("duplicate_owner_field_visible")
    if stale_critical:
        warnings.append("stale_runtime_critical_dashboard_metric")

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "canonical_metric_ownership_status": _status_from_issues(failures, warnings),
        "metric_count": len(metrics),
        "runtime_critical_metric_count": sum(1 for record in metrics.values() if record.get("runtime_critical")),
        "advisory_metric_count": sum(1 for record in metrics.values() if record.get("advisory")),
        "external_readonly_metric_count": sum(1 for record in metrics.values() if record.get("external_readonly")),
        "metrics": metrics,
        "duplicate_owner_fields": duplicate_owner_fields,
        "stale_runtime_critical_metrics": stale_critical,
        "warnings": warnings,
        "failures": failures,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_metric_dependency_graph(ownership=None, path=None, now=None):
    path = path or METRIC_DEPENDENCY_GRAPH_PATH
    now_ist = as_ist_datetime(now)
    ownership = ownership if isinstance(ownership, dict) else build_canonical_metric_ownership(now=now_ist)
    metric_nodes = ownership.get("metrics") or {}
    owner_nodes = sorted({record.get("canonical_owner") for record in metric_nodes.values() if record.get("canonical_owner")})
    dependencies = []
    stale_edges = []
    for metric, record in sorted(metric_nodes.items()):
        owner = record.get("canonical_owner")
        dependencies.append({"from": owner, "to": metric, "type": "owns_metric"})
        for upstream in record.get("dependencies") or []:
            dependencies.append({"from": upstream, "to": metric, "type": "upstream_dependency"})
        if record.get("stale_metric_detected"):
            stale_edges.append({"owner": owner, "metric": metric, "artifact_path": record.get("artifact_path")})

    warnings = []
    failures = []
    if stale_edges:
        warnings.append("stale_metric_dependency_visible")
    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "metric_dependency_graph_status": _status_from_issues(failures, warnings),
        "metric_node_count": len(metric_nodes),
        "owner_node_count": len(owner_nodes),
        "owner_nodes": owner_nodes,
        "metric_nodes": sorted(metric_nodes.keys()),
        "dependencies": dependencies,
        "stale_dependency_edges": stale_edges,
        "warnings": warnings,
        "failures": failures,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_dashboard_truth_registry(ownership=None, dependency_graph=None, path=None, now=None):
    path = path or DASHBOARD_TRUTH_REGISTRY_PATH
    now_ist = as_ist_datetime(now)
    ownership = ownership if isinstance(ownership, dict) else build_canonical_metric_ownership(now=now_ist)
    dependency_graph = dependency_graph if isinstance(dependency_graph, dict) else build_metric_dependency_graph(ownership=ownership, now=now_ist)
    metrics = ownership.get("metrics") or {}
    canonical_sources = {}
    for name, record in sorted(metrics.items()):
        owner = record.get("canonical_owner")
        canonical_sources.setdefault(owner, []).append(name)

    warnings = []
    failures = []
    if ownership.get("stale_runtime_critical_metrics"):
        warnings.append("stale_runtime_critical_dashboard_metric")
    if dependency_graph.get("stale_dependency_edges"):
        warnings.append("stale_metric_dependency_visible")

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "dashboard_truth_registry_status": _status_from_issues(failures, warnings),
        "source_of_truth_mode": "backend_visibility_only",
        "dashboard_rendering_mutation": False,
        "canonical_sources": canonical_sources,
        "metric_count": len(metrics),
        "runtime_critical_metrics": [
            name for name, record in metrics.items() if record.get("runtime_critical")
        ],
        "advisory_metrics": [
            name for name, record in metrics.items() if record.get("advisory")
        ],
        "external_readonly_metrics": [
            name for name, record in metrics.items() if record.get("external_readonly")
        ],
        "freshness_hierarchy": {
            "runtime_critical_seconds": RUNTIME_FRESH_SECONDS,
            "external_readonly_seconds": EXTERNAL_READONLY_FRESH_SECONDS,
            "advisory_seconds": ADVISORY_FRESH_SECONDS,
        },
        "metric_dependency_graph_path": _path_key(METRIC_DEPENDENCY_GRAPH_PATH),
        "canonical_metric_ownership_path": _path_key(CANONICAL_METRIC_OWNERSHIP_PATH),
        "warnings": warnings,
        "failures": failures,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_dashboard_runtime_integrity(registry=None, ownership=None, dependency_graph=None, path=None, now=None):
    path = path or DASHBOARD_RUNTIME_INTEGRITY_PATH
    now_ist = as_ist_datetime(now)
    ownership = ownership if isinstance(ownership, dict) else build_canonical_metric_ownership(now=now_ist)
    dependency_graph = dependency_graph if isinstance(dependency_graph, dict) else build_metric_dependency_graph(ownership=ownership, now=now_ist)
    registry = registry if isinstance(registry, dict) else build_dashboard_truth_registry(
        ownership=ownership,
        dependency_graph=dependency_graph,
        now=now_ist,
    )
    metrics = ownership.get("metrics") or {}
    stale_metrics = [name for name, record in metrics.items() if record.get("stale_metric_detected")]
    stale_critical = [name for name, record in metrics.items() if record.get("stale_runtime_critical_metric")]
    missing_local = [
        name
        for name, record in metrics.items()
        if record.get("freshness", {}).get("locally_verifiable") and not record.get("freshness", {}).get("present")
    ]
    failures = []
    warnings = []
    if stale_critical:
        warnings.append("stale_runtime_critical_dashboard_metric")
    if missing_local:
        warnings.append("missing_local_dashboard_metric_owner")
    if registry.get("dashboard_rendering_mutation"):
        failures.append("dashboard_rendering_mutation_detected")

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "dashboard_runtime_integrity_status": _status_from_issues(failures, warnings),
        "dashboard_backend_truth_stabilized": not failures,
        "metric_count": len(metrics),
        "stale_metric_count": len(stale_metrics),
        "stale_runtime_critical_metric_count": len(stale_critical),
        "missing_local_metric_owner_count": len(missing_local),
        "stale_metrics": stale_metrics,
        "stale_runtime_critical_metrics": stale_critical,
        "missing_local_metric_owners": missing_local,
        "source_of_truth_registry_path": _path_key(DASHBOARD_TRUTH_REGISTRY_PATH),
        "metric_dependency_graph_path": _path_key(METRIC_DEPENDENCY_GRAPH_PATH),
        "canonical_metric_ownership_path": _path_key(CANONICAL_METRIC_OWNERSHIP_PATH),
        "stale_metric_detection": {
            "runtime_critical_metrics_checked": True,
            "advisory_metrics_checked": True,
            "external_readonly_metrics_classified": True,
            "stale_runtime_critical_metric_detected": bool(stale_critical),
        },
        "warnings": warnings,
        "failures": failures,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def run_batch11_dashboard_truth_foundation(now=None):
    now_ist = as_ist_datetime(now)
    ownership = build_canonical_metric_ownership(now=now_ist)
    dependency_graph = build_metric_dependency_graph(ownership=ownership, now=now_ist)
    registry = build_dashboard_truth_registry(ownership=ownership, dependency_graph=dependency_graph, now=now_ist)
    integrity = build_dashboard_runtime_integrity(
        registry=registry,
        ownership=ownership,
        dependency_graph=dependency_graph,
        now=now_ist,
    )
    statuses = {
        "dashboard_truth_registry": registry.get("dashboard_truth_registry_status"),
        "metric_dependency_graph": dependency_graph.get("metric_dependency_graph_status"),
        "canonical_metric_ownership": ownership.get("canonical_metric_ownership_status"),
        "dashboard_runtime_integrity": integrity.get("dashboard_runtime_integrity_status"),
    }
    failures = [name for name, status in statuses.items() if status == "FAIL"]
    warnings = [name for name, status in statuses.items() if status == "WARNING"]
    return {
        "generated_at_ist": now_ist.isoformat(),
        "batch": "BATCH_11_DASHBOARD_SOURCE_OF_TRUTH_FOUNDATION",
        "status": _status_from_issues(failures, warnings),
        "artifacts": {
            "dashboard_truth_registry": _path_key(DASHBOARD_TRUTH_REGISTRY_PATH),
            "metric_dependency_graph": _path_key(METRIC_DEPENDENCY_GRAPH_PATH),
            "canonical_metric_ownership": _path_key(CANONICAL_METRIC_OWNERSHIP_PATH),
            "dashboard_runtime_integrity": _path_key(DASHBOARD_RUNTIME_INTEGRITY_PATH),
        },
        "summary": {
            "status_by_artifact": statuses,
            "metric_count": ownership.get("metric_count"),
            "runtime_critical_metric_count": ownership.get("runtime_critical_metric_count"),
            "advisory_metric_count": ownership.get("advisory_metric_count"),
            "external_readonly_metric_count": ownership.get("external_readonly_metric_count"),
            "stale_runtime_critical_metric_count": integrity.get("stale_runtime_critical_metric_count"),
            "dashboard_backend_truth_stabilized": integrity.get("dashboard_backend_truth_stabilized"),
        },
        "warnings": warnings,
        "failures": failures,
        "safety_flags": dict(SAFETY_FLAGS),
    }


if __name__ == "__main__":
    print(json.dumps(run_batch11_dashboard_truth_foundation(), indent=2, sort_keys=True))
