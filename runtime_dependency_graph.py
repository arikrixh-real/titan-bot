import json
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

from legacy_engine_visibility import build_legacy_engine_visibility
from utils.market_hours import IST, as_ist_datetime


GRAPH_PATH = Path("data") / "runtime" / "runtime_dependency_graph.json"
FRESH_SECONDS = 15 * 60
ADVISORY_FRESH_SECONDS = 24 * 60 * 60

SAFETY_FLAGS = {
    "advisory_only": True,
    "affects_live_ranking": False,
    "affects_execution": False,
    "broker_mutation": False,
    "telegram_mutation": False,
    "supabase_mutation": False,
    "live_order_behavior": False,
    "recommended_live_weight": 0.0,
    "rank_adjustment": 0.0,
}

CORE_NODES = {
    "daemon": {
        "path": Path("data") / "runtime" / "daemon_health.json",
        "mode": "live_runtime",
        "upstream": [],
        "downstream": ["scanner", "runtime_health"],
    },
    "runtime_health": {
        "path": Path("data") / "runtime" / "titan_authoritative_runtime_health.json",
        "mode": "advisory",
        "upstream": ["daemon"],
        "downstream": ["market_data_health", "runtime_status"],
    },
    "market_data_health": {
        "path": Path("data") / "runtime" / "titan_market_data_health.json",
        "mode": "advisory",
        "upstream": ["runtime_health", "scanner"],
        "downstream": ["runtime_status"],
    },
    "scanner": {
        "path": Path("data") / "runtime" / "scanner_status.json",
        "mode": "live_signal_input",
        "upstream": ["daemon", "market_data_health"],
        "downstream": ["master_brain", "setup_engine"],
    },
    "master_brain": {
        "path": Path("data") / "runtime" / "master_brain_status.json",
        "mode": "read_only_advisory",
        "upstream": ["scanner"],
        "downstream": ["execution_engine"],
    },
    "setup_engine": {
        "path": Path("data") / "runtime" / "setup_engine_status.json",
        "mode": "read_only_advisory",
        "upstream": ["scanner"],
        "downstream": ["execution_engine"],
    },
    "execution_engine": {
        "path": Path("data") / "runtime" / "execution_engine_status.json",
        "fallback_import": "titan_master_brain.execution_engine",
        "mode": "execution_visibility_only",
        "upstream": ["master_brain", "setup_engine"],
        "downstream": [],
    },
    "replay": {
        "path": Path("data") / "runtime" / "historical_replay_status.json",
        "mode": "research_only",
        "upstream": [],
        "downstream": ["reinforcement_learning"],
        "fresh_seconds": ADVISORY_FRESH_SECONDS,
    },
    "reinforcement_learning": {
        "path": Path("data") / "runtime" / "reinforcement_learning_status.json",
        "fallback_path": Path("data") / "memory" / "reinforcement_learning_memory.json",
        "fallback_import": "engines.reinforcement_learning_layer",
        "mode": "research_only",
        "upstream": ["replay"],
        "downstream": ["runtime_status"],
        "fresh_seconds": ADVISORY_FRESH_SECONDS,
    },
    "dashboard_sync": {
        "path": Path("data") / "runtime" / "dashboard_sync_status.json",
        "mode": "visibility_only",
        "upstream": ["runtime_status"],
        "downstream": [],
    },
    "runtime_status": {
        "path": Path("data") / "runtime" / "titan_runtime_status.json",
        "mode": "advisory",
        "upstream": ["runtime_health", "market_data_health"],
        "downstream": ["dashboard_sync"],
    },
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


def _module_visible(module_name):
    if not module_name:
        return False
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def _node_status(name, spec, now_ist):
    path = Path(spec["path"])
    payload = _read_json_safe(path)
    artifact_path = path
    primary_connected = bool(payload)
    if not payload and spec.get("fallback_path"):
        fallback = Path(spec["fallback_path"])
        fallback_payload = _read_json_safe(fallback)
        if fallback_payload:
            payload = fallback_payload
            artifact_path = fallback
    module_visible = _module_visible(spec.get("fallback_import"))
    if not payload and module_visible:
        payload = {
            "status": "VISIBLE_IMPORT_ONLY",
            "visibility_source": spec.get("fallback_import"),
            "advisory_only": True,
        }
        artifact_path = Path(spec.get("fallback_import", name).replace(".", "/"))
    timestamp = _payload_timestamp(payload) or _file_timestamp(artifact_path)
    age = max(0.0, (now_ist - timestamp).total_seconds()) if timestamp else None
    fresh_seconds = int(spec.get("fresh_seconds") or FRESH_SECONDS)
    connected = bool(payload)
    stale = (not connected) or age is None or age > fresh_seconds
    status = payload.get("overall_status") or payload.get("status") or ("CONNECTED" if connected else "MISSING")
    return {
        "name": name,
        "artifact_path": str(artifact_path).replace("\\", "/"),
        "connected": connected,
        "status": status,
        "fresh": bool(connected and not stale),
        "stale": stale,
        "age_seconds": round(age, 3) if age is not None else None,
        "fresh_seconds": fresh_seconds,
        "connected_visibility_only": bool(connected and not primary_connected),
        "active_runtime_worker": bool(primary_connected and spec.get("mode") == "live_runtime"),
        "module_visible": module_visible,
        "advisory": spec.get("mode") != "live_runtime",
        "mode": spec.get("mode"),
        "upstream": list(spec.get("upstream") or []),
        "downstream": list(spec.get("downstream") or []),
    }


def _discover_memory_nodes():
    nodes = {}
    for path in sorted((Path("data") / "memory").glob("*_state.json")):
        name = f"memory_{path.stem.replace('_state', '')}"
        nodes[name] = {
            "path": path,
            "mode": "memory_visibility",
            "upstream": ["runtime_status"],
            "downstream": [],
            "fresh_seconds": ADVISORY_FRESH_SECONDS,
        }
    return nodes


def _discover_roadmap_phase_nodes():
    nodes = {}
    for path in sorted((Path("data") / "runtime").glob("*_status.json")):
        stem = path.stem
        if stem in {Path(spec["path"]).stem for spec in CORE_NODES.values()}:
            continue
        if any(marker in stem for marker in ("phase", "intelligence", "learning", "genome", "regime")):
            nodes[f"roadmap_{stem}"] = {
                "path": path,
                "mode": "roadmap_sidecar",
                "upstream": ["runtime_status"],
                "downstream": [],
                "fresh_seconds": ADVISORY_FRESH_SECONDS,
            }
    return nodes


def build_runtime_dependency_graph(path=GRAPH_PATH, now=None):
    now_ist = as_ist_datetime(now)
    try:
        build_legacy_engine_visibility(now=now_ist)
    except Exception:
        pass
    node_specs = {}
    node_specs.update(CORE_NODES)
    node_specs.update(_discover_roadmap_phase_nodes())
    node_specs.update(_discover_memory_nodes())

    nodes = {name: _node_status(name, spec, now_ist) for name, spec in node_specs.items()}
    edges = []
    for name, node in nodes.items():
        for upstream in node["upstream"]:
            edges.append(
                {
                    "from": upstream,
                    "to": name,
                    "connected": bool(nodes.get(upstream, {}).get("connected") and node.get("connected")),
                    "upstream_status": nodes.get(upstream, {}).get("status", "MISSING"),
                    "downstream_status": node.get("status"),
                }
            )

    disconnected = [name for name, node in nodes.items() if not node["connected"]]
    stale = [name for name, node in nodes.items() if node["stale"]]
    dependency_status = "PASS"
    if any(name in disconnected for name in ("runtime_health", "market_data_health", "scanner")):
        dependency_status = "FAIL"
    elif disconnected or stale:
        dependency_status = "WARNING"

    connected_count = sum(1 for node in nodes.values() if node["connected"])
    fresh_count = sum(1 for node in nodes.values() if node["fresh"])
    total = len(nodes) or 1
    dependency_integrity_score = round(((connected_count + fresh_count) / (2 * total)) * 100, 2)

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "dependency_status": dependency_status,
        "dependency_integrity_score": dependency_integrity_score,
        "nodes": nodes,
        "edges": edges,
        "connected_engines": [name for name, node in nodes.items() if node["connected"]],
        "disconnected_engines": disconnected,
        "stale_engines": stale,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(build_runtime_dependency_graph(), indent=2, sort_keys=True))
