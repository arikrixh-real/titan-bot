"""Read-only architecture mapper for TITAN ECHO."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_RUNTIME = REPO_ROOT / "data" / "runtime" / "echo"
INDEX_PATH = ECHO_RUNTIME / "titan_file_index.json"
ARCHITECTURE_MAP_PATH = ECHO_RUNTIME / "titan_architecture_map.json"
MODULE_REGISTRY_PATH = ECHO_RUNTIME / "titan_module_registry.json"
CONNECTION_GRAPH_PATH = ECHO_RUNTIME / "titan_connection_graph.json"

LAYERS = [
    "ECHO layer",
    "Unified Brain layer",
    "Consciousness Core layer",
    "Master Brain layer",
    "Runtime/Daemon layer",
    "Scanner/Setup layer",
    "Engine/Filter layer",
    "Risk/Execution layer",
    "Outcome/Learning/Evolution layer",
    "News/Research/Memory layer",
    "Data/Supabase layer",
    "Dashboard/Reporting layer",
    "Tools/Diagnostics layer",
    "Docs/Config layer",
    "Unknown/Unclassified layer",
]

TOP_HIERARCHY = {
    "authority": "Ari",
    "sequence": [
        "Ari",
        "ECHO",
        "Unified Brain",
        "Consciousness Core",
        "Master Brain",
        "Specialist Engines",
        "Data/Runtime/Memory/Logs",
    ],
    "edges": [
        {"from": "Ari", "to": "ECHO"},
        {"from": "ECHO", "to": "Unified Brain"},
        {"from": "Unified Brain", "to": "Consciousness Core"},
        {"from": "Consciousness Core", "to": "Master Brain"},
        {"from": "Master Brain", "to": "Specialist Engines"},
        {"from": "Specialist Engines", "to": "Data/Runtime/Memory/Logs"},
    ],
}


def load_file_index() -> list[dict[str, Any]]:
    with INDEX_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    files = data.get("files", [])
    if not isinstance(files, list):
        raise ValueError("titan_file_index.json field 'files' must be a list")
    return [item for item in files if isinstance(item, dict)]


def classify_layer(item: dict[str, Any]) -> str:
    path = str(item.get("relative_path", "")).lower()
    role = str(item.get("probable_role", "")).lower()

    if path.startswith("titan_echo/"):
        return "ECHO layer"
    if "unified_brain" in path or "unified brain" in role:
        return "Unified Brain layer"
    if path.startswith("consciousness_core/") or "consciousness core" in role:
        return "Consciousness Core layer"
    if "master_brain" in path or "master brain" in role:
        return "Master Brain layer"
    if "risk" in path or "broker" in path or "order" in path or "execution" in path:
        return "Risk/Execution layer"
    if path.startswith("runtime_") or "/runtime_" in path or "daemon" in path:
        return "Runtime/Daemon layer"
    if "scanner" in path or "setup" in path:
        return "Scanner/Setup layer"
    if path.startswith("engines/") or "engine" in path or "filter" in path:
        return "Engine/Filter layer"
    if (
        "outcome" in path
        or "learning" in path
        or "evolution" in path
        or "backtest" in path
    ):
        return "Outcome/Learning/Evolution layer"
    if (
        "news" in path
        or "research" in path
        or "memory" in path
        or "knowledge" in path
        or "journal" in path
    ):
        return "News/Research/Memory layer"
    if "supabase" in path or path.startswith("data/") or path.startswith("state/"):
        return "Data/Supabase layer"
    if "dashboard" in path or path.startswith("reports/") or "report" in path:
        return "Dashboard/Reporting layer"
    if path.startswith("tools/") or "diagnostic" in path or path.startswith("tests/"):
        return "Tools/Diagnostics layer"
    if item.get("extension") in {".md", ".json", ".yaml", ".yml", ".txt"}:
        return "Docs/Config layer"
    return "Unknown/Unclassified layer"


def module_name_for(item: dict[str, Any], layer: str) -> str:
    rel_path = str(item.get("relative_path", "unknown"))
    parts = rel_path.split("/")
    if layer == "ECHO layer":
        return "titan_echo"
    if len(parts) > 1:
        return parts[0]
    stem = Path(rel_path).stem
    if stem.startswith("runtime_"):
        return "runtime"
    return stem or "unknown"


def safety_note_for(layer: str, critical: int, high: int) -> str:
    if critical:
        return f"Read-only mapped group; {critical} CRITICAL files require explicit Ari approval before modification."
    if high:
        return f"Read-only mapped group; {high} HIGH files require review and verification before modification."
    if layer in {"Docs/Config layer", "Unknown/Unclassified layer"}:
        return "Read-only mapped group; verify ownership before modification."
    return "Read-only mapped group; review dependencies before modification."


def build_architecture(files: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {layer: [] for layer in LAYERS}
    for item in files:
        layer = classify_layer(item)
        item["_echo_layer"] = layer
        item["_echo_module"] = module_name_for(item, layer)
        grouped[layer].append(item)

    layer_summary = []
    for layer in LAYERS:
        layer_files = grouped[layer]
        critical = sum(1 for item in layer_files if item.get("criticality") == "CRITICAL")
        high = sum(1 for item in layer_files if item.get("criticality") == "HIGH")
        layer_summary.append(
            {
                "layer": layer,
                "file_count": len(layer_files),
                "critical_files": critical,
                "high_files": high,
                "sample_files": [
                    str(item.get("relative_path", "")) for item in layer_files[:10]
                ],
                "safety_note": safety_note_for(layer, critical, high),
            }
        )

    architecture_map = {
        "schema": "titan_echo.architecture_map.v1",
        "official_name": "TITAN ECHO",
        "short_name": "ECHO",
        "source": "data/runtime/echo/titan_file_index.json",
        "mapping_mode": "heuristic_read_only",
        "runtime_status": "unknown_not_asserted",
        "top_level_hierarchy": TOP_HIERARCHY,
        "layers": layer_summary,
        "notes": [
            "Layer assignment is heuristic and based on file paths, names, roles, and index metadata.",
            "This map does not assert live runtime status.",
        ],
    }
    return architecture_map, grouped


def most_common_role(items: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        role = str(item.get("probable_role", "unknown"))
        counts[role] += 1
    if not counts:
        return "unknown"
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[0][0]


def build_module_registry(grouped: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    modules = []
    by_module: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for layer, items in grouped.items():
        for item in items:
            by_module[(layer, str(item.get("_echo_module", "unknown")))].append(item)

    for (layer, module_name), items in sorted(by_module.items()):
        critical_files = [
            str(item.get("relative_path", ""))
            for item in items
            if item.get("criticality") == "CRITICAL"
        ]
        high_files = [
            str(item.get("relative_path", ""))
            for item in items
            if item.get("criticality") == "HIGH"
        ]
        modules.append(
            {
                "module_name": module_name,
                "layer": layer,
                "file_count": len(items),
                "critical_files": critical_files,
                "high_files": high_files,
                "probable_role": most_common_role(items),
                "safety_note": safety_note_for(layer, len(critical_files), len(high_files)),
            }
        )

    return {
        "schema": "titan_echo.module_registry.v1",
        "source": "data/runtime/echo/titan_file_index.json",
        "mapping_mode": "heuristic_read_only",
        "runtime_status": "unknown_not_asserted",
        "modules": modules,
    }


def module_candidates(files: list[dict[str, Any]]) -> dict[str, str]:
    candidates: dict[str, str] = {}
    for item in files:
        rel_path = str(item.get("relative_path", ""))
        if not rel_path.endswith(".py"):
            continue
        module_path = rel_path[:-3].replace("/", ".")
        candidates[module_path] = rel_path
        candidates[module_path.split(".")[-1]] = rel_path
    return candidates


def confidence_for(evidence: list[str]) -> str:
    has_import = any(item.startswith("import:") for item in evidence)
    has_known = any(item.startswith("known-link:") for item in evidence)
    if has_import and has_known:
        return "HIGH"
    if has_import:
        return "MEDIUM"
    return "LOW"


def add_edge(
    edges: dict[tuple[str, str], dict[str, Any]],
    source: str,
    target: str,
    evidence: str,
) -> None:
    if source == target:
        return
    key = (source, target)
    if key not in edges:
        edges[key] = {
            "from": source,
            "to": target,
            "relationship": "heuristic_dependency",
            "confidence": "LOW",
            "evidence": [],
        }
    if evidence not in edges[key]["evidence"]:
        edges[key]["evidence"].append(evidence)
    edges[key]["confidence"] = confidence_for(edges[key]["evidence"])


def build_connection_graph(files: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = module_candidates(files)
    by_path = {str(item.get("relative_path", "")): item for item in files}
    edges: dict[tuple[str, str], dict[str, Any]] = {}

    for item in files:
        source = str(item.get("relative_path", ""))
        imports = item.get("detected_imports", [])
        if not isinstance(imports, list):
            continue
        for imported in imports:
            imported_name = str(imported).lstrip(".")
            target = candidates.get(imported_name)
            if target:
                add_edge(edges, source, target, f"import:{imported_name}")
                continue
            root = imported_name.split(".")[0]
            target = candidates.get(root)
            if target:
                add_edge(edges, source, target, f"import-root:{root}")

    known_links = [
        ("titan_echo", "data/runtime/echo", "known-link:ECHO writes memory artifacts"),
        ("dashboard", "runtime", "known-link:dashboard commonly reads runtime state"),
        ("runtime", "data/runtime", "known-link:runtime modules commonly write runtime state"),
        ("scanner", "runtime", "known-link:scanner participates in runtime flow"),
        ("master_brain", "engines", "known-link:Master Brain coordinates specialist engines"),
        ("master_brain", "risk", "known-link:Master Brain depends on risk gating"),
        ("consciousness_core", "memory", "known-link:Consciousness Core uses memory context"),
    ]

    paths = list(by_path)
    for source_key, target_key, evidence in known_links:
        sources = [path for path in paths if source_key in path.lower()][:20]
        targets = [path for path in paths if target_key in path.lower()][:20]
        for source in sources:
            for target in targets[:3]:
                add_edge(edges, source, target, evidence)

    nodes = []
    for item in files:
        nodes.append(
            {
                "id": str(item.get("relative_path", "")),
                "layer": str(item.get("_echo_layer", classify_layer(item))),
                "criticality": str(item.get("criticality", "LOW")),
            }
        )

    return {
        "schema": "titan_echo.connection_graph.v1",
        "source": "data/runtime/echo/titan_file_index.json",
        "mapping_mode": "heuristic_read_only",
        "runtime_status": "unknown_not_asserted",
        "certainty_note": "Connections are inferred from imports and path/name matching; they are not guaranteed runtime call paths.",
        "nodes": nodes,
        "edges": sorted(edges.values(), key=lambda edge: (edge["from"], edge["to"])),
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    files = load_file_index()
    architecture_map, grouped = build_architecture(files)
    module_registry = build_module_registry(grouped)
    connection_graph = build_connection_graph(files)

    write_json(ARCHITECTURE_MAP_PATH, architecture_map)
    write_json(MODULE_REGISTRY_PATH, module_registry)
    write_json(CONNECTION_GRAPH_PATH, connection_graph)

    populated_layers = sum(1 for layer in architecture_map["layers"] if layer["file_count"])
    print("TITAN ECHO architecture mapper: PASSED")
    print(f"Input files mapped: {len(files)}")
    print(f"Populated layers: {populated_layers}")
    print(f"Modules registered: {len(module_registry['modules'])}")
    print(f"Graph edges: {len(connection_graph['edges'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
