import json
from datetime import datetime, timedelta
from pathlib import Path

from report_vault.report_schema import report_sort_key
from report_vault.vault_writer import INDEX_PATH, load_index


def _parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _read_report(path):
    with Path(path).open("r", encoding="utf-8") as report_file:
        payload = json.load(report_file)
    return payload if isinstance(payload, dict) else None


def read_index():
    return load_index()


def read_report_by_id(report_id):
    index = load_index()
    for entry in index.get("reports", []):
        if entry.get("report_id") == report_id:
            return _read_report(entry.get("path"))
    return None


def read_recent_reports(source_worker=None, report_type=None, severity=None, hours=24, limit=200):
    index = load_index()
    cutoff = datetime.now().astimezone() - timedelta(hours=hours) if hours else None
    selected = []
    for entry in reversed(index.get("reports", [])):
        if source_worker and entry.get("source_worker") != source_worker:
            continue
        if report_type and entry.get("report_type") != report_type:
            continue
        if severity and str(entry.get("severity")).upper() != str(severity).upper():
            continue
        created_at = _parse_datetime(entry.get("created_at"))
        if cutoff and created_at and created_at.astimezone() < cutoff:
            continue
        report = _read_report(entry.get("path"))
        if report:
            selected.append(report)
        if limit and len(selected) >= limit:
            break
    return sorted(selected, key=report_sort_key, reverse=True)


def latest_by_worker():
    index = load_index()
    reports = {}
    for worker, entry in index.get("latest_by_worker", {}).items():
        report = _read_report(entry.get("path"))
        if report:
            reports[worker] = report
    return reports


def vault_status():
    index = load_index()
    return {
        "index_path": str(INDEX_PATH).replace("\\", "/"),
        "report_count": index.get("report_count", 0),
        "deduplicated_count": index.get("deduplicated_count", 0),
        "latest_workers": sorted(index.get("latest_by_worker", {}).keys()),
        "updated_at": index.get("updated_at"),
    }
