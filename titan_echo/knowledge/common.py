"""Shared helpers for read-only ECHO knowledge builders."""

from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
ECHO_RUNTIME = REPO_ROOT / "data" / "runtime" / "echo"

INDEX_EXTENSIONS = {
    ".bat",
    ".csv",
    ".ini",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".txt",
    ".yaml",
    ".yml",
}

EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}

EXCLUDED_PREFIXES = {
    ("data", "cache"),
    ("data", "historical"),
    ("data", "historical_longterm"),
}

RUNTIME_GENERATED_NAMES = {
    "live_price_cache.json",
    "live_price_cache_meta.json",
    "live_price_status.json",
}

MODULE_KEYWORDS = {
    "api": ("api", "fastapi", "relay"),
    "brain": ("brain", "decision", "reasoning"),
    "dashboard": ("dashboard",),
    "evolution": ("evolution", "mutation", "genome"),
    "journal": ("journal", "outcome", "trade_id"),
    "learning": ("learning", "adaptive", "reinforcement"),
    "memory": ("memory", "vault"),
    "news": ("news", "calendar"),
    "research": ("research", "backtest", "replay"),
    "runtime": ("runtime", "daemon", "worker", "scheduler"),
    "scanner": ("scanner", "scan", "setup"),
}

ROLE_PATTERNS = (
    ("runtime_scanner.py", "scanner runtime coordinator"),
    ("outcome_tracker.py", "trade outcome tracker"),
    ("master_controller.py", "master orchestration controller"),
    ("setup_engine.py", "setup evaluation engine"),
    ("trade_execution_layer.py", "trade execution layer"),
    ("risk_management_engine.py", "risk management engine"),
    ("dashboard.py", "dashboard interface"),
    ("titan_api.py", "TITAN API surface"),
)

SECRET_TERMS = (
    "api_key",
    "apikey",
    "auth",
    "bearer",
    "broker",
    "client_id",
    "client_secret",
    "credential",
    "env",
    "password",
    "private_key",
    "secret",
    "supabase",
    "telegram",
    "token",
    "upstox",
)

WRITE_CALL_NAMES = {
    "dump",
    "dumps",
    "open",
    "write",
    "writelines",
    "append",
    "to_csv",
    "to_json",
    "save",
    "savefig",
}

READ_CALL_NAMES = {
    "load",
    "loads",
    "open",
    "read",
    "read_text",
    "read_csv",
    "read_json",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def output_path(name: str) -> Path:
    return ECHO_RUNTIME / name


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(read_text(path))
    except Exception:
        return None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def should_exclude(path: Path) -> bool:
    try:
        parts = tuple(part.lower() for part in path.relative_to(REPO_ROOT).parts)
    except ValueError:
        return True
    if any(part in EXCLUDED_PARTS for part in parts):
        return True
    if path.name in RUNTIME_GENERATED_NAMES:
        return True
    return any(parts[: len(prefix)] == prefix for prefix in EXCLUDED_PREFIXES)


def iter_files(extensions: Iterable[str] | None = None) -> list[Path]:
    allowed = {ext.lower() for ext in extensions} if extensions else INDEX_EXTENSIONS
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or should_exclude(path):
            continue
        if path.suffix.lower() not in allowed:
            continue
        files.append(path)
    return sorted(files, key=relative)


def parse_ast(path: Path) -> ast.Module | None:
    if path.suffix.lower() != ".py":
        return None
    try:
        return ast.parse(read_text(path))
    except SyntaxError:
        return None


def ast_imports(tree: ast.Module | None) -> list[str]:
    if tree is None:
        return []
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * int(node.level or 0)
            imports.add(f"{prefix}{node.module or ''}")
    return sorted(imports)


def ast_defs(tree: ast.Module | None) -> tuple[list[str], list[str]]:
    if tree is None:
        return [], []
    functions: list[str] = []
    classes: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
    return sorted(functions), sorted(classes)


def top_module(rel_path: str) -> str:
    parts = Path(rel_path).parts
    if len(parts) > 1:
        return parts[0]
    return Path(rel_path).stem


def category_for_path(rel_path: str) -> str:
    key = rel_path.lower()
    if key.startswith("titan_echo/"):
        return "echo"
    if key.startswith("tests/") or Path(key).name.startswith("test_"):
        return "tests"
    if key.startswith("tools/") or "diagnostic" in key or "check" in key:
        return "tools"
    if key.startswith("config/") or ".env" in key:
        return "configuration"
    if key.startswith("data/"):
        return "data"
    for module, terms in MODULE_KEYWORDS.items():
        if any(term in key for term in terms):
            return module
    if key.startswith("engines/") or "engine" in key:
        return "engine"
    if key.endswith((".md", ".txt")):
        return "documentation"
    return "general"


def module_for_path(rel_path: str) -> str:
    key = rel_path.lower()
    for module, terms in MODULE_KEYWORDS.items():
        if any(term in key for term in terms):
            return module
    if key.startswith("titan_echo/"):
        return "echo"
    if key.startswith("engines/"):
        return "engines"
    return top_module(rel_path)


def role_for_path(rel_path: str) -> str:
    name = Path(rel_path).name.lower()
    key = rel_path.lower()
    for exact, role in ROLE_PATTERNS:
        if name == exact:
            return role
    category = category_for_path(rel_path)
    stem = Path(rel_path).stem.replace("_", " ")
    if category == "tests":
        return f"test coverage for {stem}"
    if category == "configuration":
        return f"configuration or credential boundary for {stem}"
    if category == "data":
        return f"data artifact or state file for {stem}"
    if category == "documentation":
        return f"documentation for {stem}"
    if "registry" in key:
        return f"{category} registry"
    if "mapper" in key or "map" in key:
        return f"{category} mapper"
    if "check" in key or "diagnostic" in key:
        return f"{category} diagnostic checker"
    return f"{category} component for {stem}"


def danger_for_path(rel_path: str) -> tuple[str, str]:
    key = rel_path.lower()
    if key.endswith(".env") or any(term in key for term in ("secret", "token", "api_key", "credential", "supabase_client")):
        return "CRITICAL", "sensitive credential or secret-adjacent location"
    if any(term in key for term in ("broker", "execution", "trade_execution", "order", "paper_engine")):
        return "HIGH", "trade execution or broker-adjacent area"
    if any(term in key for term in ("risk", "master_brain", "unified_brain", "runtime_scanner", "runtime_master")):
        return "HIGH", "protected trading orchestration area"
    if any(term in key for term in ("scanner", "filter", "setup_engine", "learning", "evolution", "journal", "outcome")):
        return "MEDIUM", "behavioral trading knowledge or scanner area"
    return "LOW", "documentation, test, data, or general support area"


def secret_metadata(path: Path) -> dict[str, Any] | None:
    rel = relative(path)
    key = rel.lower()
    text = ""
    if path.suffix.lower() in {".py", ".json", ".yaml", ".yml", ".env", ".txt", ".md"}:
        text = read_text(path).lower()
    markers = sorted({term for term in SECRET_TERMS if term in key or term in text})
    if not markers:
        return None
    return {
        "path": rel,
        "category": category_for_path(rel),
        "markers": markers,
        "stores_values": path.name == ".env" or "credential" in key or "secret" in key,
        "actual_values_stored": False,
        "note": "Metadata only. Secret values are not read into this registry.",
    }


def imported_repo_paths(path: Path, imports: list[str]) -> list[str]:
    related: set[str] = set()
    for item in imports:
        module = item.lstrip(".").split(".")[0]
        if not module:
            continue
        candidate_dir = REPO_ROOT / module
        candidate_file = REPO_ROOT / f"{module}.py"
        if candidate_dir.exists() or candidate_file.exists():
            related.add(module)
    return sorted(related)


def string_literals(tree: ast.Module | None) -> list[str]:
    if tree is None:
        return []
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "/" in node.value or "\\" in node.value or "." in node.value:
                values.add(node.value)
    return sorted(values)


def detect_io_targets(path: Path, mode: str) -> list[str]:
    tree = parse_ast(path)
    if tree is None:
        return []
    targets: set[str] = set()
    call_names = WRITE_CALL_NAMES if mode == "write" else READ_CALL_NAMES
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name not in call_names:
            continue
        for arg in node.args[:1]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                targets.add(arg.value)
    return sorted(targets)


def slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return value or "unknown"
