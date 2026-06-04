"""Read-only TITAN inspection layer for the local relay."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from titan_echo.echo_relay_config import relay_safety


REPO_ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 200_000
MAX_JSON_PATH_FILE_BYTES = 400_000
MAX_JSON_PATH_STRING_CHARS = 300
MAX_JSON_PATH_CONTAINER_ITEMS = 20
MAX_SEARCH_BYTES = 400_000
MAX_SEARCH_RESULTS = 100
SKIPPED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
SENSITIVE_NAME_RE = re.compile(
    r"(^\.env($|\.)|secret|token|apikey|api_key|password|passwd|credential|private[_-]?key|auth)",
    re.IGNORECASE,
)
SENSITIVE_JSON_KEY_RE = re.compile(
    r"(secret|token|apikey|api_key|password|passwd|credential|private[_-]?key)",
    re.IGNORECASE,
)
REDACTION_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|credential)(\s*[:=]\s*)([^\s,'\"\}]+)"),
    re.compile(r"(?i)(bearer\s+)[a-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)(x-[a-z0-9-]*key['\"]?\s*[:=]\s*['\"]?)[^'\"\s,}]+"),
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safety() -> dict[str, bool]:
    safety = relay_safety()
    safety.update(
        {
            "read_only": True,
            "write_delete_edit_restart_deploy": False,
            "git_push_pull": False,
            "path_confined_to_repo": True,
            "traversal_blocked": True,
            "secrets_redacted": True,
        }
    )
    return safety


def _audit(action: str, target: str | None = None) -> dict[str, Any]:
    return {
        "schema": "titan.inspect.audit.v1",
        "recorded_in_response": True,
        "persistent_write_performed": False,
        "action": action,
        "target": target or "",
        "timestamp_utc": _now(),
    }


def _response(action: str, target: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    payload.setdefault("schema", "titan.inspect.v1")
    payload.setdefault("status", "OK")
    payload["audit"] = _audit(action, target)
    payload["safety"] = _safety()
    return payload


def _blocked(action: str, target: str | None, reason: str) -> dict[str, Any]:
    return _response(
        action,
        target,
        {
            "status": "BLOCKED",
            "reason": reason,
            "read_performed": False,
        },
    )


def _json_path_response(
    *,
    status: str,
    path: str | None,
    json_path: str | None,
    found: bool,
    value: Any,
    value_type: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "path": path or "",
        "json_path": json_path or "",
        "found": found,
        "value": value,
        "value_type": value_type,
        "safety": _safety(),
        "audit": _audit("json-path", path),
    }


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix() or "."


def _resolve_repo_path(raw_path: str | None) -> tuple[Path | None, str | None]:
    requested = (raw_path or ".").strip() or "."
    if "\x00" in requested:
        return None, "nul_byte_in_path"
    if ".." in Path(requested).parts:
        return None, "parent_traversal_blocked"
    candidate = (REPO_ROOT / requested).resolve()
    try:
        candidate.relative_to(REPO_ROOT)
    except ValueError:
        return None, "path_outside_repo"
    return candidate, None


def _is_sensitive(path: Path) -> bool:
    rel_parts = path.relative_to(REPO_ROOT).parts
    return any(SENSITIVE_NAME_RE.search(part) for part in rel_parts)


def _redact(text: str) -> str:
    redacted = text
    for pattern in REDACTION_PATTERNS:
        redacted = pattern.sub(lambda match: "".join(match.groups()[:-1]) + "[REDACTED]", redacted)
    return redacted


def _redact_json_value(value: Any, key: str | None = None) -> Any:
    if key and SENSITIVE_JSON_KEY_RE.search(key):
        return "[REDACTED]"
    if isinstance(value, str):
        return _redact(value)
    if isinstance(value, list):
        return [_redact_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _redact_json_value(v, str(k)) for k, v in value.items()}
    return value


def _compact_json_value(value: Any) -> Any:
    redacted = _redact_json_value(value)
    if isinstance(redacted, str):
        if len(redacted) <= MAX_JSON_PATH_STRING_CHARS:
            return redacted
        return {
            "preview": redacted[:MAX_JSON_PATH_STRING_CHARS],
            "truncated": True,
            "length": len(redacted),
        }
    if isinstance(redacted, list):
        items = redacted[:MAX_JSON_PATH_CONTAINER_ITEMS]
        return {
            "type": "list",
            "count": len(redacted),
            "items": [_compact_json_value(item) for item in items],
            "truncated": len(redacted) > len(items),
        }
    if isinstance(redacted, dict):
        keys = list(redacted)[:MAX_JSON_PATH_CONTAINER_ITEMS]
        return {
            "type": "dict",
            "count": len(redacted),
            "keys": keys,
            "items": {key: _compact_json_value(redacted[key]) for key in keys},
            "truncated": len(redacted) > len(keys),
        }
    return redacted


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def inspect_json_path(path: str, json_path: str) -> dict[str, Any]:
    target, error = _resolve_repo_path(path)
    if error:
        return _json_path_response(
            status="BLOCKED",
            path=path,
            json_path=json_path,
            found=False,
            value=None,
            value_type="missing",
        )
    if target is None or not target.exists() or not target.is_file():
        return _json_path_response(
            status="NOT_FOUND",
            path=path,
            json_path=json_path,
            found=False,
            value=None,
            value_type="missing",
        )
    if _is_sensitive(target):
        return _json_path_response(
            status="BLOCKED",
            path=path,
            json_path=json_path,
            found=False,
            value=None,
            value_type="missing",
        )
    if target.suffix.lower() != ".json":
        return _json_path_response(
            status="BLOCKED",
            path=path,
            json_path=json_path,
            found=False,
            value=None,
            value_type="missing",
        )
    if target.stat().st_size > MAX_JSON_PATH_FILE_BYTES:
        return _json_path_response(
            status="BLOCKED",
            path=path,
            json_path=json_path,
            found=False,
            value=None,
            value_type="missing",
        )

    requested_path = (json_path or "").strip()
    if not requested_path:
        return _json_path_response(
            status="BLOCKED",
            path=path,
            json_path=json_path,
            found=False,
            value=None,
            value_type="missing",
        )

    try:
        payload = json.loads(target.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return _json_path_response(
            status="INVALID_JSON",
            path=_relative(target),
            json_path=requested_path,
            found=False,
            value=None,
            value_type="missing",
        )

    current = payload
    for segment in requested_path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        elif isinstance(current, list) and segment.isdigit() and int(segment) < len(current):
            current = current[int(segment)]
        else:
            return _json_path_response(
                status="OK",
                path=_relative(target),
                json_path=requested_path,
                found=False,
                value=None,
                value_type="missing",
            )

    return _json_path_response(
        status="OK",
        path=_relative(target),
        json_path=requested_path,
        found=True,
        value=_compact_json_value(current),
        value_type=_value_type(current),
    )


def inspect_tree(path: str | None = ".", depth: int = 2, max_entries: int = 250) -> dict[str, Any]:
    target, error = _resolve_repo_path(path)
    if error:
        return _blocked("tree", path, error)
    if target is None or not target.exists():
        return _blocked("tree", path, "path_not_found")
    if _is_sensitive(target):
        return _blocked("tree", path, "sensitive_path_blocked")

    bounded_depth = max(0, min(int(depth), 6))
    bounded_max = max(1, min(int(max_entries), 1000))
    entries: list[dict[str, Any]] = []

    def walk(current: Path, remaining: int) -> None:
        if len(entries) >= bounded_max or not current.is_dir():
            return
        try:
            children = sorted(current.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        except OSError:
            return
        for child in children:
            if len(entries) >= bounded_max:
                break
            if child.name in SKIPPED_DIRS or _is_sensitive(child):
                entries.append({"path": _relative(child), "type": "redacted", "reason": "sensitive_or_skipped"})
                continue
            entries.append(
                {
                    "path": _relative(child),
                    "type": "dir" if child.is_dir() else "file",
                    "size_bytes": child.stat().st_size if child.is_file() else None,
                }
            )
            if child.is_dir() and remaining > 0:
                walk(child, remaining - 1)

    walk(target, bounded_depth)
    return _response(
        "tree",
        path,
        {
            "root": _relative(target),
            "depth": bounded_depth,
            "entries_returned": len(entries),
            "truncated": len(entries) >= bounded_max,
            "entries": entries,
            "read_performed": True,
        },
    )


def inspect_file(path: str) -> dict[str, Any]:
    target, error = _resolve_repo_path(path)
    if error:
        return _blocked("file", path, error)
    if target is None or not target.exists() or not target.is_file():
        return _blocked("file", path, "file_not_found")
    if _is_sensitive(target):
        return _blocked("file", path, "sensitive_file_blocked")
    size = target.stat().st_size
    if size > MAX_FILE_BYTES:
        return _blocked("file", path, "file_too_large")
    raw = target.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    return _response(
        "file",
        path,
        {
            "path": _relative(target),
            "size_bytes": size,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "content": _redact(text),
            "redacted": True,
            "read_performed": True,
        },
    )


def inspect_runtime() -> dict[str, Any]:
    runtime_dir = REPO_ROOT / "data" / "runtime"
    files = []
    if runtime_dir.exists():
        for path in sorted(runtime_dir.glob("*.json"))[:50]:
            if _is_sensitive(path):
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                payload = {}
            files.append(
                {
                    "path": _relative(path),
                    "status": payload.get("status") if isinstance(payload, dict) else None,
                    "updated_at": payload.get("updated_at") if isinstance(payload, dict) else None,
                    "size_bytes": path.stat().st_size,
                }
            )
    return _response("runtime", "data/runtime", {"runtime_files": files, "read_performed": True})


def inspect_health() -> dict[str, Any]:
    probes = {
        "repo_root_exists": REPO_ROOT.exists(),
        "runtime_dir_exists": (REPO_ROOT / "data" / "runtime").exists(),
        "fastapi_importable": _module_available("fastapi"),
        "relay_app_importable": True,
    }
    return _response("health", None, {"status": "OK", "probes": probes, "read_performed": True})


def _module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def _git(args: list[str]) -> dict[str, Any]:
    blocked = {"push", "pull", "fetch", "merge", "rebase", "reset", "checkout", "commit"}
    if any(arg in blocked for arg in args):
        return {"returncode": 1, "stdout": "", "stderr": "blocked_git_mutation"}
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )
    return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def inspect_git() -> dict[str, Any]:
    head = _git(["rev-parse", "HEAD"])
    branch = _git(["branch", "--show-current"])
    status = _git(["status", "--short"])
    latest = _git(["log", "-1", "--pretty=%H%x09%an%x09%aI%x09%s"])
    return _response(
        "git",
        None,
        {
            "head": head["stdout"].strip(),
            "branch": branch["stdout"].strip(),
            "status_short": status["stdout"].splitlines(),
            "latest_commit": latest["stdout"].strip(),
            "git_commands_executed": [
                "git rev-parse HEAD",
                "git branch --show-current",
                "git status --short",
                "git log -1 --pretty=%H%x09%an%x09%aI%x09%s",
            ],
            "blocked_git_mutations": ["push", "pull", "fetch", "merge", "rebase", "reset", "checkout", "commit"],
            "read_performed": True,
        },
    )


def inspect_search(q: str, path: str | None = ".", max_results: int = MAX_SEARCH_RESULTS) -> dict[str, Any]:
    query = (q or "").strip()
    if not query:
        return _blocked("search", path, "query_required")
    target, error = _resolve_repo_path(path)
    if error:
        return _blocked("search", path, error)
    if target is None or not target.exists():
        return _blocked("search", path, "path_not_found")
    if _is_sensitive(target):
        return _blocked("search", path, "sensitive_path_blocked")

    bounded_max = max(1, min(int(max_results), MAX_SEARCH_RESULTS))
    results: list[dict[str, Any]] = []
    roots = [target] if target.is_file() else target.rglob("*")
    for file_path in roots:
        if len(results) >= bounded_max:
            break
        if not file_path.is_file() or any(part in SKIPPED_DIRS for part in file_path.relative_to(REPO_ROOT).parts):
            continue
        if _is_sensitive(file_path) or file_path.stat().st_size > MAX_SEARCH_BYTES:
            continue
        try:
            lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        for line_no, line in enumerate(lines, start=1):
            if query.lower() in line.lower():
                results.append(
                    {
                        "path": _relative(file_path),
                        "line": line_no,
                        "preview": _redact(line.strip())[:240],
                    }
                )
                if len(results) >= bounded_max:
                    break
    return _response(
        "search",
        path,
        {
            "query": "[REDACTED]" if SENSITIVE_NAME_RE.search(query) else query,
            "results": results,
            "results_returned": len(results),
            "truncated": len(results) >= bounded_max,
            "read_performed": True,
        },
    )


def inspect_connections(path: str | None = None, max_edges: int = 250) -> dict[str, Any]:
    start, error = _resolve_repo_path(path or ".")
    if error:
        return _blocked("connections", path, error)
    if start is None or not start.exists():
        return _blocked("connections", path, "path_not_found")
    py_files = [start] if start.is_file() else sorted(start.rglob("*.py"))
    nodes = set()
    edges: list[dict[str, str]] = []
    bounded_edges = max(1, min(int(max_edges), 1000))
    for file_path in py_files:
        if len(edges) >= bounded_edges:
            break
        if any(part in SKIPPED_DIRS for part in file_path.relative_to(REPO_ROOT).parts) or _is_sensitive(file_path):
            continue
        rel = _relative(file_path)
        nodes.add(rel)
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        for node in ast.walk(tree):
            module = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
                    break
            elif isinstance(node, ast.ImportFrom):
                module = node.module
            if not module or not module.startswith(("titan_", "runtime_", "engines", "data", "journal", "scanners", "config")):
                continue
            edges.append({"from": rel, "to": module, "relationship": "imports"})
            if len(edges) >= bounded_edges:
                break
    return _response(
        "connections",
        path,
        {
            "nodes": sorted(nodes),
            "edges": edges,
            "summary": {"nodes": len(nodes), "edges": len(edges)},
            "truncated": len(edges) >= bounded_edges,
            "read_performed": True,
        },
    )


__all__ = [
    "inspect_connections",
    "inspect_file",
    "inspect_git",
    "inspect_health",
    "inspect_json_path",
    "inspect_runtime",
    "inspect_search",
    "inspect_tree",
]
