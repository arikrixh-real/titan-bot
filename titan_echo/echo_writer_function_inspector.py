"""Read-only function-level writer inspection for TITAN truth files."""

from __future__ import annotations

import ast
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_RUNTIME = REPO_ROOT / "data" / "runtime" / "echo"

FILE_INDEX_PATH = ECHO_RUNTIME / "titan_file_index.json"
DUPLICATE_AUDIT_PATH = ECHO_RUNTIME / "duplicate_writer_audit.json"
OUTPUT_PATH = ECHO_RUNTIME / "writer_function_inspection.json"

IST = timezone(timedelta(hours=5, minutes=30))

TRUTH_FILES = [
    "brain_state.json",
    "runtime_status.json",
    "filter_engine_diagnostics.json",
    "truth_gate_status.json",
    "worker_health.json",
    "scanner_status.json",
    "outcome_tracker_diagnostics.json",
    "trade_contract_diagnostics.json",
]

WRITER_PATTERNS = [
    "write_text(",
    "json.dump(",
    "os.replace(",
    ".replace(",
    "atomic",
    "tempfile",
]

APPEND_PATTERNS = [
    '"a"',
    "'a'",
    "append",
]

READER_PATTERNS = [
    "read_text(",
    "json.load(",
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


def truth_variants(filename: str) -> list[str]:
    return list(
        dict.fromkeys(
            [
                filename,
                f"data/runtime/{filename}",
                f"data\\runtime\\{filename}",
                f"runtime/{filename}",
                f"runtime\\{filename}",
            ]
        )
    )


def function_ranges(text: str) -> list[tuple[int, int, str]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            ranges.append((node.lineno, end, node.name))
        elif isinstance(node, ast.ClassDef):
            end = getattr(node, "end_lineno", node.lineno)
            ranges.append((node.lineno, end, f"class:{node.name}"))
    return sorted(ranges)


def enclosing_symbol(ranges: list[tuple[int, int, str]], line_number: int) -> str:
    best = "module_scope"
    best_span = 10**9
    for start, end, name in ranges:
        if start <= line_number <= end:
            span = end - start
            if span < best_span:
                best = name
                best_span = span
    return best


def line_window(lines: list[str], line_number: int, radius: int = 4) -> str:
    start = max(0, line_number - radius - 1)
    end = min(len(lines), line_number + radius)
    return "\n".join(lines[start:end])


def matching_lines(lines: list[str], variants: list[str]) -> list[tuple[int, str, str]]:
    matches = []
    for index, line in enumerate(lines, start=1):
        lower = line.lower()
        for variant in variants:
            if variant.lower() in lower:
                matches.append((index, line.strip(), variant))
                break
    return matches


def has_open_mode(window: str, modes: tuple[str, ...]) -> bool:
    compact = re.sub(r"\s+", "", window.lower())
    return any(f"open(" in compact and mode in compact for mode in modes)


def classify_reference(window: str) -> str:
    lower = window.lower()
    writer = any(pattern in lower for pattern in WRITER_PATTERNS) or has_open_mode(
        lower, ('"w"', "'w'")
    )
    appender = has_open_mode(lower, ('"a"', "'a'")) or any(
        pattern in lower for pattern in APPEND_PATTERNS
    )
    reader = any(pattern in lower for pattern in READER_PATTERNS) or has_open_mode(
        lower, ('"r"', "'r'")
    )

    if writer:
        return "writer"
    if appender:
        return "appender"
    if reader:
        return "reader"
    return "unknown"


def evidence_entry(
    rel_path: str,
    line_number: int,
    symbol: str,
    reference_type: str,
    variant: str,
    line: str,
) -> dict[str, Any]:
    return {
        "relative_path": rel_path,
        "line": line_number,
        "symbol": symbol,
        "reference_type": reference_type,
        "matched_reference": variant,
        "line_excerpt": line[:220],
    }


def inspect_truth_file(filename: str, indexed_files: list[dict[str, Any]]) -> dict[str, Any]:
    variants = truth_variants(filename)
    confirmed_writer_functions = []
    possible_writer_functions = []
    appender_functions = []
    reader_references = []
    unknown_references = []
    evidence = []

    for item in indexed_files:
        rel_path = str(item.get("relative_path", ""))
        path = REPO_ROOT / rel_path
        if not path.is_file() or path.suffix.lower() != ".py":
            continue

        text = read_text_safely(path)
        if not any(variant.lower() in text.lower() for variant in variants):
            continue

        lines = text.splitlines()
        ranges = function_ranges(text)
        for line_number, line, variant in matching_lines(lines, variants):
            window = line_window(lines, line_number)
            reference_type = classify_reference(window)
            symbol = enclosing_symbol(ranges, line_number)
            entry = evidence_entry(rel_path, line_number, symbol, reference_type, variant, line)

            if reference_type == "writer":
                if "write_text(" in window.lower() or "json.dump(" in window.lower() or has_open_mode(window, ('"w"', "'w'")):
                    confirmed_writer_functions.append(entry)
                else:
                    possible_writer_functions.append(entry)
            elif reference_type == "appender":
                appender_functions.append(entry)
            elif reference_type == "reader":
                reader_references.append(entry)
            else:
                unknown_references.append(entry)
            evidence.append(entry)

    confirmed_writer_functions = dedupe_entries(confirmed_writer_functions)
    possible_writer_functions = dedupe_entries(possible_writer_functions)
    appender_functions = dedupe_entries(appender_functions)
    reader_references = dedupe_entries(reader_references)
    unknown_references = dedupe_entries(unknown_references)

    writer_status, confidence = writer_status_for(
        confirmed_writer_functions,
        possible_writer_functions,
        appender_functions,
        reader_references,
        unknown_references,
    )

    return {
        "truth_file": filename,
        "confirmed_writer_functions": confirmed_writer_functions,
        "possible_writer_functions": possible_writer_functions,
        "appender_functions": appender_functions,
        "reader_references": reader_references,
        "unknown_references": unknown_references,
        "confidence": confidence,
        "writer_status": writer_status,
        "evidence": dedupe_entries(evidence)[:40],
        "safe_next_action": safe_next_action(filename, writer_status),
    }


def dedupe_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for entry in entries:
        key = (entry.get("relative_path"), entry.get("line"), entry.get("symbol"), entry.get("reference_type"))
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return sorted(result, key=lambda item: (str(item.get("relative_path", "")), int(item.get("line", 0))))


def writer_status_for(
    confirmed: list[dict[str, Any]],
    possible: list[dict[str, Any]],
    appenders: list[dict[str, Any]],
    readers: list[dict[str, Any]],
    unknown: list[dict[str, Any]],
) -> tuple[str, str]:
    if confirmed:
        return "CONFIRMED_WRITER", "HIGH"
    if possible:
        return "POSSIBLE_WRITER", "MEDIUM"
    if appenders:
        return "APPENDER_ONLY", "MEDIUM"
    if readers:
        return "READER_ONLY", "MEDIUM"
    if unknown:
        return "READER_ONLY", "LOW"
    return "NO_REFERENCE", "LOW"


def safe_next_action(filename: str, status: str) -> str:
    if status == "CONFIRMED_WRITER":
        return f"Confirm runtime owner manually for {filename}; do not patch until owner is approved."
    if status == "POSSIBLE_WRITER":
        return f"Inspect possible writer context for {filename} before proposing any change."
    if status == "APPENDER_ONLY":
        return f"Confirm whether append-only behavior is expected for {filename}."
    if status == "READER_ONLY":
        return f"Build writer ownership registry entry for {filename}; do not create duplicate writer."
    return f"Confirm intended owner for {filename}; do not create writer until Ari approves."


def recommended_next_steps(results: list[dict[str, Any]]) -> list[str]:
    steps = [
        "Confirm runtime owner manually for each unresolved truth file.",
        "Build writer ownership registry before any writer patch.",
        "Do not create duplicate writer.",
        "Do not patch until owner confirmed.",
    ]
    if any(item["writer_status"] == "CONFIRMED_WRITER" for item in results):
        steps.append("Inspect confirmed writer functions in read-only mode and record ownership evidence.")
    if any(item["writer_status"] in {"READER_ONLY", "NO_REFERENCE"} for item in results):
        steps.append("Run focused read-only inspection of owner modules for reader-only or no-reference files.")
    return steps


def build_report() -> dict[str, Any]:
    file_index = load_json(FILE_INDEX_PATH)
    load_json(DUPLICATE_AUDIT_PATH)
    indexed_files = [item for item in file_index.get("files", []) if isinstance(item, dict)]
    results = [inspect_truth_file(filename, indexed_files) for filename in TRUTH_FILES]
    counts = Counter(str(item["writer_status"]) for item in results)
    unresolved = [
        item["truth_file"]
        for item in results
        if item["writer_status"] in {"POSSIBLE_WRITER", "APPENDER_ONLY", "READER_ONLY", "NO_REFERENCE"}
    ]

    return {
        "schema": "titan_echo.writer_function_inspection.v1",
        "timestamp_ist": timestamp_ist(),
        "files_inspected": len(results),
        "confirmed_writer_count": counts["CONFIRMED_WRITER"],
        "possible_writer_count": counts["POSSIBLE_WRITER"],
        "appender_only_count": counts["APPENDER_ONLY"],
        "reader_only_count": counts["READER_ONLY"],
        "no_reference_count": counts["NO_REFERENCE"],
        "unresolved_truth_files": unresolved,
        "recommended_next_steps": recommended_next_steps(results),
        "truth_files": results,
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    report = build_report()
    write_json(OUTPUT_PATH, report)
    print("TITAN ECHO writer function inspector: PASSED")
    print(f"Files inspected: {report['files_inspected']}")
    print(f"Confirmed writers: {report['confirmed_writer_count']}")
    print(f"Possible writers: {report['possible_writer_count']}")
    print(f"Appender only: {report['appender_only_count']}")
    print(f"Reader only: {report['reader_only_count']}")
    print(f"No reference: {report['no_reference_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
