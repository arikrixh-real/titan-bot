import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone


IST = timezone(timedelta(hours=5, minutes=30))
REPORT_SCHEMA_VERSION = 1
VALID_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
VALID_STATUSES = {"OK", "WARNING", "ERROR", "STALE", "UNKNOWN"}


def now_ist():
    return datetime.now(IST).isoformat()


def stable_hash(payload):
    encoded = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _clean_string(value, default=""):
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def normalize_severity(value):
    normalized = str(value or "LOW").upper()
    return normalized if normalized in VALID_SEVERITIES else "LOW"


def severity_rank(severity):
    return {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}.get(normalize_severity(severity), 1)


def normalize_status(value):
    normalized = str(value or "UNKNOWN").upper()
    return normalized if normalized in VALID_STATUSES else normalized[:40] or "UNKNOWN"


def normalize_score(value):
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    if score > 1.0:
        score = score / 100.0
    return round(max(0.0, min(score, 1.0)), 3)


def report_content_payload(report):
    return {
        "source_worker": report.get("source_worker"),
        "report_type": report.get("report_type"),
        "status": report.get("status"),
        "severity": report.get("severity"),
        "summary": report.get("summary"),
        "key_findings": report.get("key_findings", []),
        "evidence": report.get("evidence", []),
        "recommendations": report.get("recommendations", []),
        "data_quality": report.get("data_quality"),
        "actionability_score": report.get("actionability_score"),
    }


def normalize_report(payload):
    payload = payload or {}
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_id": _clean_string(payload.get("report_id"), f"report_{uuid.uuid4().hex}"),
        "source_worker": _clean_string(payload.get("source_worker"), "unknown_worker"),
        "report_type": _clean_string(payload.get("report_type"), "general"),
        "created_at": _clean_string(payload.get("created_at"), now_ist()),
        "status": normalize_status(payload.get("status")),
        "severity": normalize_severity(payload.get("severity")),
        "summary": _clean_string(payload.get("summary"), "No summary provided."),
        "key_findings": _as_list(payload.get("key_findings")),
        "evidence": _as_list(payload.get("evidence")),
        "recommendations": _as_list(payload.get("recommendations")),
        "data_quality": _clean_string(payload.get("data_quality"), "UNKNOWN"),
        "actionability_score": normalize_score(payload.get("actionability_score")),
        "content_hash": _clean_string(payload.get("content_hash")),
    }
    if not report["content_hash"]:
        report["content_hash"] = stable_hash(report_content_payload(report))
    return report


def report_sort_key(report):
    return (
        severity_rank(report.get("severity")),
        float(report.get("actionability_score") or 0.0),
        str(report.get("created_at") or ""),
    )
