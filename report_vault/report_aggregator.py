import glob
import json
from pathlib import Path

from report_vault.intelligence_packet import build_intelligence_packet, packet_to_text
from report_vault.report_schema import normalize_report, now_ist, stable_hash
from report_vault.vault_reader import read_recent_reports
from report_vault.vault_writer import VAULT_DIR, write_report, _atomic_write_json, ensure_vault


PACKET_PATH = VAULT_DIR / "latest_aggregated_packet.json"
SUMMARY_PATH = VAULT_DIR / "latest_aggregated_summary.txt"
DEFAULT_SOURCE_PATTERNS = (
    "data/runtime/worker_health.json",
    "data/runtime/intelligence_state/*.json",
    "data/runtime/*_status.json",
    "data/research/*.json",
    "data/scenario_simulation/*.json",
    "data/self_reflection/*.json",
    "data/confidence_calibration/*.json",
    "data/no_trade/*.json",
    "data/memory_consolidation/*.json",
    "data/auto_repair/*.json",
    "data/execution_safety/*.json",
    "data/news_intelligence/*.json",
    "data/economic_calendar/*.json",
    "data/microstructure/*.json",
    "data/options_flow/*.json",
    "data/liquidity_map/*.json",
    "reports/*.txt",
)


def _read_json(path):
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload


def _read_text(path):
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return handle.read()[-8000:]


def _severity_from_payload(payload):
    text = json.dumps(payload, sort_keys=True, default=str) if not isinstance(payload, str) else payload
    normalized = text.upper()
    if any(token in normalized for token in ("CRITICAL", "FATAL")):
        return "CRITICAL"
    if any(token in normalized for token in ("ERROR", "TIMEOUT", "FAILED", "REJECTED")):
        return "HIGH"
    if any(token in normalized for token in ("WARN", "WARNING", "REVIEW", "LOW", "STALE", "NO_DATA")):
        return "MEDIUM"
    return "LOW"


def _status_from_payload(payload):
    if isinstance(payload, dict):
        for key in ("status", "last_status", "health", "state"):
            if payload.get(key):
                return str(payload.get(key)).upper()
    severity = _severity_from_payload(payload)
    return "WARNING" if severity in {"MEDIUM", "HIGH", "CRITICAL"} else "OK"


def _summary_from_payload(path, payload):
    if isinstance(payload, dict):
        for key in ("summary", "current_understanding", "latest_summary", "final_consensus", "next_day_bias"):
            value = payload.get(key)
            if value:
                return str(value)[:700]
        return f"{path.name} contains {len(payload)} top-level fields."
    if isinstance(payload, list):
        return f"{path.name} contains {len(payload)} records."
    text = str(payload).strip().replace("\n", " ")
    return text[:700] if text else f"{path.name} is empty."


def _findings_from_payload(payload):
    findings = []
    if isinstance(payload, dict):
        candidate_keys = (
            "key_findings",
            "findings",
            "warnings",
            "active_weaknesses",
            "recommendations",
            "top_institutional_concerns",
            "missing_data_warnings",
            "blockers",
        )
        for key in candidate_keys:
            value = payload.get(key)
            if isinstance(value, list):
                findings.extend(value[:10])
            elif value:
                findings.append(value)
    elif isinstance(payload, str):
        findings.extend(
            line.strip("- ").strip()
            for line in payload.splitlines()
            if line.strip().startswith("-")
        )
    cleaned = []
    for item in findings:
        if isinstance(item, dict):
            cleaned.append(json.dumps(item, sort_keys=True, default=str)[:500])
        else:
            cleaned.append(str(item)[:500])
    return cleaned[:20]


def _recommendations_from_payload(payload):
    if isinstance(payload, dict):
        for key in ("recommendations", "suggested_actions", "what_to_study_next", "directives"):
            value = payload.get(key)
            if isinstance(value, list):
                return value[:10]
            if value:
                return [value]
    return []


def _data_quality_from_payload(payload):
    if isinstance(payload, dict):
        for key in ("data_quality", "data_quality_score", "validation_depth_score"):
            if key in payload:
                value = payload.get(key)
                if isinstance(value, (int, float)):
                    if value >= 70:
                        return "HIGH"
                    if value >= 40:
                        return "MEDIUM"
                    return "LOW"
                return str(value).upper()
    return "UNKNOWN"


def _actionability_from_payload(payload, severity):
    base = {"LOW": 0.25, "MEDIUM": 0.5, "HIGH": 0.75, "CRITICAL": 0.9}.get(severity, 0.25)
    if isinstance(payload, dict):
        for key in ("actionability_score", "confidence", "validation_depth_score", "data_quality_score"):
            try:
                value = float(payload.get(key))
            except (TypeError, ValueError):
                continue
            if value > 1:
                value = value / 100.0
            return round(max(base, min(value, 1.0)), 3)
    return base


def report_from_file(path):
    path = Path(path)
    if "data\\report_vault" in str(path) or "data/report_vault" in str(path).replace("\\", "/"):
        return None
    try:
        payload = _read_json(path) if path.suffix.lower() == ".json" else _read_text(path)
    except Exception as exc:
        payload = {"status": "ERROR", "error": str(exc), "path": str(path)}
    severity = _severity_from_payload(payload)
    report = {
        "source_worker": path.stem,
        "report_type": "existing_report_file",
        "created_at": now_ist(),
        "status": _status_from_payload(payload),
        "severity": severity,
        "summary": _summary_from_payload(path, payload),
        "key_findings": _findings_from_payload(payload),
        "evidence": [{"source_path": str(path).replace("\\", "/"), "payload_hash": stable_hash(payload)}],
        "recommendations": _recommendations_from_payload(payload),
        "data_quality": _data_quality_from_payload(payload),
        "actionability_score": _actionability_from_payload(payload, severity),
    }
    return normalize_report(report)


def ingest_existing_reports(patterns=DEFAULT_SOURCE_PATTERNS):
    results = []
    seen = set()
    for pattern in patterns:
        for match in sorted(glob.glob(pattern)):
            path = Path(match)
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            report = report_from_file(path)
            if report:
                results.append(write_report(report))
    return results


def run_report_aggregator(state=None, state_path=None, intelligence_state=None, hours=24):
    ensure_vault()
    ingested = ingest_existing_reports()
    reports = read_recent_reports(hours=hours, limit=500)
    packet = build_intelligence_packet(reports, source_window_hours=hours)
    _atomic_write_json(PACKET_PATH, packet)
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(packet_to_text(packet), encoding="utf-8")
    result = {
        "status": "ok",
        "ingested_reports": len(ingested),
        "reports_reviewed": len(reports),
        "packet_path": str(PACKET_PATH).replace("\\", "/"),
        "summary_path": str(SUMMARY_PATH).replace("\\", "/"),
        "packet_hash": packet.get("packet_hash"),
    }
    if isinstance(state, dict):
        state["report_vault_packet_path"] = result["packet_path"]
        state["report_vault_summary_path"] = result["summary_path"]
        state["report_vault_packet_hash"] = result["packet_hash"]
    if isinstance(intelligence_state, dict) and intelligence_state is not state:
        intelligence_state.update(
            {
                "report_vault_packet_path": result["packet_path"],
                "report_vault_summary_path": result["summary_path"],
                "report_vault_packet_hash": result["packet_hash"],
            }
        )
    return result


if __name__ == "__main__":
    print(run_report_aggregator())
