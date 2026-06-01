"""Summarize TITAN ECHO observer output into mission-safe issues."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_RUNTIME = REPO_ROOT / "data" / "runtime" / "echo"

LIVE_STATUS_PATH = ECHO_RUNTIME / "live_status.json"
OBSERVATIONS_PATH = ECHO_RUNTIME / "observations.json"
ARCHITECTURE_MAP_PATH = ECHO_RUNTIME / "titan_architecture_map.json"
MODULE_REGISTRY_PATH = ECHO_RUNTIME / "titan_module_registry.json"
CONNECTION_GRAPH_PATH = ECHO_RUNTIME / "titan_connection_graph.json"
OUTPUT_PATH = ECHO_RUNTIME / "observation_summary.json"

IST = timezone(timedelta(hours=5, minutes=30))

FORBIDDEN_ACTIONS = ["restart", "deploy", "broker changes", "risk changes"]


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def normalize_source(source_file: str) -> str:
    return source_file.replace("\\", "/")


def infer_issue_title(source_file: str, severity: str, summaries: list[str]) -> str:
    source = normalize_source(source_file).lower()
    joined = " ".join(summaries).lower()

    if "missing" in joined:
        if "brain_state" in source:
            return "Brain state truth file missing"
        if "runtime_status" in source:
            return "Runtime status truth file missing"
        return "Missing runtime truth files"
    if "scanner" in source:
        return "Scanner status requires review"
    if "worker_health" in source:
        return "Worker health requires review"
    if "runtime_selector" in source:
        return "Runtime selector status requires review"
    if "filter_engine" in source:
        return "Filter engine diagnostics require review"
    if "trade_contract" in source:
        return "Trade contract diagnostics require review"
    if "outcome_tracker" in source:
        return "Outcome tracker diagnostics require review"
    if "truth_gate" in source:
        return "Truth gate status requires review"
    if severity == "CRITICAL":
        return "Runtime health critical"
    if severity == "WARNING":
        return "Runtime health degraded"
    return "Runtime observation noted"


def infer_layer(source_file: str, architecture_map: dict[str, Any]) -> str:
    source = normalize_source(source_file).lower()
    if "scanner" in source or "setup" in source:
        return "Scanner/Setup layer"
    if "runtime" in source or "worker" in source or "daemon" in source:
        return "Runtime/Daemon layer"
    if "filter" in source:
        return "Engine/Filter layer"
    if "trade" in source or "risk" in source or "broker" in source:
        return "Risk/Execution layer"
    if "outcome" in source or "learning" in source or "evolution" in source:
        return "Outcome/Learning/Evolution layer"
    if "brain" in source:
        return "Master Brain layer"
    layers = architecture_map.get("layers", [])
    if isinstance(layers, list) and layers:
        return "Unknown/Unclassified layer"
    return "Unknown/Unclassified layer"


def related_modules_for_layer(layer: str, module_registry: dict[str, Any]) -> list[str]:
    modules = module_registry.get("modules", [])
    names: list[str] = []
    if not isinstance(modules, list):
        return names
    for module in modules:
        if not isinstance(module, dict):
            continue
        if module.get("layer") == layer:
            name = str(module.get("module_name", "unknown"))
            if name not in names:
                names.append(name)
        if len(names) >= 10:
            break
    return names


def edge_evidence_for_source(source_file: str, connection_graph: dict[str, Any]) -> list[str]:
    source_key = Path(normalize_source(source_file)).stem.lower()
    edges = connection_graph.get("edges", [])
    evidence: list[str] = []
    if not isinstance(edges, list):
        return evidence
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        from_path = str(edge.get("from", "")).lower()
        to_path = str(edge.get("to", "")).lower()
        if source_key and (source_key in from_path or source_key in to_path):
            proof = edge.get("evidence", [])
            if isinstance(proof, list):
                evidence.extend(str(item) for item in proof[:3])
        if len(evidence) >= 10:
            break
    return evidence


def group_top_issues(
    observations: list[dict[str, Any]],
    architecture_map: dict[str, Any],
    module_registry: dict[str, Any],
    connection_graph: dict[str, Any],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in observations:
        severity = str(item.get("severity", "INFO"))
        if severity not in {"CRITICAL", "WARNING"}:
            continue
        source_file = normalize_source(str(item.get("source_file", "unknown")))
        grouped[(source_file, severity)].append(item)

    issues = []
    severity_rank = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    for (source_file, severity), items in grouped.items():
        summaries = [str(item.get("summary", "")) for item in items]
        evidence = []
        for item in items:
            raw = item.get("evidence", [])
            if isinstance(raw, list):
                evidence.extend(str(value) for value in raw)
        graph_evidence = edge_evidence_for_source(source_file, connection_graph)
        layer = infer_layer(source_file, architecture_map)
        issues.append(
            {
                "title": infer_issue_title(source_file, severity, summaries),
                "severity": severity,
                "source_file": source_file,
                "count": len(items),
                "affected_layer": layer,
                "related_modules": related_modules_for_layer(layer, module_registry),
                "summary": summaries[0] if summaries else "Observation requires review.",
                "evidence": list(dict.fromkeys([*evidence, *graph_evidence]))[:20],
            }
        )

    return sorted(
        issues,
        key=lambda item: (
            severity_rank.get(str(item["severity"]), 9),
            -int(item["count"]),
            str(item["source_file"]),
        ),
    )


def likely_root_areas(top_issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter(str(issue.get("affected_layer", "Unknown")) for issue in top_issues)
    return [
        {"area": area, "issue_count": count}
        for area, count in counts.most_common()
    ]


def recommended_actions(live_status: dict[str, Any], top_issues: list[dict[str, Any]]) -> list[str]:
    actions = [
        "Run read-only runtime truth audit.",
        "Run ECHO context builder for the highest-severity affected component.",
        "Do not patch until root cause is confirmed.",
    ]

    missing = live_status.get("files_missing", [])
    if isinstance(missing, list) and missing:
        actions.append("Check missing truth file source and writer ownership.")

    if any(issue.get("affected_layer") == "Scanner/Setup layer" for issue in top_issues):
        actions.append("Run scanner/setup diagnostics in read-only mode.")
    if any(issue.get("affected_layer") == "Outcome/Learning/Evolution layer" for issue in top_issues):
        actions.append("Run context builder with outcome_tracker before any write task.")
    if any(issue.get("affected_layer") == "Risk/Execution layer" for issue in top_issues):
        actions.append("Require Ari explicit approval before any broker, risk, or execution change.")

    return list(dict.fromkeys(actions))


def mission_suggestions(top_issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    suggestions = [
        {
            "mission_title": "Read-only runtime truth audit",
            "risk_level": "LOW",
            "requires_ari_approval": True,
            "forbidden_actions": FORBIDDEN_ACTIONS,
        }
    ]
    layers = {str(issue.get("affected_layer", "")) for issue in top_issues}
    if "Scanner/Setup layer" in layers:
        suggestions.append(
            {
                "mission_title": "Read-only scanner/setup truth audit",
                "risk_level": "LOW",
                "requires_ari_approval": True,
                "forbidden_actions": FORBIDDEN_ACTIONS,
            }
        )
    if "Outcome/Learning/Evolution layer" in layers:
        suggestions.append(
            {
                "mission_title": "Read-only outcome tracker context build",
                "risk_level": "LOW",
                "requires_ari_approval": True,
                "forbidden_actions": FORBIDDEN_ACTIONS,
            }
        )
    if "Risk/Execution layer" in layers:
        suggestions.append(
            {
                "mission_title": "Read-only trade contract and risk boundary audit",
                "risk_level": "CRITICAL",
                "requires_ari_approval": True,
                "forbidden_actions": FORBIDDEN_ACTIONS,
            }
        )
    return suggestions


def confidence(live_status: dict[str, Any], observations: list[dict[str, Any]]) -> str:
    found = live_status.get("files_found", [])
    if isinstance(found, list) and len(found) >= 5 and observations:
        return "HIGH"
    if observations:
        return "MEDIUM"
    return "LOW"


def build_summary() -> dict[str, Any]:
    live_status = load_json(LIVE_STATUS_PATH)
    observation_report = load_json(OBSERVATIONS_PATH)
    architecture_map = load_json(ARCHITECTURE_MAP_PATH)
    module_registry = load_json(MODULE_REGISTRY_PATH)
    connection_graph = load_json(CONNECTION_GRAPH_PATH)

    observations = [
        item
        for item in observation_report.get("observations", [])
        if isinstance(item, dict)
    ]
    top_issues = group_top_issues(
        observations,
        architecture_map,
        module_registry,
        connection_graph,
    )
    affected_layers = sorted(
        {
            str(issue.get("affected_layer"))
            for issue in top_issues
            if issue.get("affected_layer")
        }
    )
    evidence = []
    for issue in top_issues[:10]:
        evidence.extend(str(item) for item in issue.get("evidence", [])[:5])

    return {
        "schema": "titan_echo.observation_summary.v1",
        "timestamp_ist": timestamp_ist(),
        "overall_health": live_status.get("overall_health", "UNKNOWN"),
        "total_observations": len(observations),
        "critical_count": live_status.get("critical_count", 0),
        "warnings_count": live_status.get("warnings_count", 0),
        "top_issues": top_issues,
        "affected_layers": affected_layers,
        "likely_root_areas": likely_root_areas(top_issues),
        "recommended_next_actions": recommended_actions(live_status, top_issues),
        "mission_suggestions": mission_suggestions(top_issues),
        "confidence": confidence(live_status, observations),
        "evidence": list(dict.fromkeys(evidence))[:50],
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    summary = build_summary()
    write_json(OUTPUT_PATH, summary)
    print("TITAN ECHO observation summarizer: PASSED")
    print(f"Overall health: {summary['overall_health']}")
    print(f"Total observations: {summary['total_observations']}")
    print(f"Top issues: {len(summary['top_issues'])}")
    print(f"Recommended actions: {len(summary['recommended_next_actions'])}")
    print(f"Mission suggestions: {len(summary['mission_suggestions'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
