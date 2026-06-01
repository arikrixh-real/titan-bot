"""Read-only mission context builder for TITAN ECHO."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_RUNTIME = REPO_ROOT / "data" / "runtime" / "echo"

FILE_INDEX_PATH = ECHO_RUNTIME / "file_index.json"
ARCHITECTURE_MAP_PATH = ECHO_RUNTIME / "architecture_map.json"
MODULE_REGISTRY_PATH = ECHO_RUNTIME / "module_registry.json"
ENGINE_REGISTRY_PATH = ECHO_RUNTIME / "engine_registry.json"
DANGER_REGISTRY_PATH = ECHO_RUNTIME / "danger_registry.json"
OWNERSHIP_MAP_PATH = ECHO_RUNTIME / "ownership_map.json"
CONNECTION_GRAPH_PATH = ECHO_RUNTIME / "connection_graph.json"
KNOWN_RISKS_PATH = ECHO_RUNTIME / "titan_known_risks.json"
OUTPUT_PATH = ECHO_RUNTIME / "echo_context_report.json"

LEGACY_PATHS = {
    FILE_INDEX_PATH: ECHO_RUNTIME / "titan_file_index.json",
    ARCHITECTURE_MAP_PATH: ECHO_RUNTIME / "titan_architecture_map.json",
    MODULE_REGISTRY_PATH: ECHO_RUNTIME / "titan_module_registry.json",
    CONNECTION_GRAPH_PATH: ECHO_RUNTIME / "titan_connection_graph.json",
}

CRITICAL_TERMS = {
    "broker",
    "order",
    "execution",
    "risk",
    "master_brain",
    "unified_brain",
    "consciousness",
    "consciousness_core",
    "scanner",
    "daemon",
}

REQUIRED_FIELDS = [
    "issue_keyword",
    "timestamp",
    "matched_files",
    "matched_layers",
    "related_modules",
    "probable_affected_systems",
    "criticality_summary",
    "forbidden_files",
    "allowed_safe_scope",
    "required_tests",
    "safety_notes",
    "mission_prompt_guidance",
    "confidence",
    "evidence",
]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists() and path in LEGACY_PATHS:
        path = LEGACY_PATHS[path]
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return load_json(path)


def normalize_keyword(keyword: str | None) -> str:
    if not keyword:
        return "general"
    return keyword.strip().lower().replace("\\", "/") or "general"


def keyword_tokens(keyword: str) -> list[str]:
    if keyword == "general":
        return []
    raw = keyword.replace("-", "_").replace("/", "_").replace(".", "_")
    return [part for part in raw.split("_") if part]


def item_search_text(item: dict[str, Any]) -> str:
    imports = item.get("detected_imports", [])
    functions = item.get("detected_functions", [])
    classes = item.get("detected_classes", [])
    values = [
        item.get("relative_path", ""),
        item.get("probable_role", ""),
        item.get("criticality", ""),
        " ".join(str(value) for value in imports if isinstance(value, str)),
        " ".join(str(value) for value in functions if isinstance(value, str)),
        " ".join(str(value) for value in classes if isinstance(value, str)),
    ]
    return " ".join(str(value).lower() for value in values)


def matches_keyword(item: dict[str, Any], keyword: str, tokens: list[str]) -> bool:
    if keyword == "general":
        return True
    text = item_search_text(item)
    if keyword in text:
        return True
    return bool(tokens and all(token in text for token in tokens))


def layer_for_file(path: str, architecture_map: dict[str, Any]) -> str:
    layers = architecture_map.get("layers", [])
    if not isinstance(layers, list):
        return "Unknown/Unclassified layer"
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        samples = layer.get("sample_files", [])
        if isinstance(samples, list) and path in samples:
            return str(layer.get("layer", "Unknown/Unclassified layer"))
    return "Unknown/Unclassified layer"


def module_for_file(path: str, module_registry: dict[str, Any]) -> list[dict[str, Any]]:
    modules = module_registry.get("modules", [])
    matched = []
    if not isinstance(modules, list):
        return matched
    for module in modules:
        if not isinstance(module, dict):
            continue
        critical_files = module.get("critical_files", [])
        high_files = module.get("high_files", [])
        locations = module.get("locations", [])
        module_name = str(module.get("module_name", ""))
        if (
            path in critical_files
            or path in high_files
            or path in locations
            or path.startswith(f"{module_name}/")
            or Path(path).stem == module_name
        ):
            matched.append(module)
    return matched


def infer_layer_from_path(path: str) -> str:
    key = path.lower()
    if key.startswith("titan_echo/"):
        return "ECHO layer"
    if "unified_brain" in key:
        return "Unified Brain layer"
    if key.startswith("consciousness_core/") or "consciousness" in key:
        return "Consciousness Core layer"
    if "master_brain" in key:
        return "Master Brain layer"
    if "risk" in key or "broker" in key or "order" in key or "execution" in key:
        return "Risk/Execution layer"
    if key.startswith("runtime_") or "daemon" in key:
        return "Runtime/Daemon layer"
    if "scanner" in key or "setup" in key:
        return "Scanner/Setup layer"
    if "engine" in key or "filter" in key or key.startswith("engines/"):
        return "Engine/Filter layer"
    if "outcome" in key or "learning" in key or "evolution" in key:
        return "Outcome/Learning/Evolution layer"
    if "news" in key or "research" in key or "memory" in key:
        return "News/Research/Memory layer"
    if key.startswith("data/") or "supabase" in key:
        return "Data/Supabase layer"
    if "dashboard" in key or "report" in key:
        return "Dashboard/Reporting layer"
    if key.startswith("tools/") or "diagnostic" in key or key.startswith("tests/"):
        return "Tools/Diagnostics layer"
    return "Unknown/Unclassified layer"


def collect_related_edges(
    matched_paths: set[str],
    connection_graph: dict[str, Any],
    limit: int = 60,
) -> tuple[list[dict[str, Any]], list[str]]:
    edges = connection_graph.get("edges", [])
    related = []
    evidence = []
    if not isinstance(edges, list):
        return related, evidence
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("from", ""))
        target = str(edge.get("to", ""))
        if source not in matched_paths and target not in matched_paths:
            continue
        related.append(edge)
        proof = edge.get("evidence", [])
        if isinstance(proof, list):
            for item in proof:
                evidence.append(f"graph:{source}->{target}:{item}")
        if len(related) >= limit:
            break
    return related, evidence


def summarize_criticality(files: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    for item in files:
        criticality = str(item.get("criticality", "LOW"))
        counts[criticality] = counts.get(criticality, 0) + 1
    return counts


def forbidden_files(files: list[dict[str, Any]]) -> list[str]:
    forbidden = []
    for item in files:
        path = str(item.get("relative_path", ""))
        criticality = str(item.get("criticality", "LOW"))
        layer = infer_layer_from_path(path)
        if criticality == "CRITICAL" or layer in {
            "Unified Brain layer",
            "Consciousness Core layer",
            "Master Brain layer",
            "Risk/Execution layer",
            "Scanner/Setup layer",
            "Runtime/Daemon layer",
        }:
            forbidden.append(path)
    return sorted(set(forbidden))


def required_tests(keyword: str, matched_paths: set[str], files: list[dict[str, Any]]) -> list[str]:
    search_text = " ".join([keyword, *matched_paths]).lower()
    suggestions: list[str] = []
    available = {str(item.get("relative_path", "")) for item in files}

    if "outcome" in search_text or "trade" in search_text or "result" in search_text:
        suggestions.append("tools/trade_pipeline_check.py")
    if "scanner" in search_text or "setup" in search_text:
        suggestions.append("truth_gate_check.py")
        suggestions.append("scanner diagnostics")
    if "runtime" in search_text or "daemon" in search_text:
        suggestions.append("runtime_status.py")
    if "learning" in search_text or "evolution" in search_text:
        diagnostics = sorted(
            path
            for path in available
            if ("learning" in path.lower() or "evolution" in path.lower())
            and ("diagnostic" in path.lower() or path.startswith("tools/"))
        )
        suggestions.extend(diagnostics[:5] or ["learning/evolution diagnostics if present"])
    if (
        "broker" in search_text
        or "risk" in search_text
        or "execution" in search_text
        or "order" in search_text
    ):
        suggestions.append("CRITICAL: require Ari explicit approval before any write task")
    if "consciousness" in search_text:
        suggestions.append("CRITICAL: perform read-only Consciousness Core audit first")
    if "unified_brain" in search_text or "unified brain" in search_text:
        suggestions.append("CRITICAL: perform architecture audit before any write task")

    return list(dict.fromkeys(suggestions or ["Run focused checks for matched modules before any change."]))


def confidence_level(matched: list[dict[str, Any]], edges: list[dict[str, Any]], keyword: str) -> str:
    if keyword == "general":
        return "MEDIUM"
    if len(matched) >= 5 and edges:
        return "HIGH"
    if matched:
        return "MEDIUM"
    return "LOW"


def probable_systems(layers: list[str], modules: list[dict[str, Any]]) -> list[str]:
    systems = set(layers)
    for module in modules:
        role = str(module.get("probable_role", ""))
        if role and role != "unknown":
            systems.add(role)
    return sorted(systems)


def safe_scope(keyword: str, criticality: dict[str, int]) -> list[str]:
    scope = [
        "Read ECHO indexes and generated maps.",
        "Inspect matched files before proposing changes.",
        "Prefer documentation, tests, or ECHO-only planning artifacts until approval is explicit.",
    ]
    if criticality.get("CRITICAL", 0):
        scope.append("Do not edit CRITICAL files without explicit Ari approval.")
    if keyword == "general":
        scope.append("Use this report for orientation only; narrow the issue keyword before a write task.")
    return scope


def safety_notes(keyword: str, criticality: dict[str, int], risks: dict[str, Any]) -> list[str]:
    notes = [
        "This report is read-only context and does not assert live runtime status.",
        "Do not restart TITAN, deploy, push GitHub, or edit protected runtime logic from this context step.",
    ]
    if criticality.get("CRITICAL", 0):
        notes.append("Matched CRITICAL files are forbidden for modification unless Ari explicitly approves.")
    if keyword in CRITICAL_TERMS or any(term in keyword for term in CRITICAL_TERMS):
        notes.append("Issue keyword touches protected systems; require Ari approval before Codex write task.")
    risk_items = risks.get("risks", [])
    if isinstance(risk_items, list) and risk_items:
        notes.append("Known risk entries exist in titan_known_risks.json; review before task creation.")
    return notes


def prompt_guidance(keyword: str, report: dict[str, Any]) -> list[str]:
    return [
        f"Use issue keyword: {keyword}.",
        "Tell Codex to inspect matched files and related modules before editing.",
        "Tell Codex to respect forbidden_files and allowed_safe_scope exactly.",
        "Tell Codex to run or justify required_tests before completion.",
        "Tell Codex not to restart TITAN, deploy, push, or touch protected systems without explicit Ari approval.",
    ]


def build_report(keyword: str) -> dict[str, Any]:
    file_index = load_json(FILE_INDEX_PATH)
    architecture_map = load_json(ARCHITECTURE_MAP_PATH)
    module_registry = load_json(MODULE_REGISTRY_PATH)
    connection_graph = load_json(CONNECTION_GRAPH_PATH)
    known_risks = load_optional_json(KNOWN_RISKS_PATH)
    engine_registry = load_optional_json(ENGINE_REGISTRY_PATH)
    danger_registry = load_optional_json(DANGER_REGISTRY_PATH)
    ownership_map = load_optional_json(OWNERSHIP_MAP_PATH)

    files = [item for item in file_index.get("files", []) if isinstance(item, dict)]
    tokens = keyword_tokens(keyword)
    matched = [item for item in files if matches_keyword(item, keyword, tokens)]
    if keyword == "general":
        matched = files[:100]

    matched_paths = {str(item.get("relative_path", "")) for item in matched}
    related_edges, graph_evidence = collect_related_edges(matched_paths, connection_graph)

    modules_by_name: dict[str, dict[str, Any]] = {}
    for path in matched_paths:
        for module in module_for_file(path, module_registry):
            name = f"{module.get('layer')}::{module.get('module_name')}"
            modules_by_name[name] = module

    layers = sorted({infer_layer_from_path(path) for path in matched_paths})
    for edge in related_edges:
        source = str(edge.get("from", ""))
        target = str(edge.get("to", ""))
        if source:
            layers.append(infer_layer_from_path(source))
        if target:
            layers.append(infer_layer_from_path(target))
    layers = sorted(set(layers))

    criticality = summarize_criticality(matched)
    evidence = [
        f"file-match:{path}" for path in sorted(matched_paths)[:50]
    ] + graph_evidence[:50]

    report: dict[str, Any] = {
        "schema": "titan_echo.context_report.v1",
        "issue_keyword": keyword,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "matched_files": [
            {
                "relative_path": str(item.get("relative_path", "")),
                "criticality": str(item.get("criticality", "LOW")),
                "probable_role": str(item.get("probable_role", "unknown")),
                "layer": infer_layer_from_path(str(item.get("relative_path", ""))),
                "modify_safety_note": str(item.get("modify_safety_note", "")),
            }
            for item in matched[:100]
        ],
        "matched_layers": layers,
        "related_modules": list(modules_by_name.values())[:50],
        "knowledge_sources": {
            "file_index": str(FILE_INDEX_PATH.relative_to(REPO_ROOT)),
            "module_registry": str(MODULE_REGISTRY_PATH.relative_to(REPO_ROOT)),
            "engine_registry": str(ENGINE_REGISTRY_PATH.relative_to(REPO_ROOT)),
            "architecture_map": str(ARCHITECTURE_MAP_PATH.relative_to(REPO_ROOT)),
            "danger_registry": str(DANGER_REGISTRY_PATH.relative_to(REPO_ROOT)),
            "ownership_map": str(OWNERSHIP_MAP_PATH.relative_to(REPO_ROOT)),
            "connection_graph": str(CONNECTION_GRAPH_PATH.relative_to(REPO_ROOT)),
        },
        "engine_registry_summary": engine_registry.get("summary", {}),
        "danger_registry_summary": danger_registry.get("summary", {}),
        "ownership_map_summary": ownership_map.get("summary", {}),
        "probable_affected_systems": probable_systems(layers, list(modules_by_name.values())),
        "criticality_summary": criticality,
        "forbidden_files": forbidden_files(matched)[:100],
        "allowed_safe_scope": safe_scope(keyword, criticality),
        "required_tests": required_tests(keyword, matched_paths, files),
        "safety_notes": safety_notes(keyword, criticality, known_risks),
        "mission_prompt_guidance": [],
        "confidence": confidence_level(matched, related_edges, keyword),
        "evidence": evidence,
    }
    report["mission_prompt_guidance"] = prompt_guidance(keyword, report)
    return report


def write_report(report: dict[str, Any]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    keyword = normalize_keyword(args[0] if args else None)
    report = build_report(keyword)
    write_report(report)
    print("TITAN ECHO context builder: PASSED")
    print(f"Issue keyword: {keyword}")
    print(f"Matched files: {len(report['matched_files'])}")
    print(f"Matched layers: {len(report['matched_layers'])}")
    print(f"Confidence: {report['confidence']}")
    print("Output: data/runtime/echo/echo_context_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
