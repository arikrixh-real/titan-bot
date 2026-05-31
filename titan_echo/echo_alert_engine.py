"""Generate ECHO alerts without sending Telegram messages."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_RUNTIME = REPO_ROOT / "data" / "runtime" / "echo"

LIVE_STATUS_PATH = ECHO_RUNTIME / "live_status.json"
OBSERVATIONS_PATH = ECHO_RUNTIME / "observations.json"
OBSERVATION_SUMMARY_PATH = ECHO_RUNTIME / "observation_summary.json"
RUNTIME_TRUTH_AUDIT_PATH = ECHO_RUNTIME / "runtime_truth_audit.json"
WRITER_OWNERSHIP_REGISTRY_PATH = ECHO_RUNTIME / "writer_ownership_registry.json"
ALERT_QUEUE_PATH = ECHO_RUNTIME / "alert_queue.json"
ALERT_HISTORY_PATH = ECHO_RUNTIME / "alert_history.jsonl"

IST = timezone(timedelta(hours=5, minutes=30))
LAST_SOURCE_STATUS: dict[str, dict[str, Any]] = {}

FORBIDDEN_ACTIONS = [
    "restart TITAN",
    "deploy",
    "modify broker execution",
    "modify risk logic",
    "modify scanner pipeline",
    "push GitHub",
    "send Telegram",
]


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def load_json(path: Path) -> dict[str, Any]:
    source = relative(path)
    if not path.exists():
        LAST_SOURCE_STATUS[source] = {
            "exists": False,
            "alert_status": "ALERT_STATUS_UNKNOWN",
            "evidence_status": "WAITING_FOR_DATA",
            "reason": "NO_ALERT_EVIDENCE",
        }
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        LAST_SOURCE_STATUS[source] = {
            "exists": True,
            "alert_status": "ALERT_STATUS_UNKNOWN",
            "evidence_status": "WAITING_FOR_DATA",
            "reason": f"INVALID_ALERT_EVIDENCE:{type(exc).__name__}",
        }
        return {}
    if not isinstance(data, dict):
        LAST_SOURCE_STATUS[source] = {
            "exists": True,
            "alert_status": "ALERT_STATUS_UNKNOWN",
            "evidence_status": "WAITING_FOR_DATA",
            "reason": "NO_ALERT_EVIDENCE",
        }
        return {}
    LAST_SOURCE_STATUS[source] = {
        "exists": True,
        "alert_status": "ALERT_EVIDENCE_PRESENT",
        "evidence_status": "PRESENT",
        "reason": "EVIDENCE_FILE_READ",
    }
    return data


def short_evidence(evidence: list[Any], limit: int = 4) -> list[str]:
    result = []
    for item in evidence[:limit]:
        if isinstance(item, dict):
            if "source_file" in item:
                result.append(str(item["source_file"]))
            elif "line_excerpt" in item:
                result.append(str(item["line_excerpt"])[:180])
            else:
                result.append(json.dumps(item, sort_keys=True)[:180])
        else:
            result.append(str(item)[:180])
    return result


def suggested_component(affected_systems: list[str]) -> str:
    if not affected_systems:
        return "runtime truth"
    component = affected_systems[0].replace("data/runtime/", "").replace(".json", "")
    return component.replace("_", " ")


def telegram_text(severity: str, summary: str, evidence: list[str], action: str, affected_systems: list[str]) -> str:
    evidence_text = "\n".join(f"- {item}" for item in evidence[:4]) or "- ECHO generated alert evidence unavailable."
    component = suggested_component(affected_systems)
    return (
        f"ECHO ALERT - {severity}\n\n"
        "Ari, TITAN requires attention.\n\n"
        "Issue:\n"
        f"{summary}\n\n"
        "Evidence:\n"
        f"{evidence_text}\n\n"
        "Recommended action:\n"
        f"{action}\n\n"
        "Suggested command:\n"
        f"Echo, investigate {component}"
    )


def alert_id_for(severity: str, title: str, affected_systems: list[str]) -> str:
    raw = "|".join([severity, title, ",".join(sorted(affected_systems))])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"echo-alert-{digest}"


def make_alert(
    severity: str,
    title: str,
    summary: str,
    affected_systems: list[str],
    evidence: list[Any],
    recommended_action: str,
    requires_ari_approval: bool = True,
) -> dict[str, Any]:
    evidence_lines = short_evidence(evidence)
    return {
        "alert_id": alert_id_for(severity, title, affected_systems),
        "timestamp_ist": timestamp_ist(),
        "severity": severity,
        "title": title,
        "summary": summary,
        "affected_systems": affected_systems,
        "evidence": evidence_lines,
        "recommended_action": recommended_action,
        "requires_ari_approval": requires_ari_approval,
        "forbidden_actions": FORBIDDEN_ACTIONS,
        "telegram_ready_text": telegram_text(
            severity,
            summary,
            evidence_lines,
            recommended_action,
            affected_systems,
        ),
        "status": "QUEUED",
    }


def dedupe_alerts(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for alert in alerts:
        key = (
            alert["title"],
            tuple(sorted(alert.get("affected_systems", []))),
            alert["severity"],
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(alert)
    return deduped


def alerts_from_health(live_status: dict[str, Any]) -> list[dict[str, Any]]:
    if live_status.get("overall_health") != "CRITICAL":
        return []
    return [
        make_alert(
            "CRITICAL",
            "ECHO detected CRITICAL TITAN health",
            "ECHO live status reports overall health as CRITICAL.",
            ["data/runtime/echo/live_status.json"],
            [
                f"critical_count={live_status.get('critical_count')}",
                f"warnings_count={live_status.get('warnings_count')}",
            ],
            "Run read-only runtime truth audit and confirm root cause before any patch.",
        )
    ]


def alerts_from_summary(summary: dict[str, Any]) -> list[dict[str, Any]]:
    alerts = []
    for issue in summary.get("top_issues", [])[:10]:
        if not isinstance(issue, dict):
            continue
        severity = str(issue.get("severity", "INFO"))
        if severity not in {"CRITICAL", "WARNING"}:
            continue
        source = str(issue.get("source_file", "unknown"))
        title = str(issue.get("title", "Runtime observation requires review"))
        summary_text = str(issue.get("summary", title))
        action = "Run ECHO context builder for the affected component before any patch."
        alerts.append(
            make_alert(
                severity,
                title,
                summary_text,
                [source],
                issue.get("evidence", []),
                action,
            )
        )
    return alerts


def alerts_from_truth_audit(audit: dict[str, Any]) -> list[dict[str, Any]]:
    alerts = []
    for source in audit.get("critical_sources", []):
        if not isinstance(source, dict):
            continue
        source_file = str(source.get("source_file", "unknown"))
        alerts.append(
            make_alert(
                "CRITICAL",
                f"Critical runtime truth issue: {Path(source_file).name}",
                f"{source_file} has critical truth observations.",
                [source_file],
                source.get("evidence", []),
                "Run context builder for this truth file and inspect writer ownership before any patch.",
            )
        )

    for missing in audit.get("missing_files", []):
        source_file = str(missing)
        alerts.append(
            make_alert(
                "WARNING",
                f"Missing important truth file: {Path(source_file).name}",
                f"{source_file} is missing from runtime truth files.",
                [source_file],
                ["missing_file"],
                "Inspect writer ownership for the missing truth file; do not create a duplicate writer.",
            )
        )

    for source in audit.get("warning_sources", []):
        if not isinstance(source, dict):
            continue
        source_file = str(source.get("source_file", "unknown"))
        if "worker_health" not in source_file:
            continue
        alerts.append(
            make_alert(
                "WARNING",
                "Worker health warning requires attention",
                "ECHO detected warning observations in worker health runtime truth.",
                [source_file],
                source.get("evidence", []),
                "Run read-only worker health and heartbeat audit.",
            )
        )
    return alerts


def alerts_from_registry(registry: dict[str, Any]) -> list[dict[str, Any]]:
    alerts = []
    for item in registry.get("highest_risk_truth_files", []):
        if not isinstance(item, dict):
            continue
        status = str(item.get("owner_status", "UNKNOWN"))
        truth_file = str(item.get("truth_file", "unknown"))
        if status == "CONFIRMED_OWNER":
            continue
        severity = "CRITICAL" if status == "NO_REFERENCE" else "WARNING"
        alerts.append(
            make_alert(
                severity,
                f"Ownership uncertainty: {Path(truth_file).name}",
                f"{truth_file} owner status is {status}.",
                [truth_file],
                [f"owner_status={status}", f"exists_now={item.get('exists_now')}"],
                "Confirm authoritative writer before any patch; do not create a duplicate writer.",
            )
        )
    return alerts


def alerts_from_missing_inputs() -> list[dict[str, Any]]:
    alerts = []
    for source, status in sorted(LAST_SOURCE_STATUS.items()):
        if status.get("evidence_status") != "WAITING_FOR_DATA":
            continue
        alerts.append(
            make_alert(
                "WARNING",
                f"Missing alert evidence: {Path(source).name}",
                f"{source} is unavailable; alert status is ALERT_STATUS_UNKNOWN and waiting for data.",
                [source],
                [status.get("reason", "NO_ALERT_EVIDENCE")],
                "Regenerate or transfer the missing ECHO evidence file before claiming alert health.",
                requires_ari_approval=False,
            )
        )
    return alerts


def build_alerts() -> list[dict[str, Any]]:
    LAST_SOURCE_STATUS.clear()
    live_status = load_json(LIVE_STATUS_PATH)
    load_json(OBSERVATIONS_PATH)
    observation_summary = load_json(OBSERVATION_SUMMARY_PATH)
    truth_audit = load_json(RUNTIME_TRUTH_AUDIT_PATH)
    registry = load_json(WRITER_OWNERSHIP_REGISTRY_PATH)

    alerts = []
    alerts.extend(alerts_from_health(live_status))
    alerts.extend(alerts_from_summary(observation_summary))
    alerts.extend(alerts_from_truth_audit(truth_audit))
    alerts.extend(alerts_from_registry(registry))
    alerts.extend(alerts_from_missing_inputs())
    return dedupe_alerts(alerts)


def write_queue(alerts: list[dict[str, Any]]) -> None:
    missing_inputs = [
        source
        for source, status in LAST_SOURCE_STATUS.items()
        if status.get("evidence_status") == "WAITING_FOR_DATA"
    ]
    payload = {
        "schema": "titan_echo.alert_queue.v1",
        "timestamp_ist": timestamp_ist(),
        "telegram_send_enabled": False,
        "alerts": alerts,
        "summary": {
            "total_alerts": len(alerts),
            "severity_counts": dict(Counter(alert["severity"] for alert in alerts)),
            "alert_status": "ALERT_STATUS_UNKNOWN" if missing_inputs else "ALERT_EVIDENCE_PRESENT",
            "evidence_status": "WAITING_FOR_DATA" if missing_inputs else "PRESENT",
            "missing_input_files": sorted(missing_inputs),
            "no_fake_health_claim": True,
        },
        "source_evidence_status": LAST_SOURCE_STATUS,
        "safety": {
            "read_only_alert_evidence": True,
            "telegram_send_enabled": False,
            "broker_changed": False,
            "risk_changed": False,
            "scanner_changed": False,
            "execution_changed": False,
            "runtime_behavior_changed": False,
            "master_brain_behavior_changed": False,
            "unified_brain_behavior_changed": False,
            "deploy_or_restart": False,
            "push": False,
        },
    }
    with ALERT_QUEUE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def append_history(alerts: list[dict[str, Any]]) -> None:
    ALERT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ALERT_HISTORY_PATH.open("a", encoding="utf-8") as handle:
        for alert in alerts:
            json.dump(alert, handle, sort_keys=True)
            handle.write("\n")


def main() -> int:
    alerts = build_alerts()
    write_queue(alerts)
    append_history(alerts)
    counts = Counter(alert["severity"] for alert in alerts)
    print("TITAN ECHO alert engine: PASSED")
    print(f"Alerts queued: {len(alerts)}")
    print(f"Critical alerts: {counts.get('CRITICAL', 0)}")
    print(f"Warning alerts: {counts.get('WARNING', 0)}")
    print(f"Info alerts: {counts.get('INFO', 0)}")
    print("Telegram sent: False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
