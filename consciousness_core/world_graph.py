from pathlib import Path

from consciousness_core.state import atomic_write_json, now_ist, stable_hash


WORLD_GRAPH_PATH = Path("data") / "consciousness_core" / "world_graph.json"
MAX_NODES = 500
MAX_EDGES = 1200
CHAIN = ("macro", "market", "sector", "stock", "setup", "decision", "outcome", "lesson")


def load_world_graph(path=WORLD_GRAPH_PATH):
    try:
        import json

        with Path(path).open("r", encoding="utf-8") as graph_file:
            payload = json.load(graph_file)
        if isinstance(payload, dict):
            payload.setdefault("nodes", [])
            payload.setdefault("edges", [])
            return payload
    except Exception:
        pass
    return {"nodes": [], "edges": [], "updated_at": now_ist()}


def _node(kind, label):
    node_id = f"{kind}_{stable_hash(label)[:16]}"
    return {
        "node_id": node_id,
        "kind": kind,
        "label": label,
        "last_seen": now_ist(),
        "count": 1,
    }


def update_world_graph(observations, lessons=None, path=WORLD_GRAPH_PATH):
    graph = load_world_graph(path)
    nodes = {node["node_id"]: node for node in graph.get("nodes", [])}
    edges = graph.get("edges", [])
    for observation in observations[:80]:
        source = observation.get("source", "unknown")
        previous_id = None
        labels = {
            "macro": "runtime context",
            "market": "observed system state",
            "sector": source.split("/")[1] if "/" in source else "general",
            "stock": "portfolio universe",
            "setup": source,
            "decision": observation.get("status", "unknown"),
            "outcome": f"records={observation.get('metadata', {}).get('record_count', 0)}",
            "lesson": "pending reflection",
        }
        if lessons:
            labels["lesson"] = lessons[0]
        for kind in CHAIN:
            node = _node(kind, labels[kind])
            existing = nodes.get(node["node_id"])
            if existing:
                existing["count"] = int(existing.get("count") or 0) + 1
                existing["last_seen"] = now_ist()
            else:
                nodes[node["node_id"]] = node
            if previous_id:
                edges.append(
                    {
                        "from": previous_id,
                        "to": node["node_id"],
                        "relationship": "leads_to",
                        "last_seen": now_ist(),
                    }
                )
            previous_id = node["node_id"]
    graph["nodes"] = list(nodes.values())[-MAX_NODES:]
    graph["edges"] = edges[-MAX_EDGES:]
    graph["updated_at"] = now_ist()
    atomic_write_json(path, graph)
    return graph

