"""Safe permanent memory writer for TITAN ECHO."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_RUNTIME = REPO_ROOT / "data" / "runtime" / "echo"

MEMORY_PATH = ECHO_RUNTIME / "echo_memory.jsonl"
MISSION_HISTORY_PATH = ECHO_RUNTIME / "titan_mission_history.jsonl"
DECISION_HISTORY_PATH = ECHO_RUNTIME / "titan_decision_history.jsonl"
CHANGE_HISTORY_PATH = ECHO_RUNTIME / "titan_change_history.jsonl"

IST = timezone(timedelta(hours=5, minutes=30))

EVENT_TYPES = {
    "mission_created",
    "mission_completed",
    "mission_failed",
    "ari_approved",
    "ari_rejected",
    "issue_detected",
    "fix_applied",
    "deployment_done",
    "rollback_done",
    "roadmap_updated",
    "architecture_observation",
    "warning",
}

RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"}

MISSION_EVENTS = {"mission_created", "mission_completed", "mission_failed"}
DECISION_EVENTS = {"ari_approved", "ari_rejected"}
CHANGE_EVENTS = {
    "fix_applied",
    "deployment_done",
    "rollback_done",
    "architecture_observation",
    "roadmap_updated",
}


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def safe_event(
    event_type: str,
    title: str,
    summary: str,
    source: str,
    risk_level: str,
    related_files: list[str],
    related_modules: list[str],
    evidence: list[str],
    decision: str,
    next_action: str,
) -> dict[str, Any]:
    normalized_type = event_type.strip()
    normalized_risk = risk_level.strip().upper()

    if normalized_type not in EVENT_TYPES:
        raise ValueError(f"Unsupported event_type: {normalized_type}")
    if normalized_risk not in RISK_LEVELS:
        raise ValueError(f"Unsupported risk_level: {normalized_risk}")

    return {
        "timestamp_ist": timestamp_ist(),
        "event_type": normalized_type,
        "title": title.strip(),
        "summary": summary.strip(),
        "source": source.strip(),
        "risk_level": normalized_risk,
        "related_files": related_files,
        "related_modules": related_modules,
        "evidence": evidence,
        "decision": decision.strip(),
        "next_action": next_action.strip(),
    }


def append_jsonl(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        json.dump(event, handle, sort_keys=True)
        handle.write("\n")


def write_event(event: dict[str, Any]) -> list[Path]:
    written = [MEMORY_PATH]
    append_jsonl(MEMORY_PATH, event)

    event_type = str(event["event_type"])
    if event_type in MISSION_EVENTS:
        append_jsonl(MISSION_HISTORY_PATH, event)
        written.append(MISSION_HISTORY_PATH)
    if event_type in DECISION_EVENTS:
        append_jsonl(DECISION_HISTORY_PATH, event)
        written.append(DECISION_HISTORY_PATH)
    if event_type in CHANGE_EVENTS:
        append_jsonl(CHANGE_HISTORY_PATH, event)
        written.append(CHANGE_HISTORY_PATH)

    return written


def load_events(path: Path = MEMORY_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            data = json.loads(stripped)
            if not isinstance(data, dict):
                raise ValueError(f"JSONL entry must be an object at line {line_number}")
            events.append(data)
    return events


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def command_add(args: argparse.Namespace) -> int:
    event = safe_event(
        event_type=args.event_type,
        title=args.title,
        summary=args.summary,
        source=args.source,
        risk_level=args.risk_level,
        related_files=parse_csv(args.related_files),
        related_modules=parse_csv(args.related_modules),
        evidence=parse_csv(args.evidence),
        decision=args.decision,
        next_action=args.next_action,
    )
    written = write_event(event)
    print("TITAN ECHO memory add: PASSED")
    print(f"Event type: {event['event_type']}")
    print(f"Risk level: {event['risk_level']}")
    print(f"Written files: {len(written)}")
    return 0


def command_list(args: argparse.Namespace) -> int:
    events = load_events()
    limit = max(1, args.limit)
    selected = events[-limit:]
    print("TITAN ECHO memory list: PASSED")
    print(f"Total events: {len(events)}")
    print(f"Shown events: {len(selected)}")
    for event in selected:
        timestamp = str(event.get("timestamp_ist", "unknown"))
        event_type = str(event.get("event_type", "unknown"))
        risk_level = str(event.get("risk_level", "UNKNOWN"))
        title = str(event.get("title", ""))
        print(f"- {timestamp} | {event_type} | {risk_level} | {title}")
    return 0


def command_summarize(_: argparse.Namespace) -> int:
    events = load_events()
    type_counts = Counter(str(event.get("event_type", "unknown")) for event in events)
    risk_counts = Counter(str(event.get("risk_level", "UNKNOWN")) for event in events)

    print("TITAN ECHO memory summarize: PASSED")
    print(f"Total events: {len(events)}")
    print(f"Event types: {dict(sorted(type_counts.items()))}")
    print(f"Risk levels: {dict(sorted(risk_counts.items()))}")
    print(f"Memory file: {relative(MEMORY_PATH)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TITAN ECHO safe memory writer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Append a memory event")
    add_parser.add_argument("--event-type", required=True, choices=sorted(EVENT_TYPES))
    add_parser.add_argument("--title", required=True)
    add_parser.add_argument("--summary", required=True)
    add_parser.add_argument("--source", default="manual_cli")
    add_parser.add_argument("--risk-level", default="LOW", choices=sorted(RISK_LEVELS))
    add_parser.add_argument("--related-files", default="")
    add_parser.add_argument("--related-modules", default="")
    add_parser.add_argument("--evidence", default="")
    add_parser.add_argument("--decision", default="")
    add_parser.add_argument("--next-action", default="")
    add_parser.set_defaults(func=command_add)

    list_parser = subparsers.add_parser("list", help="List recent memory events")
    list_parser.add_argument("--limit", type=int, default=5)
    list_parser.set_defaults(func=command_list)

    summary_parser = subparsers.add_parser("summarize", help="Summarize memory events")
    summary_parser.set_defaults(func=command_summarize)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
