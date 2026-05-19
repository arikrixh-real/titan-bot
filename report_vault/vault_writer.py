import json
import os
import tempfile
from pathlib import Path

from report_vault.report_schema import normalize_report, now_ist


VAULT_DIR = Path("data") / "report_vault"
REPORTS_DIR = VAULT_DIR / "reports"
INDEX_PATH = VAULT_DIR / "index.json"


def ensure_vault():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_PATH.exists():
        _atomic_write_json(INDEX_PATH, _empty_index())


def _empty_index():
    return {
        "schema_version": 1,
        "created_at": now_ist(),
        "updated_at": now_ist(),
        "report_count": 0,
        "deduplicated_count": 0,
        "reports": [],
        "content_hashes": {},
        "latest_by_worker": {},
    }


def _atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as temp_file:
            json.dump(payload, temp_file, indent=2, sort_keys=True, default=str)
            temp_file.write("\n")
            temp_path = Path(temp_file.name)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def load_index():
    ensure_vault()
    try:
        with INDEX_PATH.open("r", encoding="utf-8") as index_file:
            index = json.load(index_file)
        if isinstance(index, dict):
            index.setdefault("reports", [])
            index.setdefault("content_hashes", {})
            index.setdefault("latest_by_worker", {})
            index.setdefault("deduplicated_count", 0)
            return index
    except Exception:
        pass
    index = _empty_index()
    _atomic_write_json(INDEX_PATH, index)
    return index


def _report_path(report):
    safe_worker = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in report["source_worker"])[:80]
    safe_type = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in report["report_type"])[:80]
    created = "".join(char if char.isdigit() else "" for char in report["created_at"])[:14] or "unknown_time"
    return REPORTS_DIR / f"{created}_{safe_worker}_{safe_type}_{report['report_id']}.json"


def write_report(payload):
    """Write one structured report to the append-only vault.

    Raw report files are never overwritten. If the content hash is already indexed,
    the existing report metadata is returned and the duplicate is only counted.
    """
    ensure_vault()
    report = normalize_report(payload)
    index = load_index()
    existing = index["content_hashes"].get(report["content_hash"])
    if existing:
        index["deduplicated_count"] = int(index.get("deduplicated_count") or 0) + 1
        index["updated_at"] = now_ist()
        _atomic_write_json(INDEX_PATH, index)
        return {
            "status": "deduplicated",
            "report_id": existing.get("report_id"),
            "content_hash": report["content_hash"],
            "path": existing.get("path"),
        }

    path = _report_path(report)
    if path.exists():
        path = path.with_name(f"{path.stem}_{report['content_hash'][:8]}{path.suffix}")
    _atomic_write_json(path, report)
    relative_path = str(path).replace("\\", "/")
    entry = {
        "report_id": report["report_id"],
        "source_worker": report["source_worker"],
        "report_type": report["report_type"],
        "created_at": report["created_at"],
        "status": report["status"],
        "severity": report["severity"],
        "summary": report["summary"],
        "actionability_score": report["actionability_score"],
        "content_hash": report["content_hash"],
        "path": relative_path,
    }
    index["reports"].append(entry)
    index["content_hashes"][report["content_hash"]] = entry
    index["latest_by_worker"][report["source_worker"]] = entry
    index["report_count"] = len(index["reports"])
    index["updated_at"] = now_ist()
    _atomic_write_json(INDEX_PATH, index)
    return {
        "status": "written",
        "report_id": report["report_id"],
        "content_hash": report["content_hash"],
        "path": relative_path,
    }


def write_reports(reports):
    results = []
    for report in reports:
        results.append(write_report(report))
    return results
