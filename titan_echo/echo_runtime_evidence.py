"""Evidence-based runtime status layer for ECHO.

This module reads runtime/status evidence files and writes only Echo runtime
evidence reports under data/runtime/echo. It does not execute commands or
inspect process tables.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
ECHO_DIR = RUNTIME_DIR / "echo"
REPORT_PATH = ECHO_DIR / "runtime_evidence_report.json"
SUMMARY_PATH = ECHO_DIR / "runtime_evidence_summary.json"
CANONICAL_RUNTIME_STATUS_PATH = RUNTIME_DIR / "titan_runtime_status.json"
IST = timezone(timedelta(hours=5, minutes=30))
FRESH_SECONDS = 900

SUBSYSTEMS = {
    "Scanner": [
        RUNTIME_DIR / "scanner_status.json",
    ],
    "Master Brain": [
        RUNTIME_DIR / "master_brain_status.json",
        RUNTIME_DIR / "brain_state.json",
    ],
    "Unified Brain": [
        RUNTIME_DIR / "unified_brain_status.json",
        RUNTIME_DIR / "unified_brain" / "unified_brain_final_status.json",
    ],
    "Runtime Workers": [
        RUNTIME_DIR / "runtime_status.json",
        RUNTIME_DIR / "worker_health.json",
        RUNTIME_DIR / "daemon_owner.json",
        RUNTIME_DIR / "runtime_owner.json",
        RUNTIME_DIR / "titan_runtime_status.json",
    ],
    "Truth Gate": [
        RUNTIME_DIR / "truth_gate_status.json",
    ],
    "Filter Engine": [
        RUNTIME_DIR / "filter_engine_diagnostics.json",
    ],
    "Selector": [
        RUNTIME_DIR / "runtime_selector_status.json",
    ],
    "Outcome Tracker": [
        RUNTIME_DIR / "outcome_tracker_status.json",
        ECHO_DIR / "outcome_id_adoption_report.json",
    ],
    "Learning": [
        ECHO_DIR / "learning_event_id_adoption_report.json",
        REPO_ROOT / "data" / "learning" / "reinforcement_learning_reports.jsonl",
    ],
    "Evolution": [
        ECHO_DIR / "evolution_event_id_adoption_report.json",
        REPO_ROOT / "data" / "memory" / "evolution_state.json",
        RUNTIME_DIR / "evolution_engine_status.json",
    ],
    "Alerts": [
        ECHO_DIR / "alert_queue.json",
    ],
    "ECHO API": [
        ECHO_DIR / "echo_api_status.json",
        ECHO_DIR / "echo_api_contract.json",
    ],
}

TIMESTAMP_KEYS = (
    "timestamp_ist",
    "timestamp",
    "updated_at",
    "last_updated",
    "last_update",
    "generated_at",
    "created_at",
    "heartbeat_at",
    "last_heartbeat",
    "last_seen",
)
STATUS_KEYS = (
    "status",
    "verdict",
    "health",
    "state",
    "runtime_status",
    "scanner_status",
    "master_brain_status",
    "unified_brain_status",
    "worker_status",
)
FAIL_TOKENS = ("FAIL", "FAILED", "ERROR", "BROKEN", "BLOCKED", "CRITICAL")
TRUE_WORKER_FAIL_TOKENS = ("ERROR", "EXCEPTION", "CRASH", "TIMEOUT", "FAILED")
SAFE_STANDBY_TOKENS = (
    "WAITING_FOR_MODE",
    "OFF_HOURS",
    "WEEKEND_MODE",
    "SKIPPED_NOT_MARKET_MODE",
    "OUTSIDE_TRADE_WINDOW_STANDBY",
    "READ_ONLY",
)
DEGRADED_TOKENS = ("DEGRADED", "WARNING", "PARTIAL")
RUNNING_TOKENS = ("RUNNING", "ACTIVE", "ALIVE")
HEALTHY_TOKENS = ("HEALTHY", "PASS", "OK", "READY", "COMPLETE", "OPERATIONAL")
STOPPED_TOKENS = ("STOPPED", "HALTED", "OFFLINE", "DOWN", "EXITED")


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None


def read_jsonl_latest(path: Path) -> Any:
    if not path.exists():
        return None
    latest: Any = None
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                latest = item
    except Exception:
        return None
    return latest


def write_echo_json(path: Path, payload: Any) -> None:
    resolved_echo = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_echo not in (resolved_path, *resolved_path.parents):
        raise ValueError("runtime evidence writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def iter_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        for child in value.values():
            found.extend(iter_dicts(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(iter_dicts(child))
    return found


def parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def latest_timestamp(payloads: list[Any], paths: list[Path]) -> datetime | None:
    candidates: list[datetime] = []
    for payload in payloads:
        for item in iter_dicts(payload):
            for key in TIMESTAMP_KEYS:
                parsed = parse_time(item.get(key))
                if parsed:
                    candidates.append(parsed)
    for path in paths:
        if path.exists():
            candidates.append(datetime.fromtimestamp(path.stat().st_mtime, IST))
    return max(candidates) if candidates else None


def status_tokens(payloads: list[Any]) -> list[str]:
    values: list[str] = []
    for payload in payloads:
        for item in iter_dicts(payload):
            for key in STATUS_KEYS:
                value = item.get(key)
                if isinstance(value, (dict, list)):
                    continue
                if value not in (None, ""):
                    values.append(str(value).upper())
    return values


def contains_any(values: list[str], tokens: tuple[str, ...]) -> bool:
    return any(token in value for value in values for token in tokens)


def numeric_values_for_keys(payloads: list[Any], keys: tuple[str, ...]) -> list[float]:
    values: list[float] = []
    for payload in payloads:
        for item in iter_dicts(payload):
            for key in keys:
                value = item.get(key)
                try:
                    if value not in (None, ""):
                        values.append(float(value))
                except Exception:
                    pass
    return values


def runtime_context(payloads: list[Any]) -> dict[str, Any]:
    values: list[str] = []
    for payload in payloads:
        for item in iter_dicts(payload):
            for value in item.values():
                if isinstance(value, str) and value.strip():
                    values.append(value.strip().upper())
            mode_allowed = item.get("mode_allowed")
            if mode_allowed is False:
                values.append("MODE_ALLOWED_FALSE")
            if item.get("is_market_open") is False:
                values.append("MARKET_CLOSED")
    safe_tokens_seen = sorted(
        {
            token
            for token in SAFE_STANDBY_TOKENS
            if any(token in value for value in values)
        }
    )
    mode_allowed_false = "MODE_ALLOWED_FALSE" in values
    market_closed = "MARKET_CLOSED" in values
    off_hours = bool(safe_tokens_seen) or mode_allowed_false or market_closed
    return {
        "expected_off_hours_standby": off_hours,
        "safe_tokens_seen": safe_tokens_seen,
        "mode_allowed_false_seen": mode_allowed_false,
        "market_closed_seen": market_closed,
    }


def true_worker_failure_found(payloads: list[Any], values: list[str], context: dict[str, Any]) -> bool:
    worker_failure_values = [
        value
        for value in values
        if any(token in value for token in TRUE_WORKER_FAIL_TOKENS)
        and "BREAKOUT_PIPELINE_INTEGRITY_ERROR" not in value
    ]
    if worker_failure_values:
        return True
    counts = numeric_values_for_keys(payloads, ("consecutive_failure_count", "error_count"))
    if context["expected_off_hours_standby"] and contains_any(values, SAFE_STANDBY_TOKENS):
        return False
    return any(count > 0 for count in counts)


def scanner_standby_evidence(payloads: list[Any]) -> bool:
    for payload in payloads:
        for item in iter_dicts(payload):
            publication = str(item.get("scanner_publication_health") or "").upper()
            loop = str(item.get("scanner_loop_health") or "").upper()
            scheduler = item.get("scheduler_active")
            if publication == "PASS" or loop == "ACTIVE" or scheduler is True:
                return True
    return False


def master_read_only_evidence(payloads: list[Any]) -> bool:
    for payload in payloads:
        for item in iter_dicts(payload):
            mode = str(item.get("master_brain_runtime_mode") or item.get("runtime_mode") or "").upper()
            if "READ_ONLY" in mode:
                return True
            if item.get("observe_only") is True:
                return True
    return False


def alert_queue_evidence(payloads: list[Any]) -> bool:
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        if payload.get("schema") == "titan_echo.alert_queue.v1" and isinstance(payload.get("alerts"), list):
            return True
        if isinstance(payload.get("summary"), dict) and "total_alerts" in payload["summary"]:
            return True
    return False


def echo_api_read_only_evidence(payloads: list[Any]) -> bool:
    api_status_present = False
    api_contract_present = False
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        if payload.get("schema") == "titan.echo.api_status.v1" and payload.get("api_mode") == "READ_ONLY":
            api_status_present = True
        if payload.get("schema") == "titan.echo.api_contract.v1" and payload.get("api_mode") == "READ_ONLY":
            endpoints = payload.get("endpoints")
            api_contract_present = isinstance(endpoints, list) and bool(endpoints)
    return api_status_present and api_contract_present


def unified_brain_shadow_only(payloads: list[Any]) -> bool:
    for payload in payloads:
        for item in iter_dicts(payload):
            if item.get("live_decision_allowed") is False:
                return True
            mode = str(item.get("mode") or item.get("promotion_state") or "").upper()
            if "SHADOW" in mode or "READ_ONLY" in mode:
                return True
    return False


def standby_status(name: str, context: dict[str, Any], freshness_seconds: int | None) -> dict[str, str]:
    if name == "Scanner":
        return {
            "status": "STANDBY",
            "confidence": "MEDIUM",
            "reason": "NO_LIVE_SCANNING_OUTSIDE_TRADE_WINDOW;WAITING_FOR_MARKET;EXPECTED_OFF_HOURS_STANDBY",
        }
    if name == "Master Brain":
        return {
            "status": "DEGRADED",
            "confidence": "MEDIUM",
            "reason": "EXPECTED_OFF_HOURS_STANDBY;WAITING_FOR_MARKET",
        }
    if name == "Runtime Workers":
        return {
            "status": "DEGRADED",
            "confidence": "MEDIUM",
            "reason": "EXPECTED_OFF_HOURS_STANDBY;WAITING_FOR_MARKET",
        }
    return {
        "status": "DEGRADED" if freshness_seconds else "NOT_PROVEN",
        "confidence": "MEDIUM" if freshness_seconds else "LOW",
        "reason": "EXPECTED_OFF_HOURS_STANDBY;WAITING_FOR_MARKET",
    }


def pid_lock_paths() -> list[Path]:
    paths = list(RUNTIME_DIR.glob("*.pid"))
    paths.extend(RUNTIME_DIR.glob("*.lock"))
    locks_dir = RUNTIME_DIR / "locks"
    if locks_dir.exists():
        paths.extend(path for path in locks_dir.iterdir() if path.is_file())
    return paths


def load_payload(path: Path) -> Any:
    if path.suffix.lower() == ".jsonl":
        return read_jsonl_latest(path)
    return read_json(path)


def evaluate_subsystem(name: str, configured_paths: list[Path]) -> dict[str, Any]:
    paths = configured_paths[:]
    if name == "Runtime Workers":
        paths.extend(pid_lock_paths())
    present_paths = [path for path in paths if path.exists()]
    payloads = [load_payload(path) for path in present_paths]
    payloads = [payload for payload in payloads if payload is not None]
    canonical_runtime_payload = load_payload(CANONICAL_RUNTIME_STATUS_PATH)
    context_payloads = payloads + ([canonical_runtime_payload] if canonical_runtime_payload is not None else [])
    latest = latest_timestamp(payloads, present_paths)
    now = datetime.now(IST)
    freshness_seconds = int((now - latest).total_seconds()) if latest else None
    values = status_tokens(payloads)
    context = runtime_context(context_payloads)
    evidence_found = bool(present_paths)
    missing = [relative(path) for path in configured_paths if not path.exists()]

    if not evidence_found:
        status = "UNKNOWN"
        confidence = "LOW"
        reason = "No configured evidence files found."
    elif name == "Runtime Workers" and true_worker_failure_found(payloads, values, context):
        status = "FAIL"
        confidence = "HIGH"
        reason = "Runtime worker evidence contains true failure token or positive failure/error count."
    elif name == "Runtime Workers" and context["expected_off_hours_standby"]:
        standby = standby_status(name, context, freshness_seconds)
        status = standby["status"]
        confidence = standby["confidence"]
        reason = standby["reason"]
    elif name == "Scanner" and context["expected_off_hours_standby"] and scanner_standby_evidence(context_payloads):
        standby = standby_status(name, context, freshness_seconds)
        status = standby["status"]
        confidence = standby["confidence"]
        reason = standby["reason"]
    elif name == "Master Brain" and context["expected_off_hours_standby"] and master_read_only_evidence(context_payloads):
        standby = standby_status(name, context, freshness_seconds)
        status = standby["status"]
        confidence = standby["confidence"]
        reason = standby["reason"]
    elif name == "Alerts" and alert_queue_evidence(payloads):
        status = "DEGRADED"
        confidence = "MEDIUM"
        reason = "ALERT_QUEUE_PRESENT_READ_ONLY_NOT_DELIVERY_PROOF"
    elif name == "ECHO API" and echo_api_read_only_evidence(payloads):
        status = "DEGRADED"
        confidence = "MEDIUM"
        reason = "API_CONTRACT_PRESENT_READ_ONLY_NOT_SERVER_PROOF"
    elif name == "Unified Brain" and unified_brain_shadow_only(payloads):
        status = "DEGRADED"
        confidence = "MEDIUM"
        reason = "UNIFIED_BRAIN_SHADOW_ONLY_NOT_LIVE_DECISION_PROOF"
    elif contains_any(values, FAIL_TOKENS):
        status = "FAIL"
        confidence = "HIGH"
        reason = "A current evidence status/verdict field contains a failure token."
    elif contains_any(values, STOPPED_TOKENS):
        status = "STOPPED"
        confidence = "HIGH" if latest else "MEDIUM"
        reason = "Evidence status/verdict indicates stopped/offline."
    elif latest is None:
        status = "UNKNOWN"
        confidence = "LOW"
        reason = "Evidence files exist, but no timestamp or file mtime could prove recency."
    elif freshness_seconds is not None and freshness_seconds > FRESH_SECONDS:
        status = "STALE"
        confidence = "MEDIUM"
        reason = f"Latest evidence is older than {FRESH_SECONDS} seconds."
    elif contains_any(values, RUNNING_TOKENS):
        status = "RUNNING"
        confidence = "HIGH"
        reason = "Fresh evidence contains a running/active status token."
    elif contains_any(values, HEALTHY_TOKENS):
        status = "HEALTHY"
        confidence = "HIGH"
        reason = "Fresh evidence contains a healthy/pass/ready status token."
    elif contains_any(values, DEGRADED_TOKENS):
        status = "DEGRADED"
        confidence = "MEDIUM"
        reason = "Fresh evidence contains degraded/warning/partial token."
    else:
        status = "NOT_PROVEN"
        confidence = "LOW"
        reason = "Evidence exists, but status fields do not prove running or health."

    return {
        "subsystem": name,
        "evidence_found": evidence_found,
        "latest_timestamp": latest.isoformat() if latest else None,
        "freshness_seconds": freshness_seconds,
        "status": status,
        "confidence": confidence,
        "evidence_files": [
            {"path": relative(path), "exists": path.exists()}
            for path in paths
        ],
        "missing_evidence": missing,
        "status_values_seen": values[:20],
        "reason": reason,
        "classification_context": context,
    }


def verdict_for(summary_counts: dict[str, int], subsystems: dict[str, dict[str, Any]]) -> str:
    core = [
        subsystems["Scanner"]["status"],
        subsystems["Master Brain"]["status"],
        subsystems["Runtime Workers"]["status"],
        subsystems["Unified Brain"]["status"],
    ]
    if all(status in ("RUNNING", "HEALTHY") for status in core):
        return "RUNTIME_PROVEN"
    if summary_counts["fail_count"] > 0:
        return "PARTIAL_RUNTIME_EVIDENCE"
    if summary_counts.get("standby_count", 0) > 0:
        return "EXPECTED_OFF_HOURS_STANDBY"
    if summary_counts["stale_count"] > 0:
        return "STALE_RUNTIME_EVIDENCE"
    if any(status not in ("UNKNOWN", "NOT_PROVEN") for status in core):
        return "PARTIAL_RUNTIME_EVIDENCE"
    return "RUNTIME_NOT_PROVEN"


def build_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    subsystem_list = [evaluate_subsystem(name, paths) for name, paths in SUBSYSTEMS.items()]
    subsystems = {item["subsystem"]: item for item in subsystem_list}
    status_counts = {
        "stale_count": sum(1 for item in subsystem_list if item["status"] == "STALE"),
        "standby_count": sum(1 for item in subsystem_list if item["status"] == "STANDBY"),
        "unknown_count": sum(1 for item in subsystem_list if item["status"] in ("UNKNOWN", "NOT_PROVEN")),
        "fail_count": sum(1 for item in subsystem_list if item["status"] == "FAIL"),
        "healthy_count": sum(1 for item in subsystem_list if item["status"] in ("RUNNING", "HEALTHY")),
        "degraded_count": sum(1 for item in subsystem_list if item["status"] == "DEGRADED"),
    }
    report = {
        "schema": "titan.echo.runtime_evidence_report.v1",
        "timestamp_ist": timestamp_ist(),
        "freshness_rule_seconds": FRESH_SECONDS,
        "truth_rule": "RUNNING/HEALTHY requires fresh timestamp plus supportive status evidence.",
        "safety": {
            "read_only_evidence_layer": True,
            "reads_env": False,
            "shell_execution": False,
            "codex_execution": False,
            "writes_outside_echo_runtime": False,
            "broker_risk_scanner_changes": False,
            "deploy_or_restart": False,
        },
        "subsystems": subsystems,
    }
    summary = {
        "schema": "titan.echo.runtime_evidence_summary.v1",
        "timestamp_ist": report["timestamp_ist"],
        "titan_runtime_status": subsystems["Runtime Workers"]["status"],
        "scanner_runtime_status": subsystems["Scanner"]["status"],
        "master_brain_runtime_status": subsystems["Master Brain"]["status"],
        "worker_runtime_status": subsystems["Runtime Workers"]["status"],
        "unified_brain_runtime_status": subsystems["Unified Brain"]["status"],
        **status_counts,
        "current_runtime_truth_verdict": verdict_for(status_counts, subsystems),
        "still_unknown_systems": [
            item["subsystem"]
            for item in subsystem_list
            if item["status"] in ("UNKNOWN", "NOT_PROVEN")
        ],
        "safety": report["safety"],
    }
    return report, summary


def generate_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    report, summary = build_reports()
    write_echo_json(REPORT_PATH, report)
    write_echo_json(SUMMARY_PATH, summary)
    return report, summary


def main() -> None:
    _, summary = generate_reports()
    print("ECHO runtime evidence generated.")
    print(f"titan_runtime_status={summary['titan_runtime_status']}")
    print(f"scanner_runtime_status={summary['scanner_runtime_status']}")
    print(f"master_brain_runtime_status={summary['master_brain_runtime_status']}")
    print(f"worker_runtime_status={summary['worker_runtime_status']}")
    print(f"unified_brain_runtime_status={summary['unified_brain_runtime_status']}")
    print(f"stale_count={summary['stale_count']}")
    print(f"standby_count={summary['standby_count']}")
    print(f"unknown_count={summary['unknown_count']}")
    print(f"fail_count={summary['fail_count']}")
    print(f"degraded_count={summary['degraded_count']}")
    print(f"healthy_count={summary['healthy_count']}")
    print(f"current_runtime_truth_verdict={summary['current_runtime_truth_verdict']}")
    print("still_unknown_systems=" + ", ".join(summary["still_unknown_systems"]))


if __name__ == "__main__":
    main()
