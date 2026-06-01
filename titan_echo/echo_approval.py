"""ECHO approval queue for Ari-controlled mission safety gates."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_RUNTIME = REPO_ROOT / "data" / "runtime" / "echo"

ALERT_QUEUE_PATH = ECHO_RUNTIME / "alert_queue.json"
OBSERVATION_SUMMARY_PATH = ECHO_RUNTIME / "observation_summary.json"
RUNTIME_TRUTH_AUDIT_PATH = ECHO_RUNTIME / "runtime_truth_audit.json"
WRITER_OWNERSHIP_REGISTRY_PATH = ECHO_RUNTIME / "writer_ownership_registry.json"
APPROVAL_QUEUE_PATH = ECHO_RUNTIME / "approval_queue.json"
APPROVAL_HISTORY_PATH = ECHO_RUNTIME / "approval_history.jsonl"

IST = timezone(timedelta(hours=5, minutes=30))

RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
STATUSES = {"PENDING", "APPROVED", "REJECTED"}

ALLOWED_ACTIONS_BY_RISK = {
    "LOW": ["read-only audit", "health check", "status report"],
    "MEDIUM": ["code patch", "config patch", "diagnostic module addition"],
    "HIGH": ["git push", "VPS pull", "restart", "runtime behavior change"],
    "CRITICAL": ["broker execution", "risk logic", "live order behavior", "capital allocation"],
}

FORBIDDEN_ACTIONS_ALWAYS = [
    "broker execution changes",
    "risk logic changes",
    "live order changes",
    "bypass approval",
    "dangerous sandbox bypass",
]


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return default or {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def append_history(record: dict[str, Any]) -> None:
    APPROVAL_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with APPROVAL_HISTORY_PATH.open("a", encoding="utf-8") as handle:
        json.dump(record, handle, sort_keys=True)
        handle.write("\n")


def load_queue() -> dict[str, Any]:
    queue = load_json(APPROVAL_QUEUE_PATH, {"schema": "titan_echo.approval_queue.v1", "approvals": []})
    approvals = queue.get("approvals")
    if not isinstance(approvals, list):
        queue["approvals"] = []
    return queue


def save_queue(queue: dict[str, Any]) -> None:
    approvals = [item for item in queue.get("approvals", []) if isinstance(item, dict)]
    counts = Counter(str(item.get("status", "UNKNOWN")) for item in approvals)
    queue["schema"] = "titan_echo.approval_queue.v1"
    queue["timestamp_ist"] = timestamp_ist()
    queue["summary"] = {
        "total": len(approvals),
        "pending": counts.get("PENDING", 0),
        "approved": counts.get("APPROVED", 0),
        "rejected": counts.get("REJECTED", 0),
    }
    queue["approvals"] = approvals
    write_json(APPROVAL_QUEUE_PATH, queue)


def mission_id_for(title: str, summary: str, created_at: str) -> str:
    raw = f"{title}|{summary}|{created_at}"
    return "echo-mission-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def source_alert_context() -> tuple[list[str], list[str]]:
    queue = load_json(ALERT_QUEUE_PATH, {})
    alerts = queue.get("alerts", [])
    if not isinstance(alerts, list):
        return [], []
    alert_ids = []
    systems = []
    for alert in alerts[:10]:
        if not isinstance(alert, dict):
            continue
        alert_id = str(alert.get("alert_id", ""))
        if alert_id:
            alert_ids.append(alert_id)
        affected = alert.get("affected_systems", [])
        if isinstance(affected, list):
            systems.extend(str(item) for item in affected)
    return list(dict.fromkeys(alert_ids)), list(dict.fromkeys(systems))


def create_record(args: argparse.Namespace) -> dict[str, Any]:
    risk = args.risk_level.upper()
    if risk not in RISK_LEVELS:
        raise ValueError(f"Unsupported risk level: {risk}")
    created_at = timestamp_ist()
    alert_ids, affected_systems = source_alert_context()
    related_alert_ids = parse_csv(args.related_alert_ids) or alert_ids
    affected = parse_csv(args.affected_systems) or affected_systems
    mission_id = mission_id_for(args.title, args.summary, created_at)
    return {
        "mission_id": mission_id,
        "timestamp_ist": created_at,
        "title": args.title.strip(),
        "summary": args.summary.strip(),
        "risk_level": risk,
        "status": "PENDING",
        "source": args.source,
        "related_alert_ids": related_alert_ids,
        "affected_systems": affected,
        "allowed_actions": ALLOWED_ACTIONS_BY_RISK[risk],
        "forbidden_actions": FORBIDDEN_ACTIONS_ALWAYS,
        "requires_ari_approval": True,
        "approval_note": "",
        "decision_timestamp_ist": "",
    }


def command_create(args: argparse.Namespace) -> int:
    queue = load_queue()
    record = create_record(args)
    queue["approvals"].append(record)
    save_queue(queue)
    append_history({**record, "history_event": "CREATED"})
    print("TITAN ECHO approval create: PASSED")
    print(f"Mission ID: {record['mission_id']}")
    print(f"Status: {record['status']}")
    print(f"Risk level: {record['risk_level']}")
    print("Executed: False")
    return 0


def command_list(_: argparse.Namespace) -> int:
    queue = load_queue()
    approvals = [item for item in queue.get("approvals", []) if isinstance(item, dict)]
    print("TITAN ECHO approval list: PASSED")
    print(f"Approvals: {len(approvals)}")
    for item in approvals[-10:]:
        print(f"- {item.get('mission_id')} | {item.get('status')} | {item.get('risk_level')} | {item.get('title')}")
    print("Executed: False")
    return 0


def update_status(mission_id: str, status: str, note: str) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"Unsupported status: {status}")
    queue = load_queue()
    approvals = [item for item in queue.get("approvals", []) if isinstance(item, dict)]
    for item in approvals:
        if item.get("mission_id") == mission_id:
            item["status"] = status
            item["approval_note"] = note
            item["decision_timestamp_ist"] = timestamp_ist()
            queue["approvals"] = approvals
            save_queue(queue)
            append_history({**item, "history_event": status})
            return item
    raise ValueError(f"Mission not found: {mission_id}")


def command_approve(args: argparse.Namespace) -> int:
    record = update_status(args.mission_id, "APPROVED", args.note)
    print("TITAN ECHO approval approve: PASSED")
    print(f"Mission ID: {record['mission_id']}")
    print(f"Status: {record['status']}")
    print("Executed: False")
    return 0


def command_reject(args: argparse.Namespace) -> int:
    record = update_status(args.mission_id, "REJECTED", args.note)
    print("TITAN ECHO approval reject: PASSED")
    print(f"Mission ID: {record['mission_id']}")
    print(f"Status: {record['status']}")
    print("Executed: False")
    return 0


def command_summary(_: argparse.Namespace) -> int:
    queue = load_queue()
    approvals = [item for item in queue.get("approvals", []) if isinstance(item, dict)]
    statuses = Counter(str(item.get("status", "UNKNOWN")) for item in approvals)
    risks = Counter(str(item.get("risk_level", "UNKNOWN")) for item in approvals)
    print("TITAN ECHO approval summary: PASSED")
    print(f"Total approvals: {len(approvals)}")
    print(f"Status counts: {dict(sorted(statuses.items()))}")
    print(f"Risk counts: {dict(sorted(risks.items()))}")
    print("Executed: False")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TITAN ECHO approval safety gate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--title", required=True)
    create.add_argument("--risk-level", required=True, choices=sorted(RISK_LEVELS))
    create.add_argument("--summary", required=True)
    create.add_argument("--source", default="manual_cli")
    create.add_argument("--related-alert-ids", default="")
    create.add_argument("--affected-systems", default="")
    create.set_defaults(func=command_create)

    list_cmd = subparsers.add_parser("list")
    list_cmd.set_defaults(func=command_list)

    approve = subparsers.add_parser("approve")
    approve.add_argument("--mission-id", required=True)
    approve.add_argument("--note", default="Ari approved")
    approve.set_defaults(func=command_approve)

    reject = subparsers.add_parser("reject")
    reject.add_argument("--mission-id", required=True)
    reject.add_argument("--note", default="Ari rejected")
    reject.set_defaults(func=command_reject)

    summary = subparsers.add_parser("summary")
    summary.set_defaults(func=command_summary)
    return parser


def main() -> int:
    load_json(OBSERVATION_SUMMARY_PATH, {})
    load_json(RUNTIME_TRUTH_AUDIT_PATH, {})
    load_json(WRITER_OWNERSHIP_REGISTRY_PATH, {})
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
