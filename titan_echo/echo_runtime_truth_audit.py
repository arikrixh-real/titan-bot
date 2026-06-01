"""Read-only runtime truth audit for TITAN ECHO."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
ECHO_RUNTIME = RUNTIME_DIR / "echo"

LIVE_STATUS_PATH = ECHO_RUNTIME / "live_status.json"
OBSERVATIONS_PATH = ECHO_RUNTIME / "observations.json"
OBSERVATION_SUMMARY_PATH = ECHO_RUNTIME / "observation_summary.json"
FILE_INDEX_PATH = ECHO_RUNTIME / "titan_file_index.json"
ARCHITECTURE_MAP_PATH = ECHO_RUNTIME / "titan_architecture_map.json"
MODULE_REGISTRY_PATH = ECHO_RUNTIME / "titan_module_registry.json"
CONNECTION_GRAPH_PATH = ECHO_RUNTIME / "titan_connection_graph.json"
OUTPUT_PATH = ECHO_RUNTIME / "runtime_truth_audit.json"

IST = timezone(timedelta(hours=5, minutes=30))

RUNTIME_TRUTH_FILES = [
    "filter_engine_diagnostics.json",
    "truth_gate_status.json",
    "worker_health.json",
    "brain_state.json",
    "runtime_status.json",
    "scanner_status.json",
    "trade_contract_diagnostics.json",
    "outcome_tracker_diagnostics.json",
    "runtime_selector_status.json",
]

FORBIDDEN_ACTIONS = [
    "restart TITAN",
    "deploy",
    "modify broker execution",
    "modify risk logic",
    "modify scanner pipeline",
    "push GitHub",
]

STALE_HOURS = 24


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def try_load_runtime_json(path: Path) -> tuple[dict[str, Any] | list[Any] | None, str | None]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError as exc:
        return None, f"malformed_json_line_{exc.lineno}"
    except OSError as exc:
        return None, f"read_error_{exc.__class__.__name__}"
    if not isinstance(data, (dict, list)):
        return None, "json_root_not_object_or_list"
    return data, None


def runtime_source(filename: str) -> str:
    return f"data/runtime/{filename}"


def infer_layer(source_file: str) -> str:
    key = source_file.lower()
    if "filter" in key:
        return "Engine/Filter layer"
    if "truth_gate" in key or "scanner" in key:
        return "Scanner/Setup layer"
    if "worker" in key or "runtime" in key:
        return "Runtime/Daemon layer"
    if "trade" in key or "risk" in key or "broker" in key:
        return "Risk/Execution layer"
    if "outcome" in key:
        return "Outcome/Learning/Evolution layer"
    if "brain" in key:
        return "Master Brain layer"
    return "Unknown/Unclassified layer"


def owner_keywords(filename: str) -> list[str]:
    key = filename.lower()
    if "filter_engine" in key:
        return ["filter_diagnostics", "filter_engine", "scanner_filter"]
    if "truth_gate" in key:
        return ["truth_gate", "truth", "gate"]
    if "worker_health" in key:
        return ["worker_health", "heartbeat", "runtime_continuous_workers"]
    if "brain_state" in key:
        return ["brain_state", "runtime_brain", "master_brain", "unified_brain"]
    if "runtime_status" in key:
        return ["runtime_status", "runtime_health", "runtime_supervisor"]
    if "scanner_status" in key:
        return ["scanner_status", "runtime_scanner", "scanner"]
    if "trade_contract" in key:
        return ["trade_contract", "trade_pipeline", "contract"]
    if "outcome_tracker" in key:
        return ["outcome_tracker", "trade_outcome"]
    if "runtime_selector" in key:
        return ["runtime_selector", "runtime_mode"]
    return [Path(filename).stem]


def likely_writer_owners(filename: str, file_index: dict[str, Any]) -> dict[str, Any]:
    files = [item for item in file_index.get("files", []) if isinstance(item, dict)]
    keywords = owner_keywords(filename)
    matches = []
    for item in files:
        path = str(item.get("relative_path", ""))
        path_key = path.lower()
        if any(keyword in path_key for keyword in keywords):
            matches.append(
                {
                    "relative_path": path,
                    "criticality": item.get("criticality", "LOW"),
                    "probable_role": item.get("probable_role", "unknown"),
                }
            )
        if len(matches) >= 8:
            break

    fallback = {
        "filter_engine_diagnostics.json": "tools/filter_diagnostics_check.py or filter diagnostics runtime",
        "truth_gate_status.json": "truth gate/check tools",
        "worker_health.json": "runtime worker health/heartbeat modules",
        "brain_state.json": "brain/runtime brain state writer",
        "runtime_status.json": "runtime status/health modules",
        "scanner_status.json": "runtime scanner/scanner status writer",
        "trade_contract_diagnostics.json": "trade contract diagnostics tools",
        "outcome_tracker_diagnostics.json": "outcome tracker diagnostics writer",
        "runtime_selector_status.json": "runtime selector/mode resolver",
    }.get(filename, "unknown writer")

    return {
        "truth_file": runtime_source(filename),
        "heuristic_owner": fallback,
        "matched_owner_candidates": matches,
        "confidence": "MEDIUM" if matches else "LOW",
    }


def root_area_for(filename: str, severity: str, summary: str) -> str:
    key = filename.lower()
    text = summary.lower()
    if "filter_engine" in key:
        return "filter diagnostics failing"
    if "truth_gate" in key:
        return "truth gate failing/degraded"
    if "worker_health" in key:
        return "worker health stale/degraded"
    if "brain_state" in key or "missing" in text and "brain" in key:
        return "missing brain state truth"
    if "scanner" in key or "runtime" in key:
        return "scanner/runtime unknown"
    if "outcome_tracker" in key:
        return "outcome tracker unknown"
    if severity == "CRITICAL":
        return "runtime truth critical"
    return "runtime truth warning"


def collect_observation_sources(observations: list[dict[str, Any]], severity: str) -> list[dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for item in observations:
        if item.get("severity") != severity:
            continue
        source = str(item.get("source_file", "unknown")).replace("\\", "/")
        record = sources.setdefault(
            source,
            {
                "source_file": source,
                "count": 0,
                "summaries": [],
                "evidence": [],
                "affected_layer": infer_layer(source),
            },
        )
        record["count"] += 1
        summary = str(item.get("summary", ""))
        if summary and summary not in record["summaries"]:
            record["summaries"].append(summary)
        evidence = item.get("evidence", [])
        if isinstance(evidence, list):
            for value in evidence:
                text = str(value)
                if text not in record["evidence"]:
                    record["evidence"].append(text)
    return sorted(sources.values(), key=lambda row: (-int(row["count"]), row["source_file"]))


def inspect_runtime_files() -> tuple[list[dict[str, Any]], list[str], list[dict[str, str]], list[dict[str, Any]]]:
    inspected = []
    missing = []
    malformed = []
    stale_or_unknown = []
    now = datetime.now()

    for filename in RUNTIME_TRUTH_FILES:
        path = RUNTIME_DIR / filename
        source = runtime_source(filename)
        data, error = try_load_runtime_json(path)
        if error == "missing":
            missing.append(source)
            inspected.append({"source_file": source, "present": False, "status": "missing"})
            continue
        if error:
            malformed.append({"source_file": source, "error": error})
            inspected.append({"source_file": source, "present": True, "status": "malformed"})
            continue

        age_hours = None
        if path.exists():
            modified = datetime.fromtimestamp(path.stat().st_mtime)
            age_hours = round((now - modified).total_seconds() / 3600, 2)
        status = "present"
        if age_hours is not None and age_hours > STALE_HOURS:
            status = "stale"
            stale_or_unknown.append(
                {
                    "source_file": source,
                    "reason": f"last modified more than {STALE_HOURS} hours ago",
                    "age_hours": age_hours,
                }
            )
        elif data is None:
            status = "unknown"
            stale_or_unknown.append({"source_file": source, "reason": "no readable payload"})

        inspected.append(
            {
                "source_file": source,
                "present": True,
                "status": status,
                "age_hours": age_hours,
            }
        )

    return inspected, missing, malformed, stale_or_unknown


def safe_next_actions(root_areas: list[dict[str, Any]], missing_files: list[str]) -> list[str]:
    actions = [
        "Run ECHO context builder for filter_engine_diagnostics.",
        "Run existing read-only truth checks before any patch.",
        "Do not patch until writer ownership is confirmed.",
    ]
    if missing_files:
        actions.append("Inspect writer ownership for missing brain_state.json and runtime_status.json.")
    names = {str(item["root_area"]) for item in root_areas}
    if "truth gate failing/degraded" in names:
        actions.append("Run context builder for truth_gate_status.")
    if "worker health stale/degraded" in names:
        actions.append("Run read-only worker health and heartbeat audit.")
    if "outcome tracker unknown" in names:
        actions.append("Run context builder for outcome_tracker_diagnostics.")
    return list(dict.fromkeys(actions))


def build_audit() -> dict[str, Any]:
    live_status = load_json(LIVE_STATUS_PATH)
    observation_report = load_json(OBSERVATIONS_PATH)
    observation_summary = load_json(OBSERVATION_SUMMARY_PATH)
    file_index = load_json(FILE_INDEX_PATH)
    load_json(ARCHITECTURE_MAP_PATH)
    load_json(MODULE_REGISTRY_PATH)
    load_json(CONNECTION_GRAPH_PATH)

    observations = [item for item in observation_report.get("observations", []) if isinstance(item, dict)]
    files_inspected, missing_files, malformed_files, stale_or_unknown = inspect_runtime_files()
    critical_sources = collect_observation_sources(observations, "CRITICAL")
    warning_sources = collect_observation_sources(observations, "WARNING")

    affected_layers = sorted(
        {
            infer_layer(str(source.get("source_file", "")))
            for source in [*critical_sources, *warning_sources]
        }
    )

    owners = [
        likely_writer_owners(filename, file_index)
        for filename in RUNTIME_TRUTH_FILES
    ]

    root_counts: dict[str, dict[str, Any]] = {}
    for source in [*critical_sources, *warning_sources]:
        filename = Path(str(source["source_file"])).name
        summaries = source.get("summaries", [])
        summary = summaries[0] if summaries else ""
        root_area = root_area_for(filename, str(source.get("severity", "")), str(summary))
        entry = root_counts.setdefault(
            root_area,
            {
                "root_area": root_area,
                "count": 0,
                "sources": [],
                "severity": "WARNING",
            },
        )
        entry["count"] += int(source.get("count", 1))
        if source["source_file"] not in entry["sources"]:
            entry["sources"].append(source["source_file"])
        if any(cs["source_file"] == source["source_file"] for cs in critical_sources):
            entry["severity"] = "CRITICAL"
    for missing in missing_files:
        root_area = root_area_for(Path(missing).name, "WARNING", "missing")
        entry = root_counts.setdefault(
            root_area,
            {"root_area": root_area, "count": 0, "sources": [], "severity": "WARNING"},
        )
        entry["count"] += 1
        if missing not in entry["sources"]:
            entry["sources"].append(missing)

    root_area_candidates = sorted(
        root_counts.values(),
        key=lambda item: (0 if item["severity"] == "CRITICAL" else 1, -int(item["count"]), item["root_area"]),
    )

    evidence = []
    for source in [*critical_sources, *warning_sources]:
        evidence.extend(str(item) for item in source.get("evidence", [])[:5])

    confidence = "HIGH" if critical_sources and files_inspected else "MEDIUM" if files_inspected else "LOW"

    return {
        "schema": "titan_echo.runtime_truth_audit.v1",
        "timestamp_ist": timestamp_ist(),
        "overall_health_from_echo": live_status.get("overall_health", "UNKNOWN"),
        "files_inspected": files_inspected,
        "missing_files": missing_files,
        "malformed_files": malformed_files,
        "stale_or_unknown_files": stale_or_unknown,
        "critical_sources": critical_sources,
        "warning_sources": warning_sources,
        "affected_layers": affected_layers,
        "likely_writer_owners": owners,
        "root_area_candidates": root_area_candidates,
        "evidence": list(dict.fromkeys([*evidence, *observation_summary.get("evidence", [])]))[:80],
        "safe_next_actions": safe_next_actions(root_area_candidates, missing_files),
        "forbidden_actions": FORBIDDEN_ACTIONS,
        "confidence": confidence,
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    audit = build_audit()
    write_json(OUTPUT_PATH, audit)
    print("TITAN ECHO runtime truth audit: PASSED")
    print(f"Overall health from ECHO: {audit['overall_health_from_echo']}")
    print(f"Files inspected: {len(audit['files_inspected'])}")
    print(f"Missing files: {len(audit['missing_files'])}")
    print(f"Critical sources: {len(audit['critical_sources'])}")
    print(f"Warning sources: {len(audit['warning_sources'])}")
    print(f"Root areas: {len(audit['root_area_candidates'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
