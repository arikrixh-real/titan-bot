"""Shared read-only helpers for TITAN ECHO Batch B audits."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_RUNTIME = REPO_ROOT / "data" / "runtime" / "echo"
IST = timezone(timedelta(hours=5, minutes=30))


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def rel(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def load_json(path: Path, default: Any | None = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {} if default is None else default


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def file_index_paths() -> list[str]:
    data = load_json(ECHO_RUNTIME / "titan_file_index.json", {})
    files = data.get("files", []) if isinstance(data, dict) else []
    paths = []
    for item in files:
        if isinstance(item, dict) and item.get("relative_path"):
            paths.append(str(item["relative_path"]).replace("\\", "/"))
    return sorted(dict.fromkeys(paths))


def filesystem_paths() -> list[str]:
    ignored = {".git", ".venv", "__pycache__"}
    paths: list[str] = []
    for path in REPO_ROOT.rglob("*"):
        if any(part in ignored for part in path.parts):
            continue
        if path.is_file():
            paths.append(rel(path))
    return sorted(paths)


def all_known_paths() -> list[str]:
    return sorted(dict.fromkeys(file_index_paths() + filesystem_paths()))


def matching_paths(needles: list[str], paths: list[str] | None = None) -> list[str]:
    paths = paths if paths is not None else all_known_paths()
    lowered_needles = [needle.lower() for needle in needles]
    return [path for path in paths if any(needle in path.lower() for needle in lowered_needles)]


def layer_file_count(layer: str) -> int:
    data = load_json(ECHO_RUNTIME / "titan_architecture_map.json", {})
    for item in data.get("layers", []) if isinstance(data, dict) else []:
        if isinstance(item, dict) and item.get("layer") == layer:
            return int(item.get("file_count") or 0)
    return 0


def text_hits(paths: list[str], needles: list[str], max_hits: int = 25) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    lowered_needles = [needle.lower() for needle in needles]
    for relative in paths:
        path = REPO_ROOT / relative
        if not path.exists() or path.suffix.lower() not in {".py", ".json", ".md", ".txt"}:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        for idx, line in enumerate(lines, start=1):
            lowered = line.lower()
            if any(needle in lowered for needle in lowered_needles):
                hits.append({"file": relative, "line": idx, "text": line.strip()[:220]})
                if len(hits) >= max_hits:
                    return hits
    return hits


def artifact_summary(paths: list[str]) -> list[dict[str, Any]]:
    artifacts = []
    for relative in paths:
        path = REPO_ROOT / relative
        if not path.exists():
            continue
        try:
            stat = path.stat()
            artifacts.append(
                {
                    "path": relative,
                    "size_bytes": stat.st_size,
                    "modified_at_ist": datetime.fromtimestamp(stat.st_mtime, IST).isoformat(),
                }
            )
        except Exception:
            artifacts.append({"path": relative})
    return artifacts


def status_from_runtime(path: str, active_keys: list[str]) -> dict[str, Any]:
    payload = load_json(REPO_ROOT / path, {})
    evidence = {"path": path, "exists": bool(payload), "active_fields": {}}
    active = False
    if isinstance(payload, dict):
        for key in active_keys:
            value = payload.get(key)
            if value is not None:
                evidence["active_fields"][key] = value
                if str(value).upper() in {"ACTIVE", "OK", "PASS", "MASTER_BRAIN_READ_ONLY_COMPLETE"}:
                    active = True
    return {"active": active, "evidence": evidence, "payload": payload if isinstance(payload, dict) else {}}


def unique(items: list[Any], limit: int = 20) -> list[Any]:
    result = []
    seen = set()
    for item in items:
        key = json.dumps(item, sort_keys=True, default=str) if isinstance(item, (dict, list)) else str(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def score_from_flags(flags: list[bool]) -> int:
    return round((sum(1 for flag in flags if flag) / len(flags)) * 100) if flags else 0
