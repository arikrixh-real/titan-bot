"""Read-only duplicate and missing writer audit for TITAN truth files."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_RUNTIME = REPO_ROOT / "data" / "runtime" / "echo"

WRITER_OWNERSHIP_PATH = ECHO_RUNTIME / "writer_ownership_audit.json"
FILE_INDEX_PATH = ECHO_RUNTIME / "titan_file_index.json"
CONNECTION_GRAPH_PATH = ECHO_RUNTIME / "titan_connection_graph.json"
MODULE_REGISTRY_PATH = ECHO_RUNTIME / "titan_module_registry.json"
OUTPUT_PATH = ECHO_RUNTIME / "duplicate_writer_audit.json"

IST = timezone(timedelta(hours=5, minutes=30))

CLASSIFICATIONS = {
    "CONFIRMED_SINGLE_WRITER",
    "LIKELY_SINGLE_WRITER",
    "MULTIPLE_WRITER_RISK",
    "READER_ONLY_REFERENCES",
    "NO_WRITER_FOUND",
    "UNKNOWN",
}

TRUTH_FILE_NAMES = {
    "brain_state.json",
    "runtime_status.json",
    "filter_engine_diagnostics.json",
    "truth_gate_status.json",
    "worker_health.json",
    "scanner_status.json",
    "outcome_tracker_diagnostics.json",
    "trade_contract_diagnostics.json",
}


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def strong_writers(writers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    strong = []
    for writer in writers:
        signals = writer.get("signals", [])
        if isinstance(signals, list) and "write_signal" in signals:
            strong.append(writer)
    return sorted(strong, key=lambda item: (-int(item.get("score", 0)), str(item.get("relative_path", ""))))


def weak_writers(writers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    weak = []
    for writer in writers:
        signals = writer.get("signals", [])
        if isinstance(signals, list) and "write_signal" not in signals:
            weak.append(writer)
    return sorted(weak, key=lambda item: (-int(item.get("score", 0)), str(item.get("relative_path", ""))))


def reader_only_candidates(readers: list[dict[str, Any]], writer_paths: set[str]) -> list[dict[str, Any]]:
    result = []
    for reader in readers:
        path = str(reader.get("relative_path", ""))
        if path not in writer_paths:
            result.append(reader)
    return sorted(result, key=lambda item: (-int(item.get("score", 0)), str(item.get("relative_path", ""))))[:12]


def has_exact_reference(candidate: dict[str, Any]) -> bool:
    signals = candidate.get("signals", [])
    return isinstance(signals, list) and any(str(signal).startswith("exact_reference:") for signal in signals)


def classify_record(record: dict[str, Any]) -> tuple[str, str, bool]:
    writers = [item for item in record.get("likely_writers", []) if isinstance(item, dict)]
    readers = [item for item in record.get("likely_readers", []) if isinstance(item, dict)]
    strong = strong_writers(writers)
    weak = weak_writers(writers)

    if len(strong) == 1 and has_exact_reference(strong[0]) and int(strong[0].get("score", 0)) >= 9:
        return "CONFIRMED_SINGLE_WRITER", "HIGH", False
    if len(strong) == 1:
        return "LIKELY_SINGLE_WRITER", "MEDIUM", False
    if len(strong) > 1:
        return "MULTIPLE_WRITER_RISK", "HIGH", True
    if not strong and weak:
        if readers:
            return "READER_ONLY_REFERENCES", "MEDIUM", False
        return "UNKNOWN", "LOW", False
    if not writers and readers:
        return "READER_ONLY_REFERENCES", "MEDIUM", False
    if not writers:
        return "NO_WRITER_FOUND", "LOW", False
    return "UNKNOWN", "LOW", False


def recommendation_for(classification: str, truth_file: str) -> str:
    name = Path(truth_file).name
    if classification == "CONFIRMED_SINGLE_WRITER":
        return f"Inspect exact writer function for {name}; keep changes read-only until Ari approves."
    if classification == "LIKELY_SINGLE_WRITER":
        return f"Inspect runtime owner module for {name} and confirm the exact write path."
    if classification == "MULTIPLE_WRITER_RISK":
        return f"Inspect competing writer functions for {name}; do not create a new writer."
    if classification == "READER_ONLY_REFERENCES":
        return f"Confirm whether {name} has a stale or missing writer; do not patch until ownership is confirmed."
    if classification == "NO_WRITER_FOUND":
        return f"Identify intended owner for {name}; add proof writer only after Ari approval."
    return f"Run a narrower read-only ownership audit for {name}."


def compact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "relative_path": candidate.get("relative_path", ""),
        "score": candidate.get("score", 0),
        "signals": candidate.get("signals", []),
        "criticality": candidate.get("criticality", "LOW"),
        "probable_role": candidate.get("probable_role", "unknown"),
    }


def build_truth_file_result(record: dict[str, Any]) -> dict[str, Any]:
    truth_file = str(record.get("truth_file", ""))
    writers = [item for item in record.get("likely_writers", []) if isinstance(item, dict)]
    readers = [item for item in record.get("likely_readers", []) if isinstance(item, dict)]
    strong = strong_writers(writers)
    weak = weak_writers(writers)
    classification, confidence, duplicate_risk = classify_record(record)

    likely_writer = None
    if strong:
        likely_writer = compact_candidate(strong[0])
    elif weak and classification != "READER_ONLY_REFERENCES":
        likely_writer = compact_candidate(weak[0])

    writer_paths = {str(item.get("relative_path", "")) for item in [*strong, *weak]}
    competing = [compact_candidate(item) for item in strong[1:]]
    if classification == "MULTIPLE_WRITER_RISK" and not competing:
        competing = [compact_candidate(item) for item in writers[1:]]

    reader_only = [compact_candidate(item) for item in reader_only_candidates(readers, writer_paths)]
    evidence = list(record.get("evidence", [])) if isinstance(record.get("evidence"), list) else []
    if strong:
        evidence.append(f"strong_writer_count:{len(strong)}")
    if weak:
        evidence.append(f"weak_writer_candidate_count:{len(weak)}")
    if readers:
        evidence.append(f"reader_candidate_count:{len(readers)}")

    return {
        "truth_file": truth_file,
        "classification": classification,
        "likely_writer": likely_writer,
        "competing_writers": competing[:10],
        "readers": reader_only,
        "confidence": confidence,
        "duplicate_writer_risk": duplicate_risk,
        "ownership_recommendation": recommendation_for(classification, truth_file),
        "evidence": list(dict.fromkeys(str(item) for item in evidence))[:30],
    }


def highest_risk_files(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rank = {
        "MULTIPLE_WRITER_RISK": 0,
        "NO_WRITER_FOUND": 1,
        "READER_ONLY_REFERENCES": 2,
        "UNKNOWN": 3,
        "LIKELY_SINGLE_WRITER": 4,
        "CONFIRMED_SINGLE_WRITER": 5,
    }
    ordered = sorted(results, key=lambda item: (rank.get(str(item["classification"]), 9), str(item["truth_file"])))
    return [
        {
            "truth_file": item["truth_file"],
            "classification": item["classification"],
            "confidence": item["confidence"],
            "duplicate_writer_risk": item["duplicate_writer_risk"],
        }
        for item in ordered
    ]


def recommended_next_steps(results: list[dict[str, Any]]) -> list[str]:
    steps = [
        "Inspect exact writer functions for any confirmed or likely writer before proposing changes.",
        "Inspect runtime owner modules for reader-only truth files.",
        "Do not create a new writer until ownership is confirmed.",
        "Do not patch until ownership is confirmed.",
    ]
    if any(item["classification"] == "MULTIPLE_WRITER_RISK" for item in results):
        steps.append("Audit competing writer paths and decide one authoritative owner in a separate Ari-approved mission.")
    if any(item["classification"] == "NO_WRITER_FOUND" for item in results):
        steps.append("Identify intended owner for no-writer files before adding any proof writer.")
    if any(item["classification"] == "READER_ONLY_REFERENCES" for item in results):
        steps.append("Separate reader-only references from stale writer paths with a focused read-only inspection.")
    return steps


def validate_inputs() -> None:
    load_json(FILE_INDEX_PATH)
    load_json(CONNECTION_GRAPH_PATH)
    load_json(MODULE_REGISTRY_PATH)


def build_audit() -> dict[str, Any]:
    validate_inputs()
    ownership = load_json(WRITER_OWNERSHIP_PATH)
    records = [item for item in ownership.get("truth_files", []) if isinstance(item, dict)]
    filtered = [
        item
        for item in records
        if Path(str(item.get("truth_file", ""))).name in TRUTH_FILE_NAMES
    ]
    results = [build_truth_file_result(item) for item in filtered]
    counts = Counter(str(item["classification"]) for item in results)

    return {
        "schema": "titan_echo.duplicate_writer_audit.v1",
        "timestamp_ist": timestamp_ist(),
        "files_audited": len(results),
        "confirmed_single_writer_count": counts["CONFIRMED_SINGLE_WRITER"],
        "likely_single_writer_count": counts["LIKELY_SINGLE_WRITER"],
        "multiple_writer_risk_count": counts["MULTIPLE_WRITER_RISK"],
        "no_writer_found_count": counts["NO_WRITER_FOUND"],
        "reader_only_count": counts["READER_ONLY_REFERENCES"],
        "highest_risk_files": highest_risk_files(results),
        "recommended_next_steps": recommended_next_steps(results),
        "truth_files": results,
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    audit = build_audit()
    write_json(OUTPUT_PATH, audit)
    print("TITAN ECHO duplicate writer audit: PASSED")
    print(f"Files audited: {audit['files_audited']}")
    print(f"Confirmed single writers: {audit['confirmed_single_writer_count']}")
    print(f"Likely single writers: {audit['likely_single_writer_count']}")
    print(f"Multiple writer risks: {audit['multiple_writer_risk_count']}")
    print(f"No writer found: {audit['no_writer_found_count']}")
    print(f"Reader-only references: {audit['reader_only_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
