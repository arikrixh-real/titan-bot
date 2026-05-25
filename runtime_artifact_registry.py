import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from runtime_dependency_graph import SAFETY_FLAGS, build_runtime_dependency_graph
from utils.market_hours import IST, as_ist_datetime


RUNTIME_DIR = Path("data") / "runtime"
MEMORY_DIR = Path("data") / "memory"
REPORTS_DIR = Path("reports")
RESEARCH_DIR = Path("research")

RUNTIME_ARTIFACT_REGISTRY_PATH = RUNTIME_DIR / "runtime_artifact_registry.json"
DEAD_CHAIN_ISOLATION_PATH = RUNTIME_DIR / "dead_chain_isolation_status.json"
DUPLICATE_ARTIFACT_ROLES_PATH = RUNTIME_DIR / "duplicate_artifact_roles.json"
RUNTIME_CRITICAL_CHAIN_PATH = RUNTIME_DIR / "runtime_critical_chain_status.json"

ADVISORY_FRESH_SECONDS = 24 * 60 * 60
RUNTIME_FRESH_SECONDS = 15 * 60

RUNTIME_CRITICAL_CHAIN = {
    "daemon": {
        "path": RUNTIME_DIR / "daemon_health.json",
        "required": False,
        "classification": "runtime_owner_visibility",
    },
    "runtime_health": {
        "path": RUNTIME_DIR / "titan_authoritative_runtime_health.json",
        "required": True,
        "classification": "authoritative_runtime_health",
    },
    "market_data_health": {
        "path": RUNTIME_DIR / "titan_market_data_health.json",
        "required": True,
        "classification": "market_data_visibility",
    },
    "scanner": {
        "path": RUNTIME_DIR / "scanner_status.json",
        "required": True,
        "classification": "live_signal_input_visibility",
    },
    "master_brain": {
        "path": RUNTIME_DIR / "master_brain_status.json",
        "required": False,
        "classification": "decision_visibility",
    },
    "setup_engine": {
        "path": RUNTIME_DIR / "setup_engine_status.json",
        "required": False,
        "classification": "setup_visibility",
    },
    "execution_engine": {
        "path": RUNTIME_DIR / "execution_engine_status.json",
        "required": False,
        "classification": "execution_visibility_only",
    },
    "ranking_integrity": {
        "path": RUNTIME_DIR / "ranking_integrity_status.json",
        "required": True,
        "classification": "ranking_guard_visibility",
    },
    "runtime_status": {
        "path": RUNTIME_DIR / "titan_runtime_status.json",
        "required": True,
        "classification": "runtime_status_visibility",
    },
    "dashboard_sync": {
        "path": RUNTIME_DIR / "dashboard_sync_status.json",
        "required": False,
        "classification": "dashboard_visibility_only",
    },
}

RESEARCH_MARKERS = (
    "advisory",
    "agi",
    "autonomous",
    "backtesting",
    "crowd",
    "evolution",
    "historical_replay",
    "intelligence",
    "learning",
    "memory",
    "meta",
    "phase",
    "replay",
    "research",
    "shadow",
    "simulation",
    "synthetic",
)


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


def _artifact_timestamp(path, payload):
    return _payload_timestamp(payload) or _file_timestamp(path)


def _path_key(path):
    return str(Path(path)).replace("\\", "/")


def _is_under(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def _freshness(path, payload, now_ist, fresh_seconds):
    timestamp = _artifact_timestamp(path, payload)
    age = max(0.0, (now_ist - timestamp).total_seconds()) if timestamp else None
    return {
        "timestamp_ist": timestamp.isoformat() if timestamp else None,
        "age_seconds": round(age, 3) if age is not None else None,
        "fresh_seconds": fresh_seconds,
        "fresh": bool(Path(path).exists() and age is not None and age <= fresh_seconds),
        "stale": bool((not Path(path).exists()) or age is None or age > fresh_seconds),
    }


def _artifact_role(path, payload):
    path = Path(path)
    name = path.name.lower()
    critical_paths = {_path_key(spec["path"]).lower() for spec in RUNTIME_CRITICAL_CHAIN.values()}
    if _path_key(path).lower() in critical_paths:
        return "runtime_critical"
    if _is_under(path, RUNTIME_DIR):
        if any(marker in name for marker in RESEARCH_MARKERS):
            return "advisory_research_sidecar"
        if name.endswith("_status.json") or name.endswith("_health.json"):
            return "runtime_visibility"
        return "runtime_support_artifact"
    if _is_under(path, MEMORY_DIR):
        return "research_memory_artifact"
    if _is_under(path, REPORTS_DIR):
        return "research_report_artifact"
    if _is_under(path, RESEARCH_DIR):
        return "research_code_or_output"
    return "support_artifact"


def _artifact_scope(role):
    if role == "runtime_critical":
        return "runtime_critical_chain"
    if role in {"runtime_visibility", "runtime_support_artifact"}:
        return "runtime_visibility"
    if role in {"advisory_research_sidecar", "research_memory_artifact", "research_report_artifact", "research_code_or_output"}:
        return "research_or_advisory"
    return "support"


def _iter_registry_paths():
    patterns = [
        (RUNTIME_DIR, ("*.json", "*.jsonl")),
        (MEMORY_DIR, ("*.json",)),
        (REPORTS_DIR, ("*.json", "*.txt")),
        (RESEARCH_DIR, ("*.py",)),
    ]
    seen = set()
    for root, globs in patterns:
        if not root.exists():
            continue
        for pattern in globs:
            for path in sorted(root.glob(pattern)):
                key = _path_key(path)
                if key not in seen:
                    seen.add(key)
                    yield path


def _duplicate_key(path):
    stem = Path(path).stem.lower()
    for token in (
        "_status",
        "_state",
        "_memory",
        "_report",
        "_runtime",
        "_intelligence",
        "_engine",
        "_status",
    ):
        stem = stem.replace(token, "")
    return stem.strip("_-")


def build_runtime_artifact_registry(now=None):
    now_ist = as_ist_datetime(now)
    artifacts = []
    role_counts = defaultdict(int)
    scope_counts = defaultdict(int)
    for path in _iter_registry_paths():
        payload = _read_json_safe(path) if path.suffix.lower() == ".json" else {}
        role = _artifact_role(path, payload)
        scope = _artifact_scope(role)
        fresh_seconds = RUNTIME_FRESH_SECONDS if role in {"runtime_critical", "runtime_visibility"} else ADVISORY_FRESH_SECONDS
        record = {
            "path": _path_key(path),
            "artifact_name": path.name,
            "role": role,
            "scope": scope,
            "present": path.exists(),
            "status": payload.get("overall_status") or payload.get("status") or ("PRESENT" if path.exists() else "MISSING"),
            "duplicate_key": _duplicate_key(path),
            "advisory_only": role != "runtime_critical",
            "runtime_critical": role == "runtime_critical",
            "research_or_sample": scope == "research_or_advisory",
            **_freshness(path, payload, now_ist, fresh_seconds),
        }
        artifacts.append(record)
        role_counts[role] += 1
        scope_counts[scope] += 1

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "registry_status": "PASS",
        "artifact_count": len(artifacts),
        "role_counts": dict(sorted(role_counts.items())),
        "scope_counts": dict(sorted(scope_counts.items())),
        "artifacts": artifacts,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    RUNTIME_ARTIFACT_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_ARTIFACT_REGISTRY_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_runtime_critical_chain_status(now=None, graph=None):
    now_ist = as_ist_datetime(now)
    graph = graph or build_runtime_dependency_graph(now=now_ist)
    graph_nodes = graph.get("nodes") or {}
    chain = {}
    missing_required = []
    stale_required = []
    for name, spec in RUNTIME_CRITICAL_CHAIN.items():
        path = spec["path"]
        payload = _read_json_safe(path)
        fresh = _freshness(path, payload, now_ist, RUNTIME_FRESH_SECONDS)
        graph_node = graph_nodes.get(name) or {}
        record = {
            "path": _path_key(path),
            "required": spec["required"],
            "classification": spec["classification"],
            "present": path.exists(),
            "graph_connected": bool(graph_node.get("connected", path.exists())),
            "graph_visibility_classification": graph_node.get("visibility_classification"),
            "status": payload.get("overall_status") or payload.get("status") or graph_node.get("status") or ("PRESENT" if path.exists() else "MISSING"),
            "mutates_live_behavior": False,
            "advisory_visibility_only": spec["classification"] != "live_signal_input_visibility",
            **fresh,
        }
        chain[name] = record
        if spec["required"] and not record["present"]:
            missing_required.append(name)
        if spec["required"] and record["stale"]:
            stale_required.append(name)

    status = "PASS"
    if missing_required:
        status = "FAIL"
    elif stale_required:
        status = "WARNING"

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "runtime_critical_chain_status": status,
        "authoritative_ranking_owner": "final_decision_engine",
        "ranking_owner_mutated": False,
        "execution_behavior_mutated": False,
        "scanner_selection_mutated": False,
        "missing_required_nodes": missing_required,
        "stale_required_nodes": stale_required,
        "chain": chain,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    RUNTIME_CRITICAL_CHAIN_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_dead_chain_isolation_status(now=None, graph=None):
    now_ist = as_ist_datetime(now)
    graph = graph or build_runtime_dependency_graph(now=now_ist)
    critical = set(RUNTIME_CRITICAL_CHAIN)
    dead_chains = []
    isolated_count = 0
    for name, node in sorted((graph.get("nodes") or {}).items()):
        disconnected = not node.get("connected")
        stale = bool(node.get("stale"))
        critical_node = name in critical
        if not disconnected and not stale:
            continue
        isolation = "runtime_critical_visibility_required" if critical_node else "isolated_advisory_dead_chain"
        if not critical_node:
            isolated_count += 1
        dead_chains.append(
            {
                "name": name,
                "artifact_path": node.get("artifact_path"),
                "mode": node.get("mode"),
                "connected": bool(node.get("connected")),
                "stale": stale,
                "fresh": bool(node.get("fresh")),
                "visibility_classification": node.get("visibility_classification"),
                "isolation_classification": isolation,
                "excluded_from_runtime_integrity": not critical_node,
                "requires_manual_review": critical_node,
                "delete_recommended": False,
                "auto_repair_allowed": False,
            }
        )

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "dead_chain_isolation_status": "PASS",
        "dead_chain_count": len(dead_chains),
        "isolated_advisory_dead_chain_count": isolated_count,
        "runtime_critical_review_count": len(dead_chains) - isolated_count,
        "dead_chains": dead_chains,
        "topology_refinement": {
            "runtime_critical_nodes_remain_visible": sorted(critical),
            "advisory_dead_chains_isolated_from_runtime_integrity": True,
            "research_artifacts_do_not_poison_runtime_integrity": True,
            "automatic_deletion": False,
        },
        "safety_flags": dict(SAFETY_FLAGS),
    }
    DEAD_CHAIN_ISOLATION_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_duplicate_artifact_roles(registry=None, now=None):
    now_ist = as_ist_datetime(now)
    registry = registry or build_runtime_artifact_registry(now=now_ist)
    groups = defaultdict(list)
    for item in registry.get("artifacts") or []:
        key = item.get("duplicate_key")
        if key:
            groups[key].append(item)

    duplicate_groups = []
    for key, items in sorted(groups.items()):
        if len(items) < 2:
            continue
        runtime_critical = [item for item in items if item.get("runtime_critical")]
        research = [item for item in items if item.get("research_or_sample")]
        duplicate_groups.append(
            {
                "duplicate_key": key,
                "artifact_count": len(items),
                "runtime_critical_count": len(runtime_critical),
                "research_or_sample_count": len(research),
                "classification": "runtime_research_name_overlap" if runtime_critical and research else "research_duplicate_family",
                "poisons_runtime_integrity": False,
                "delete_recommended": False,
                "members": [
                    {
                        "path": item["path"],
                        "role": item["role"],
                        "scope": item["scope"],
                        "status": item["status"],
                    }
                    for item in items
                ],
            }
        )

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "duplicate_artifact_role_status": "PASS",
        "duplicate_group_count": len(duplicate_groups),
        "duplicate_groups": duplicate_groups,
        "classification_policy": {
            "runtime_critical_wins_over_research": True,
            "research_and_sample_artifacts_visibility_only": True,
            "automatic_deletion": False,
            "runtime_behavior_mutation": False,
        },
        "safety_flags": dict(SAFETY_FLAGS),
    }
    DUPLICATE_ARTIFACT_ROLES_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def run_batch7_artifact_isolation(now=None):
    now_ist = as_ist_datetime(now)
    graph = build_runtime_dependency_graph(now=now_ist)
    registry = build_runtime_artifact_registry(now=now_ist)
    critical = build_runtime_critical_chain_status(now=now_ist, graph=graph)
    dead = build_dead_chain_isolation_status(now=now_ist, graph=graph)
    duplicate = build_duplicate_artifact_roles(registry=registry, now=now_ist)
    status = "PASS"
    if critical.get("runtime_critical_chain_status") == "FAIL":
        status = "FAIL"
    elif critical.get("runtime_critical_chain_status") == "WARNING":
        status = "WARNING"
    return {
        "generated_at_ist": now_ist.isoformat(),
        "batch": "BATCH_7_DUPLICATION_CLEANUP_DEAD_CHAIN_ISOLATION",
        "status": status,
        "artifacts": {
            "runtime_artifact_registry": _path_key(RUNTIME_ARTIFACT_REGISTRY_PATH),
            "dead_chain_isolation_status": _path_key(DEAD_CHAIN_ISOLATION_PATH),
            "duplicate_artifact_roles": _path_key(DUPLICATE_ARTIFACT_ROLES_PATH),
            "runtime_critical_chain_status": _path_key(RUNTIME_CRITICAL_CHAIN_PATH),
        },
        "summary": {
            "registered_artifacts": registry.get("artifact_count"),
            "dead_chains": dead.get("dead_chain_count"),
            "isolated_advisory_dead_chains": dead.get("isolated_advisory_dead_chain_count"),
            "duplicate_groups": duplicate.get("duplicate_group_count"),
            "runtime_critical_chain_status": critical.get("runtime_critical_chain_status"),
        },
        "safety_flags": dict(SAFETY_FLAGS),
    }


if __name__ == "__main__":
    print(json.dumps(run_batch7_artifact_isolation(), indent=2, sort_keys=True))
