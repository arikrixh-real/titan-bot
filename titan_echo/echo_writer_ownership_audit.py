"""Read-only writer ownership audit for TITAN runtime truth files."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
ECHO_RUNTIME = RUNTIME_DIR / "echo"

FILE_INDEX_PATH = ECHO_RUNTIME / "titan_file_index.json"
ARCHITECTURE_MAP_PATH = ECHO_RUNTIME / "titan_architecture_map.json"
MODULE_REGISTRY_PATH = ECHO_RUNTIME / "titan_module_registry.json"
CONNECTION_GRAPH_PATH = ECHO_RUNTIME / "titan_connection_graph.json"
RUNTIME_TRUTH_AUDIT_PATH = ECHO_RUNTIME / "runtime_truth_audit.json"
OUTPUT_PATH = ECHO_RUNTIME / "writer_ownership_audit.json"

IST = timezone(timedelta(hours=5, minutes=30))

TRUTH_FILES = [
    "data/runtime/brain_state.json",
    "data/runtime/runtime_status.json",
    "data/runtime/filter_engine_diagnostics.json",
    "data/runtime/truth_gate_status.json",
    "data/runtime/worker_health.json",
    "data/runtime/scanner_status.json",
    "data/runtime/outcome_tracker_diagnostics.json",
    "data/runtime/trade_contract_diagnostics.json",
]

FORBIDDEN_ACTIONS = [
    "restart TITAN",
    "deploy",
    "modify broker execution",
    "modify risk logic",
    "modify scanner pipeline",
    "push GitHub",
]

WRITE_PATTERNS = [
    ".write_text(",
    ".write_bytes(",
    "json.dump(",
    "safe_write",
    "atomic_write",
    "open(",
    '"w"',
    "'w'",
    '"a"',
    "'a'",
]

READ_PATTERNS = [
    ".read_text(",
    ".read_bytes(",
    "json.load(",
    "open(",
    '"r"',
    "'r'",
]


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def read_text_safely(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def truth_variants(truth_file: str) -> list[str]:
    normalized = truth_file.replace("\\", "/")
    filename = Path(normalized).name
    stem = Path(filename).stem
    return list(
        dict.fromkeys(
            [
                normalized,
                normalized.replace("/", "\\"),
                f"runtime/{filename}",
                f"runtime\\{filename}",
                filename,
                stem,
            ]
        )
    )


def owner_keywords(truth_file: str) -> list[str]:
    name = Path(truth_file).name.lower()
    if name == "brain_state.json":
        return ["brain_state", "master_brain", "unified_brain", "brain"]
    if name == "runtime_status.json":
        return ["runtime_status", "runtime_health", "runtime_supervisor", "runtime_status"]
    if name == "filter_engine_diagnostics.json":
        return ["filter_engine_diagnostics", "filter_diagnostics", "filter_engine", "scanner_filter"]
    if name == "truth_gate_status.json":
        return ["truth_gate_status", "truth_gate", "truth_gate_check", "truth"]
    if name == "worker_health.json":
        return ["worker_health", "heartbeat", "continuous_workers", "worker"]
    if name == "scanner_status.json":
        return ["scanner_status", "runtime_scanner", "scanner"]
    if name == "outcome_tracker_diagnostics.json":
        return ["outcome_tracker_diagnostics", "outcome_tracker", "trade_outcome"]
    if name == "trade_contract_diagnostics.json":
        return ["trade_contract_diagnostics", "trade_contract", "trade_pipeline"]
    return [Path(name).stem]


def infer_layer(truth_file: str) -> str:
    key = truth_file.lower()
    if "brain" in key:
        return "Master Brain layer"
    if "filter" in key:
        return "Engine/Filter layer"
    if "truth_gate" in key or "scanner" in key:
        return "Scanner/Setup layer"
    if "worker" in key or "runtime_status" in key:
        return "Runtime/Daemon layer"
    if "trade" in key or "risk" in key or "broker" in key:
        return "Risk/Execution layer"
    if "outcome" in key:
        return "Outcome/Learning/Evolution layer"
    return "Unknown/Unclassified layer"


def context_window(text: str, needle: str, radius: int = 80) -> str:
    index = text.lower().find(needle.lower())
    if index < 0:
        return ""
    start = max(0, index - radius)
    end = min(len(text), index + len(needle) + radius)
    return text[start:end].replace("\n", " ").strip()


def has_write_signal(window: str) -> bool:
    lower = window.lower()
    if any(pattern in lower for pattern in [p.lower() for p in WRITE_PATTERNS]):
        if any(mode in lower for mode in ['"w"', "'w'", '"a"', "'a'", "write", "dump", "safe_write", "atomic_write"]):
            return True
    return False


def has_read_signal(window: str) -> bool:
    lower = window.lower()
    if any(pattern in lower for pattern in [p.lower() for p in READ_PATTERNS]):
        if any(mode in lower for mode in ['"r"', "'r'", "read", "load"]):
            return True
    return False


def candidate_record(item: dict[str, Any], score: int, signals: list[str]) -> dict[str, Any]:
    return {
        "relative_path": str(item.get("relative_path", "")),
        "criticality": str(item.get("criticality", "LOW")),
        "probable_role": str(item.get("probable_role", "unknown")),
        "score": score,
        "signals": signals,
    }


def scan_candidates(truth_file: str, indexed_files: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    variants = truth_variants(truth_file)
    keywords = owner_keywords(truth_file)
    likely_writers: list[dict[str, Any]] = []
    likely_readers: list[dict[str, Any]] = []
    evidence: list[str] = []

    for item in indexed_files:
        rel_path = str(item.get("relative_path", ""))
        path = REPO_ROOT / rel_path
        if not path.is_file() or path.suffix.lower() not in {".py", ".md", ".json", ".yaml", ".yml", ".txt"}:
            continue

        text = read_text_safely(path)
        text_lower = text.lower()
        path_lower = rel_path.lower()
        matched_variant = next((variant for variant in variants if variant.lower() in text_lower), "")
        matched_keyword = next((keyword for keyword in keywords if keyword.lower() in path_lower), "")

        if not matched_variant and not matched_keyword:
            continue

        signals: list[str] = []
        score = 0
        window = context_window(text, matched_variant) if matched_variant else ""

        if matched_variant:
            score += 4
            signals.append(f"exact_reference:{matched_variant}")
            evidence.append(f"{rel_path} references {Path(truth_file).name}")
        if re.search(r"Path\s*\(", window):
            score += 1
            signals.append("path_pattern")
        if has_write_signal(window):
            score += 5
            signals.append("write_signal")
        if has_read_signal(window):
            score += 3
            signals.append("read_signal")
        if matched_keyword:
            score += 1
            signals.append(f"module_keyword:{matched_keyword}")

        record = candidate_record(item, score, signals)
        if "write_signal" in signals:
            likely_writers.append(record)
        elif matched_keyword and any(word in path_lower for word in ["runtime_", "tool", "diagnostic", "check", "health", "scanner"]):
            weak = dict(record)
            weak["signals"] = [*signals, "possible_status_owner"]
            likely_writers.append(weak)
        if "read_signal" in signals or matched_variant:
            likely_readers.append(record)

    likely_writers = sorted(likely_writers, key=lambda item: (-int(item["score"]), item["relative_path"]))[:12]
    likely_readers = sorted(likely_readers, key=lambda item: (-int(item["score"]), item["relative_path"]))[:12]
    return likely_writers, likely_readers, list(dict.fromkeys(evidence))[:30]


def ownership_status(writers: list[dict[str, Any]]) -> tuple[str, str]:
    strong = [item for item in writers if "write_signal" in item.get("signals", [])]
    if not writers:
        return "NO_WRITER_FOUND", "LOW"
    if len(strong) == 1:
        return "CLEAR", "HIGH"
    if len(strong) > 1:
        return "MULTIPLE_POSSIBLE_WRITERS", "MEDIUM"
    if len(writers) == 1:
        return "UNCLEAR", "LOW"
    return "MULTIPLE_POSSIBLE_WRITERS", "LOW"


def safe_next_action(status: str, truth_file: str) -> str:
    name = Path(truth_file).name
    if status == "CLEAR":
        return f"Inspect exact writer function for {name} before proposing any change."
    if status == "NO_WRITER_FOUND":
        return f"Confirm intended writer ownership for {name}; add proof writer only after Ari approval."
    if status == "MULTIPLE_POSSIBLE_WRITERS":
        return f"Audit duplicate writer candidates for {name}; do not create another writer."
    return f"Run read-only context builder for {name} and confirm ownership before any patch."


def highest_risk(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    risk_rank = {
        "NO_WRITER_FOUND": 0,
        "MULTIPLE_POSSIBLE_WRITERS": 1,
        "UNCLEAR": 2,
        "CLEAR": 3,
    }
    selected = sorted(records, key=lambda item: (risk_rank.get(str(item["ownership_status"]), 9), item["truth_file"]))
    return [
        {
            "truth_file": item["truth_file"],
            "ownership_status": item["ownership_status"],
            "ownership_confidence": item["ownership_confidence"],
            "exists_now": item["exists_now"],
            "affected_layer": item["affected_layer"],
        }
        for item in selected[:8]
    ]


def recommended_next_missions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    missions = [
        {
            "mission_title": "Read-only writer ownership confirmation",
            "risk_level": "LOW",
            "requires_ari_approval": True,
            "target_truth_files": [item["truth_file"] for item in records],
            "forbidden_actions": FORBIDDEN_ACTIONS,
        }
    ]
    risky = [
        item["truth_file"]
        for item in records
        if item["ownership_status"] in {"NO_WRITER_FOUND", "MULTIPLE_POSSIBLE_WRITERS"}
    ]
    if risky:
        missions.append(
            {
                "mission_title": "Read-only duplicate or missing writer audit",
                "risk_level": "MEDIUM",
                "requires_ari_approval": True,
                "target_truth_files": risky,
                "forbidden_actions": FORBIDDEN_ACTIONS,
            }
        )
    return missions


def build_audit() -> dict[str, Any]:
    file_index = load_json(FILE_INDEX_PATH)
    load_json(ARCHITECTURE_MAP_PATH)
    load_json(MODULE_REGISTRY_PATH)
    load_json(CONNECTION_GRAPH_PATH)
    load_json(RUNTIME_TRUTH_AUDIT_PATH)

    indexed_files = [item for item in file_index.get("files", []) if isinstance(item, dict)]
    records = []

    for truth_file in TRUTH_FILES:
        writers, readers, evidence = scan_candidates(truth_file, indexed_files)
        status, confidence = ownership_status(writers)
        exists_now = (REPO_ROOT / truth_file).is_file()
        records.append(
            {
                "truth_file": truth_file,
                "exists_now": exists_now,
                "likely_writers": writers,
                "likely_readers": readers,
                "ownership_confidence": confidence,
                "ownership_status": status,
                "affected_layer": infer_layer(truth_file),
                "evidence": evidence,
                "safe_next_action": safe_next_action(status, truth_file),
                "forbidden_actions": FORBIDDEN_ACTIONS,
            }
        )

    counts = CounterLike(records)
    return {
        "schema": "titan_echo.writer_ownership_audit.v1",
        "timestamp_ist": timestamp_ist(),
        "total_truth_files_audited": len(records),
        "clear_ownership_count": counts["CLEAR"],
        "unclear_ownership_count": counts["UNCLEAR"],
        "no_writer_found_count": counts["NO_WRITER_FOUND"],
        "multiple_possible_writers_count": counts["MULTIPLE_POSSIBLE_WRITERS"],
        "highest_risk_truth_files": highest_risk(records),
        "recommended_next_missions": recommended_next_missions(records),
        "truth_files": records,
    }


def CounterLike(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "CLEAR": 0,
        "UNCLEAR": 0,
        "NO_WRITER_FOUND": 0,
        "MULTIPLE_POSSIBLE_WRITERS": 0,
    }
    for item in records:
        status = str(item.get("ownership_status", "UNCLEAR"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    audit = build_audit()
    write_json(OUTPUT_PATH, audit)
    print("TITAN ECHO writer ownership audit: PASSED")
    print(f"Truth files audited: {audit['total_truth_files_audited']}")
    print(f"Clear ownership: {audit['clear_ownership_count']}")
    print(f"Unclear ownership: {audit['unclear_ownership_count']}")
    print(f"No writer found: {audit['no_writer_found_count']}")
    print(f"Multiple possible writers: {audit['multiple_possible_writers_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
