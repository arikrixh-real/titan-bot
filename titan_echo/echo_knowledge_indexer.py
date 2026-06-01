"""Read-only TITAN knowledge indexer for TITAN ECHO."""

from __future__ import annotations

import ast
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "titan_file_index.json"

INDEX_EXTENSIONS = {".py", ".md", ".json", ".yaml", ".yml", ".txt"}

EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
}

EXCLUDED_PREFIXES = {
    ("data", "cache"),
    ("data", "historical_longterm"),
    ("data", "report_vault"),
}

CRITICAL_KEYWORDS = {
    "broker": "broker/order execution",
    "order": "broker/order execution",
    "execution": "broker/order execution",
    "trade_executor": "broker/order execution",
    "risk": "risk engine",
    "master_brain": "Master Brain",
    "titan_master_brain": "Master Brain",
    "unified_brain": "Unified Brain",
    "consciousness_core": "Consciousness Core",
    "scanner": "scanner/runtime daemon",
    "daemon": "scanner/runtime daemon",
    "runtime_scanner": "scanner/runtime daemon",
}

HIGH_KEYWORDS = {
    "outcome_tracker": "outcome tracker",
    "outcome": "outcome tracker",
    "learning": "learning/evolution",
    "evolution": "learning/evolution",
    "supabase": "Supabase writer",
    "live_price": "live price",
    "telegram": "Telegram alert/execution",
    "alert": "Telegram alert/execution",
}

ROLE_KEYWORDS = [
    ("scanner", "scanner"),
    ("daemon", "runtime daemon"),
    ("master_brain", "Master Brain"),
    ("unified_brain", "Unified Brain"),
    ("consciousness_core", "Consciousness Core"),
    ("broker", "broker/order execution"),
    ("order", "broker/order execution"),
    ("execution", "broker/order execution"),
    ("risk", "risk logic"),
    ("outcome", "outcome tracking"),
    ("learning", "learning"),
    ("evolution", "evolution"),
    ("supabase", "Supabase integration"),
    ("live_price", "live price"),
    ("telegram", "Telegram integration"),
    ("alert", "alerting"),
    ("dashboard", "dashboard"),
    ("runtime", "runtime support"),
    ("config", "configuration"),
    ("test", "test"),
    ("readme", "documentation"),
]


def relative_path(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def should_exclude(path: Path) -> bool:
    if path == OUTPUT_PATH:
        return True

    rel_parts = path.relative_to(REPO_ROOT).parts
    normalized = tuple(part.lower() for part in rel_parts)

    if any(part in EXCLUDED_PARTS for part in normalized):
        return True

    for prefix in EXCLUDED_PREFIXES:
        if normalized[: len(prefix)] == prefix:
            return True

    return False


def iter_indexable_files() -> list[Path]:
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if should_exclude(path):
            continue
        if path.suffix.lower() not in INDEX_EXTENSIONS:
            continue
        files.append(path)
    return sorted(files, key=relative_path)


def read_text_safely(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def parse_python(text: str) -> tuple[list[str], list[str], list[str]]:
    imports: set[str] = set()
    functions: list[str] = []
    classes: list[str] = []

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [], [], []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = "." * node.level + module
            imports.add(module)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)

    return sorted(imports), sorted(functions), sorted(classes)


def detect_probable_role(rel_path: str) -> str:
    path_key = rel_path.lower()
    for keyword, role in ROLE_KEYWORDS:
        if keyword in path_key:
            return role
    if rel_path.endswith(".md") or rel_path.endswith(".txt"):
        return "documentation"
    if rel_path.endswith((".json", ".yaml", ".yml")):
        return "configuration/data"
    return "general module"


def detect_criticality(rel_path: str) -> tuple[str, str]:
    path_key = rel_path.lower()

    for keyword, reason in CRITICAL_KEYWORDS.items():
        if keyword in path_key:
            return "CRITICAL", reason

    for keyword, reason in HIGH_KEYWORDS.items():
        if keyword in path_key:
            return "HIGH", reason

    if rel_path.endswith(".py"):
        return "MEDIUM", "code module"

    return "LOW", "documentation/configuration"


def build_modify_safety_note(criticality: str, reason: str) -> str:
    if criticality == "CRITICAL":
        return f"Do not modify without explicit Ari approval; detected as {reason}."
    if criticality == "HIGH":
        return f"Modify only with review and verification; detected as {reason}."
    if criticality == "MEDIUM":
        return "Review dependencies before modification."
    return "Low-risk documentation/configuration placeholder; still verify before change."


def index_file(path: Path) -> dict[str, object]:
    rel_path = relative_path(path)
    text = read_text_safely(path)
    lines = text.splitlines()
    imports: list[str] = []
    functions: list[str] = []
    classes: list[str] = []

    if path.suffix.lower() == ".py":
        imports, functions, classes = parse_python(text)

    criticality, reason = detect_criticality(rel_path)

    return {
        "relative_path": rel_path,
        "extension": path.suffix.lower(),
        "size_bytes": path.stat().st_size,
        "line_count": len(lines),
        "detected_imports": imports,
        "detected_functions": functions,
        "detected_classes": classes,
        "probable_role": detect_probable_role(rel_path),
        "criticality": criticality,
        "modify_safety_note": build_modify_safety_note(criticality, reason),
    }


def build_index() -> dict[str, object]:
    files = [index_file(path) for path in iter_indexable_files()]
    counts: dict[str, int] = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    for item in files:
        criticality = str(item["criticality"])
        counts[criticality] = counts.get(criticality, 0) + 1

    return {
        "schema": "titan_echo.file_index.v1",
        "official_name": "TITAN ECHO",
        "short_name": "ECHO",
        "repo_root_name": REPO_ROOT.name,
        "runtime_status": "unknown_not_asserted",
        "index_policy": {
            "mode": "read_only_scan",
            "indexed_extensions": sorted(INDEX_EXTENSIONS),
            "excluded_folders": sorted(EXCLUDED_PARTS)
            + ["/".join(prefix) for prefix in sorted(EXCLUDED_PREFIXES)],
        },
        "summary": {
            "total_indexed_files": len(files),
            "criticality_counts": counts,
        },
        "files": files,
    }


def write_index(index: dict[str, object]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(index, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    index = build_index()
    write_index(index)
    total = index["summary"]["total_indexed_files"]  # type: ignore[index]
    counts = index["summary"]["criticality_counts"]  # type: ignore[index]

    print("TITAN ECHO knowledge indexer: PASSED")
    print(f"Indexed files: {total}")
    print(f"Criticality counts: {counts}")
    print(f"Output: {relative_path(OUTPUT_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
