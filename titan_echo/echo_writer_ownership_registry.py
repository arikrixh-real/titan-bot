"""Generate the TITAN ECHO writer ownership registry."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_RUNTIME = REPO_ROOT / "data" / "runtime" / "echo"

WRITER_FUNCTION_INSPECTION_PATH = ECHO_RUNTIME / "writer_function_inspection.json"
WRITER_OWNERSHIP_AUDIT_PATH = ECHO_RUNTIME / "writer_ownership_audit.json"
DUPLICATE_WRITER_AUDIT_PATH = ECHO_RUNTIME / "duplicate_writer_audit.json"
RUNTIME_TRUTH_AUDIT_PATH = ECHO_RUNTIME / "runtime_truth_audit.json"
MODULE_REGISTRY_PATH = ECHO_RUNTIME / "titan_module_registry.json"
OUTPUT_PATH = ECHO_RUNTIME / "writer_ownership_registry.json"

IST = timezone(timedelta(hours=5, minutes=30))

TARGET_TRUTH_FILES = [
    "brain_state.json",
    "runtime_status.json",
    "filter_engine_diagnostics.json",
    "truth_gate_status.json",
    "worker_health.json",
    "scanner_status.json",
    "outcome_tracker_diagnostics.json",
    "trade_contract_diagnostics.json",
]

FORBIDDEN_ACTIONS = [
    "restart TITAN",
    "deploy",
    "modify broker execution",
    "modify risk logic",
    "modify scanner pipeline",
    "push GitHub",
]

CRITICAL_LAYERS = {
    "Master Brain layer",
    "Risk/Execution layer",
    "Scanner/Setup layer",
}


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def truth_path(filename: str) -> str:
    return f"data/runtime/{filename}"


def infer_layer(filename: str) -> str:
    key = filename.lower()
    if "brain" in key:
        return "Master Brain layer"
    if "filter" in key:
        return "Engine/Filter layer"
    if "truth_gate" in key or "scanner" in key:
        return "Scanner/Setup layer"
    if "worker" in key or "runtime_status" in key:
        return "Runtime/Daemon layer"
    if "trade" in key:
        return "Risk/Execution layer"
    if "outcome" in key:
        return "Outcome/Learning/Evolution layer"
    return "Unknown/Unclassified layer"


def by_truth_name(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = Path(str(item.get("truth_file", ""))).name
        if name:
            result[name] = item
    return result


def owner_status(writer_status: str) -> str:
    if writer_status == "CONFIRMED_WRITER":
        return "CONFIRMED_OWNER"
    if writer_status in {"POSSIBLE_WRITER", "APPENDER_ONLY"}:
        return "POSSIBLE_OWNER"
    if writer_status == "READER_ONLY":
        return "READER_ONLY"
    if writer_status == "NO_REFERENCE":
        return "NO_REFERENCE"
    return "UNRESOLVED_OWNER"


def ownership_rule(status: str, layer: str) -> str:
    rules = ["Runtime truth files must have one authoritative writer."]
    if status == "CONFIRMED_OWNER":
        rules.append("Do not create duplicate writer.")
    elif status == "POSSIBLE_OWNER":
        rules.append("Confirm owner before patch.")
    elif status == "NO_REFERENCE":
        rules.append("If no owner is proven, add owner only after Ari approval.")
    else:
        rules.append("Confirm owner before patch.")
        rules.append("Do not create duplicate writer.")
    if layer in CRITICAL_LAYERS:
        rules.append("For CRITICAL layers, read-only audit first.")
    return " ".join(rules)


def required_verification(status: str, layer: str) -> list[str]:
    verification = [
        "Review writer_function_inspection evidence.",
        "Confirm runtime owner manually.",
        "Record owner before any write task.",
    ]
    if status in {"UNRESOLVED_OWNER", "READER_ONLY", "NO_REFERENCE"}:
        verification.append("Run targeted owner confirmation audit for this truth file.")
    if status == "POSSIBLE_OWNER":
        verification.append("Inspect possible writer function and call path.")
    if layer in CRITICAL_LAYERS:
        verification.append("Ari approval required before any patch.")
    return verification


def safe_next_action(status: str, filename: str) -> str:
    if status == "CONFIRMED_OWNER":
        return f"Record confirmed owner for {filename}; keep duplicate writer blocked."
    if status == "POSSIBLE_OWNER":
        return f"Confirm possible owner for {filename} before any patch."
    if status == "READER_ONLY":
        return f"Find authoritative writer for {filename}; do not create duplicate writer."
    if status == "NO_REFERENCE":
        return f"Identify intended owner for {filename}; writer only after Ari approval."
    return f"Run targeted owner confirmation audit for {filename}."


def duplicate_risk(filename: str, duplicate_map: dict[str, dict[str, Any]]) -> bool:
    item = duplicate_map.get(filename, {})
    return bool(item.get("duplicate_writer_risk", False))


def exists_now(filename: str, ownership_map: dict[str, dict[str, Any]], truth_audit: dict[str, Any]) -> bool:
    item = ownership_map.get(filename)
    if item and "exists_now" in item:
        return bool(item["exists_now"])
    inspected = truth_audit.get("files_inspected", [])
    if isinstance(inspected, list):
        for record in inspected:
            if isinstance(record, dict) and Path(str(record.get("source_file", ""))).name == filename:
                return bool(record.get("present", False))
    return (REPO_ROOT / truth_path(filename)).is_file()


def build_registry_entry(
    filename: str,
    function_map: dict[str, dict[str, Any]],
    ownership_map: dict[str, dict[str, Any]],
    duplicate_map: dict[str, dict[str, Any]],
    truth_audit: dict[str, Any],
) -> dict[str, Any]:
    function_item = function_map.get(filename, {})
    writer_status = str(function_item.get("writer_status", "NO_REFERENCE"))
    status = owner_status(writer_status)
    layer = infer_layer(filename)

    confirmed = function_item.get("confirmed_writer_functions", [])
    possible = [
        *function_item.get("possible_writer_functions", []),
        *function_item.get("appender_functions", []),
    ]
    readers = function_item.get("reader_references", [])
    evidence = function_item.get("evidence", [])

    if not confirmed and ownership_map.get(filename):
        evidence = [*evidence, *ownership_map[filename].get("evidence", [])]
    if duplicate_map.get(filename):
        evidence = [*evidence, *duplicate_map[filename].get("evidence", [])]

    return {
        "truth_file": truth_path(filename),
        "exists_now": exists_now(filename, ownership_map, truth_audit),
        "owner_status": status,
        "confirmed_writer": confirmed[0] if confirmed else None,
        "possible_writers": possible,
        "readers": readers,
        "affected_layer": layer,
        "confidence": function_item.get("confidence", "LOW"),
        "duplicate_writer_risk": duplicate_risk(filename, duplicate_map),
        "ownership_rule": ownership_rule(status, layer),
        "required_verification": required_verification(status, layer),
        "safe_next_action": safe_next_action(status, filename),
        "forbidden_actions": FORBIDDEN_ACTIONS,
        "evidence": evidence[:40] if isinstance(evidence, list) else [],
    }


def highest_risk(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rank = {
        "UNRESOLVED_OWNER": 0,
        "NO_REFERENCE": 1,
        "READER_ONLY": 2,
        "POSSIBLE_OWNER": 3,
        "CONFIRMED_OWNER": 4,
    }
    ordered = sorted(
        entries,
        key=lambda item: (
            rank.get(str(item["owner_status"]), 9),
            0 if item["affected_layer"] in CRITICAL_LAYERS else 1,
            str(item["truth_file"]),
        ),
    )
    return [
        {
            "truth_file": item["truth_file"],
            "owner_status": item["owner_status"],
            "exists_now": item["exists_now"],
            "affected_layer": item["affected_layer"],
            "confidence": item["confidence"],
            "duplicate_writer_risk": item["duplicate_writer_risk"],
        }
        for item in ordered
    ]


def recommended_next_missions(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unresolved = [
        item["truth_file"]
        for item in entries
        if item["owner_status"] in {"UNRESOLVED_OWNER", "READER_ONLY", "NO_REFERENCE"}
    ]
    return [
        {
            "mission_title": "ECHO Alert Engine",
            "risk_level": "LOW",
            "requires_ari_approval": True,
            "purpose": "Surface ECHO observer and registry warnings without modifying TITAN runtime.",
            "forbidden_actions": FORBIDDEN_ACTIONS,
        },
        {
            "mission_title": "ECHO Mission Planner",
            "risk_level": "LOW",
            "requires_ari_approval": True,
            "purpose": "Turn ECHO context and registry evidence into safe mission proposals.",
            "forbidden_actions": FORBIDDEN_ACTIONS,
        },
        {
            "mission_title": "Targeted owner confirmation audit for unresolved truth files",
            "risk_level": "LOW",
            "requires_ari_approval": True,
            "target_truth_files": unresolved,
            "forbidden_actions": FORBIDDEN_ACTIONS,
        },
        {
            "mission_title": "Runtime truth writer repair only after Ari approval",
            "risk_level": "CRITICAL",
            "requires_ari_approval": True,
            "target_truth_files": unresolved,
            "forbidden_actions": FORBIDDEN_ACTIONS,
        },
    ]


def build_registry() -> dict[str, Any]:
    function_inspection = load_json(WRITER_FUNCTION_INSPECTION_PATH)
    ownership_audit = load_json(WRITER_OWNERSHIP_AUDIT_PATH)
    duplicate_audit = load_json(DUPLICATE_WRITER_AUDIT_PATH)
    truth_audit = load_json(RUNTIME_TRUTH_AUDIT_PATH)
    load_json(MODULE_REGISTRY_PATH)

    function_map = by_truth_name(function_inspection.get("truth_files", []))
    ownership_map = by_truth_name(ownership_audit.get("truth_files", []))
    duplicate_map = by_truth_name(duplicate_audit.get("truth_files", []))

    entries = [
        build_registry_entry(filename, function_map, ownership_map, duplicate_map, truth_audit)
        for filename in TARGET_TRUTH_FILES
    ]
    counts = Counter(str(entry["owner_status"]) for entry in entries)

    return {
        "schema": "titan_echo.writer_ownership_registry.v1",
        "timestamp_ist": timestamp_ist(),
        "files_registered": len(entries),
        "confirmed_owner_count": counts["CONFIRMED_OWNER"],
        "possible_owner_count": counts["POSSIBLE_OWNER"],
        "unresolved_owner_count": counts["UNRESOLVED_OWNER"],
        "reader_only_count": counts["READER_ONLY"],
        "no_reference_count": counts["NO_REFERENCE"],
        "highest_risk_truth_files": highest_risk(entries),
        "recommended_next_missions": recommended_next_missions(entries),
        "truth_files": entries,
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    registry = build_registry()
    write_json(OUTPUT_PATH, registry)
    print("TITAN ECHO writer ownership registry: PASSED")
    print(f"Files registered: {registry['files_registered']}")
    print(f"Confirmed owners: {registry['confirmed_owner_count']}")
    print(f"Possible owners: {registry['possible_owner_count']}")
    print(f"Unresolved owners: {registry['unresolved_owner_count']}")
    print(f"Reader only: {registry['reader_only_count']}")
    print(f"No reference: {registry['no_reference_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
