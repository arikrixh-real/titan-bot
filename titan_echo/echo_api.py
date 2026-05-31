"""Read-only local ECHO API surface.

This module is safe to import without starting a server. When FastAPI is
installed it defines an ``app`` with GET-only routes. When FastAPI is missing
it still exposes fallback functions for local callers.
"""

from __future__ import annotations

import importlib.util
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from titan_echo.echo_api_auth import PROTECTED_ENDPOINTS, require_echo_api_key
from titan_echo.echo_api_status import build_status, read_sources


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
IST = timezone(timedelta(hours=5, minutes=30))

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None
if FASTAPI_AVAILABLE:
    from fastapi import Depends, FastAPI
else:  # pragma: no cover - depends on local dependency set
    Depends = None  # type: ignore[assignment, misc]
    FastAPI = None  # type: ignore[assignment, misc]


READ_ONLY_EVIDENCE = {
    "answer": ECHO_DIR / "echo_answer.json",
    "mission_center": ECHO_DIR / "echo_mission_center.json",
    "query_router": ECHO_DIR / "echo_query_router.json",
    "approval_queue": ECHO_DIR / "approval_queue.json",
    "mission_plan": ECHO_DIR / "mission_plan.json",
    "verification_report": ECHO_DIR / "verification_report.json",
}
MISSION_PLAN_PATH = ECHO_DIR / "mission_plan.json"
APPROVAL_QUEUE_PATH = ECHO_DIR / "approval_queue.json"
APPROVAL_HISTORY_PATH = ECHO_DIR / "approval_history.jsonl"
APPROVED_MISSIONS_PATH = ECHO_DIR / "approved_missions.json"
REJECTED_MISSIONS_PATH = ECHO_DIR / "rejected_missions.json"
EXECUTION_READINESS_REPORT_PATH = ECHO_DIR / "execution_readiness_report.json"
EXECUTION_PREVIEW_PATH = ECHO_DIR / "execution_preview.json"
EXECUTION_AUTHORIZATION_PATH = ECHO_DIR / "execution_authorization.json"
EXECUTION_LOCK_PATH = ECHO_DIR / "execution_lock.json"
EXECUTION_EVIDENCE_PATH = ECHO_DIR / "execution_evidence.json"
EXECUTION_LEDGER_PATH = ECHO_DIR / "execution_ledger.json"
EXECUTION_POLICY_PATH = ECHO_DIR / "execution_policy.json"
EXECUTION_GATE_PATH = ECHO_DIR / "execution_gate.json"
CHATGPT_CONNECTION_READINESS_PATH = ECHO_DIR / "chatgpt_connection_readiness.json"
CHAT_SESSION_PATH = ECHO_DIR / "chat_session.json"
ECHO_CONTEXT_PATH = ECHO_DIR / "echo_context.json"
ECHO_RUNTIME_CONTEXT_PATH = ECHO_DIR / "echo_runtime_context.json"
ECHO_EVIDENCE_CONTEXT_PATH = ECHO_DIR / "echo_evidence_context.json"
JARVIS_STATUS_PATH = ECHO_DIR / "jarvis_status.json"
JARVIS_RESPONSE_PATH = ECHO_DIR / "jarvis_response.json"
JARVIS_INVESTIGATION_PATH = ECHO_DIR / "jarvis_investigation.json"
JARVIS_ASK_RESPONSE_PATH = ECHO_DIR / "jarvis_ask_response.json"
JARVIS_RUNTIME_INTELLIGENCE_PATH = ECHO_DIR / "jarvis_runtime_intelligence.json"
JARVIS_DEEP_TITAN_CONTEXT_PATH = ECHO_DIR / "jarvis_deep_titan_context.json"
CHATGPT_BRIDGE_READINESS_PATH = ECHO_DIR / "chatgpt_bridge_readiness.json"
CHATGPT_CONNECTOR_PLAN_PATH = ECHO_DIR / "chatgpt_connector_plan.json"
CHATGPT_HANDSHAKE_STATUS_PATH = ECHO_DIR / "chatgpt_handshake_status.json"
CHATGPT_EVIDENCE_CONTRACT_PATH = ECHO_DIR / "chatgpt_evidence_contract.json"
TITAN_RUNTIME_CONTEXT_PATH = ECHO_DIR / "titan_runtime_context.json"
TITAN_HEALTH_SUMMARY_PATH = ECHO_DIR / "titan_health_summary.json"
TITAN_WORKER_SUMMARY_PATH = ECHO_DIR / "titan_worker_summary.json"
TITAN_SCANNER_SUMMARY_PATH = ECHO_DIR / "titan_scanner_summary.json"
TITAN_TRADE_SUMMARY_PATH = ECHO_DIR / "titan_trade_summary.json"
TITAN_BRAIN_SUMMARY_PATH = ECHO_DIR / "titan_brain_summary.json"
VALID_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

SECRET_MARKERS = (
    "api_key",
    "apikey",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
)


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key).lower()
            if any(marker in text_key for marker in SECRET_MARKERS):
                clean[key] = "REDACTED"
            else:
                clean[key] = _sanitize(item)
        return clean
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _write_echo_json(path: Path, payload: Any) -> None:
    resolved_echo = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_echo not in (resolved_path, *resolved_path.parents):
        raise ValueError("ECHO API bridge writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_echo_jsonl(path: Path, payload: dict[str, Any]) -> None:
    resolved_echo = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_echo not in (resolved_path, *resolved_path.parents):
        raise ValueError("ECHO API bridge writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")


def _evidence_payload(name: str) -> dict[str, Any]:
    path = READ_ONLY_EVIDENCE[name]
    data = _sanitize(_read_json(path))
    return {
        "source": _relative(path),
        "data": data,
        "status": "EVIDENCE_PRESENT" if data is not None else "UNKNOWN",
    }


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part) for part in parts)
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _load_approval_queue() -> dict[str, Any]:
    queue = _read_json(APPROVAL_QUEUE_PATH)
    if not isinstance(queue, dict):
        queue = {"schema": "titan_echo.approval_queue.v1", "approvals": []}
    approvals = queue.get("approvals")
    if not isinstance(approvals, list):
        queue["approvals"] = []
    return queue


def _save_approval_queue(queue: dict[str, Any]) -> None:
    approvals = [item for item in queue.get("approvals", []) if isinstance(item, dict)]
    counts = Counter(str(item.get("status", "UNKNOWN")).upper() for item in approvals)
    queue["schema"] = "titan_echo.approval_queue.v1"
    queue["timestamp_ist"] = _timestamp_ist()
    queue["summary"] = {
        "total": len(approvals),
        "pending": counts.get("PENDING", 0),
        "approved": counts.get("APPROVED", 0),
        "rejected": counts.get("REJECTED", 0),
    }
    queue["approvals"] = approvals
    _write_echo_json(APPROVAL_QUEUE_PATH, queue)


def _load_mission_plan() -> dict[str, Any]:
    mission_plan = _read_json(MISSION_PLAN_PATH)
    return mission_plan if isinstance(mission_plan, dict) else {}


def _load_mission_collection(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return {"schema": "titan.echo.approval_decision_missions.v1", "missions": []}
    missions = payload.get("missions")
    if not isinstance(missions, list):
        payload["missions"] = []
    return payload


def _mission_collection_items(path: Path) -> list[dict[str, Any]]:
    payload = _load_mission_collection(path)
    missions = payload.get("missions")
    return [item for item in missions if isinstance(item, dict)] if isinstance(missions, list) else []


def _mission_collection_contains(path: Path, mission_id: str, approval_id: str) -> bool:
    for item in _mission_collection_items(path):
        if str(item.get("mission_id") or "") == mission_id and str(item.get("approval_id") or "") == approval_id:
            return True
        mission = item.get("mission") if isinstance(item.get("mission"), dict) else {}
        if str(mission.get("mission_id") or "") == mission_id and str(mission.get("approval_id") or "") == approval_id:
            return True
        approval = item.get("approval_record") if isinstance(item.get("approval_record"), dict) else {}
        if str(approval.get("mission_id") or "") == mission_id and str(approval.get("approval_id") or "") == approval_id:
            return True
    return False


def _append_mission_decision(path: Path, decision: str, record: dict[str, Any], mission_plan: dict[str, Any]) -> None:
    payload = _load_mission_collection(path)
    mission_snapshot = mission_plan.get("current_mission") if isinstance(mission_plan.get("current_mission"), dict) else {}
    item = {
        "approval_id": record.get("approval_id"),
        "mission_id": record.get("mission_id"),
        "decision": decision,
        "decision_timestamp_ist": record.get("decision_timestamp_ist"),
        "approval_note": record.get("approval_note", ""),
        "approval_record": record,
        "mission": mission_snapshot,
        "safety": _decision_safety(),
    }
    payload["schema"] = "titan.echo.approval_decision_missions.v1"
    payload["timestamp_ist"] = _timestamp_ist()
    payload["missions"].append(item)
    payload["summary"] = {"total": len(payload["missions"])}
    _write_echo_json(path, payload)


def _decision_safety() -> dict[str, bool]:
    return {
        "execution_allowed": False,
        "codex_execution": False,
        "shell_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "broker_changed": False,
        "risk_changed": False,
        "execution_changed": False,
        "scanner_changed": False,
        "master_brain_changed": False,
        "unified_brain_changed": False,
        "runtime_workers_changed": False,
    }


def _jarvis_safety() -> dict[str, bool]:
    return {
        "codex_execution": False,
        "shell_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "titan_runtime_changed": False,
        "actual_execution_permitted": False,
        "broker_changed": False,
        "risk_changed": False,
        "scanner_changed": False,
        "master_brain_changed": False,
        "runtime_workers_changed": False,
        "trade_execution_permitted": False,
        "chatgpt_connection_enabled": False,
        "external_api_calls_enabled": False,
        "public_exposure_allowed": False,
    }


def _jarvis_core_safety() -> dict[str, bool]:
    return {
        "codex_execution": False,
        "shell_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "titan_runtime_changed": False,
        "actual_execution_permitted": False,
        "broker_changed": False,
        "risk_changed": False,
        "scanner_changed": False,
        "master_brain_changed": False,
        "runtime_workers_changed": False,
        "trade_execution_permitted": False,
    }


PHASE_OMEGA_EVIDENCE_FILES = {
    "mission_plan": MISSION_PLAN_PATH,
    "approval_queue": APPROVAL_QUEUE_PATH,
    "approval_history": APPROVAL_HISTORY_PATH,
    "approved_missions": APPROVED_MISSIONS_PATH,
    "rejected_missions": REJECTED_MISSIONS_PATH,
    "execution_readiness_report": EXECUTION_READINESS_REPORT_PATH,
    "execution_preview": EXECUTION_PREVIEW_PATH,
    "execution_authorization": EXECUTION_AUTHORIZATION_PATH,
    "execution_lock": EXECUTION_LOCK_PATH,
    "execution_evidence": EXECUTION_EVIDENCE_PATH,
    "execution_ledger": EXECUTION_LEDGER_PATH,
    "execution_policy": EXECUTION_POLICY_PATH,
    "execution_gate": EXECUTION_GATE_PATH,
    "chatgpt_connection_readiness": CHATGPT_CONNECTION_READINESS_PATH,
}

TITAN_RUNTIME_EVIDENCE_FILES = {
    "titan_runtime_status": REPO_ROOT / "data" / "runtime" / "titan_runtime_status.json",
    "worker_health": REPO_ROOT / "data" / "runtime" / "worker_health.json",
    "scanner_status": REPO_ROOT / "data" / "runtime" / "scanner_status.json",
    "runtime_selector_status": REPO_ROOT / "data" / "runtime" / "runtime_selector_status.json",
    "setup_engine_status": REPO_ROOT / "data" / "runtime" / "setup_engine_status.json",
    "master_brain_status": REPO_ROOT / "data" / "runtime" / "master_brain_status.json",
    "outcome_tracker_status": REPO_ROOT / "data" / "runtime" / "outcome_tracker_status.json",
    "dashboard_sync_status": REPO_ROOT / "data" / "runtime" / "dashboard_sync_status.json",
    "ohlc_refresh_status": REPO_ROOT / "data" / "runtime" / "ohlc_refresh_status.json",
    "filter_engine_diagnostics": REPO_ROOT / "data" / "runtime" / "filter_engine_diagnostics.json",
    "near_pass_setups": REPO_ROOT / "data" / "runtime" / "near_pass_setups.json",
    "trade_contract_diagnostics": REPO_ROOT / "data" / "runtime" / "trade_contract_diagnostics.json",
    "trade_journal_diagnostics": REPO_ROOT / "data" / "runtime" / "trade_journal_diagnostics.json",
    "outcome_tracker_diagnostics": REPO_ROOT / "data" / "runtime" / "outcome_tracker_diagnostics.json",
    "paper_account": REPO_ROOT / "data" / "paper_trading" / "paper_account.json",
    "active_trades": REPO_ROOT / "data" / "journals" / "active_trades.csv",
    "trade_outcomes": REPO_ROOT / "data" / "journals" / "trade_outcomes.csv",
    "evolution_status": REPO_ROOT / "data" / "runtime" / "evolution_status.json",
    "learning_status": REPO_ROOT / "data" / "runtime" / "learning_status.json",
    "news_status": REPO_ROOT / "data" / "runtime" / "news_status.json",
    "memory_consolidation_status": REPO_ROOT / "data" / "runtime" / "memory_consolidation_status.json",
}


def _read_jsonl(path: Path) -> list[Any] | None:
    if not path.exists():
        return None
    records: list[Any] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            text = line.strip()
            if text:
                records.append(json.loads(text))
    except Exception:
        return None
    return records


def _read_phase_omega_source(path: Path) -> Any:
    if path.suffix.lower() == ".jsonl":
        return _read_jsonl(path)
    return _read_json(path)


def _read_csv_rows(path: Path) -> list[dict[str, Any]] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return None


def _read_runtime_source(path: Path) -> Any:
    if path.suffix.lower() == ".csv":
        return _read_csv_rows(path)
    return _read_phase_omega_source(path)


def _evidence_record(name: str, path: Path) -> dict[str, Any]:
    data = _sanitize(_read_phase_omega_source(path))
    return {
        "name": name,
        "source": _relative(path),
        "status": "EVIDENCE_PRESENT" if data is not None else "UNKNOWN_NOT_PROVEN",
        "data": data,
    }


def _phase_omega_evidence_map() -> dict[str, dict[str, Any]]:
    return {
        name: _evidence_record(name, path)
        for name, path in PHASE_OMEGA_EVIDENCE_FILES.items()
    }


def _titan_evidence_record(name: str, path: Path) -> dict[str, Any]:
    data = _sanitize(_read_runtime_source(path))
    return {
        "name": name,
        "source": _relative(path),
        "status": "EVIDENCE_PRESENT" if data is not None else "UNKNOWN_NOT_PROVEN",
        "data": data,
    }


def _titan_runtime_evidence_map() -> dict[str, dict[str, Any]]:
    return {
        name: _titan_evidence_record(name, path)
        for name, path in TITAN_RUNTIME_EVIDENCE_FILES.items()
    }


def _record_status(record: dict[str, Any]) -> str:
    data = record.get("data")
    if not isinstance(data, dict):
        return "UNKNOWN_NOT_PROVEN"
    value = data.get("status") or data.get("health") or data.get("state") or data.get("runtime_status")
    return str(value) if value not in (None, "") else "UNKNOWN_NOT_PROVEN"


def _source_statuses(evidence: dict[str, dict[str, Any]], names: list[str]) -> dict[str, dict[str, Any]]:
    return {
        name: {
            "source": evidence[name]["source"],
            "status": evidence[name]["status"],
        }
        for name in names
        if name in evidence
    }


def _missing_sources(evidence: dict[str, dict[str, Any]], names: list[str]) -> list[str]:
    return [name for name in names if evidence.get(name, {}).get("status") != "EVIDENCE_PRESENT"]


def _titan_summary_status(evidence: dict[str, dict[str, Any]], names: list[str]) -> str:
    return "EVIDENCE_PRESENT" if not _missing_sources(evidence, names) else "UNKNOWN_NOT_PROVEN"


def _count_rows(value: Any) -> int | str:
    if isinstance(value, list):
        return len(value)
    return "UNKNOWN_NOT_PROVEN"


def build_titan_health_summary() -> dict[str, Any]:
    evidence = _titan_runtime_evidence_map()
    names = [
        "titan_runtime_status",
        "worker_health",
        "dashboard_sync_status",
        "ohlc_refresh_status",
        "filter_engine_diagnostics",
    ]
    payload = {
        "schema": "titan.echo.titan_health_summary.v1",
        "status": _titan_summary_status(evidence, names),
        "runtime_status": _record_status(evidence["titan_runtime_status"]),
        "worker_health": _record_status(evidence["worker_health"]),
        "dashboard_sync_status": _record_status(evidence["dashboard_sync_status"]),
        "ohlc_refresh_status": _record_status(evidence["ohlc_refresh_status"]),
        "filter_engine_diagnostics_status": _record_status(evidence["filter_engine_diagnostics"]),
        "source_files": _source_statuses(evidence, names),
        "unknowns": _missing_sources(evidence, names),
        "safety": _jarvis_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(TITAN_HEALTH_SUMMARY_PATH, payload)
    return payload


def build_titan_worker_summary() -> dict[str, Any]:
    evidence = _titan_runtime_evidence_map()
    names = ["worker_health"]
    payload = {
        "schema": "titan.echo.titan_worker_summary.v1",
        "status": _titan_summary_status(evidence, names),
        "worker_health": evidence["worker_health"]["data"] if evidence["worker_health"]["status"] == "EVIDENCE_PRESENT" else "UNKNOWN_NOT_PROVEN",
        "source_files": _source_statuses(evidence, names),
        "unknowns": _missing_sources(evidence, names),
        "safety": _jarvis_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(TITAN_WORKER_SUMMARY_PATH, payload)
    return payload


def build_titan_scanner_summary() -> dict[str, Any]:
    evidence = _titan_runtime_evidence_map()
    names = [
        "scanner_status",
        "runtime_selector_status",
        "setup_engine_status",
        "filter_engine_diagnostics",
        "near_pass_setups",
    ]
    payload = {
        "schema": "titan.echo.titan_scanner_summary.v1",
        "status": _titan_summary_status(evidence, names),
        "scanner_status": _record_status(evidence["scanner_status"]),
        "runtime_selector_status": _record_status(evidence["runtime_selector_status"]),
        "setup_engine_status": _record_status(evidence["setup_engine_status"]),
        "near_pass_setup_count": _count_rows(evidence["near_pass_setups"]["data"]),
        "source_files": _source_statuses(evidence, names),
        "unknowns": _missing_sources(evidence, names),
        "safety": _jarvis_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(TITAN_SCANNER_SUMMARY_PATH, payload)
    return payload


def build_titan_trade_summary() -> dict[str, Any]:
    evidence = _titan_runtime_evidence_map()
    names = [
        "trade_contract_diagnostics",
        "trade_journal_diagnostics",
        "outcome_tracker_diagnostics",
        "paper_account",
        "active_trades",
        "trade_outcomes",
    ]
    payload = {
        "schema": "titan.echo.titan_trade_summary.v1",
        "status": _titan_summary_status(evidence, names),
        "active_trade_count": _count_rows(evidence["active_trades"]["data"]),
        "trade_outcome_count": _count_rows(evidence["trade_outcomes"]["data"]),
        "paper_account_status": _record_status(evidence["paper_account"]),
        "trade_contract_diagnostics_status": _record_status(evidence["trade_contract_diagnostics"]),
        "trade_journal_diagnostics_status": _record_status(evidence["trade_journal_diagnostics"]),
        "outcome_tracker_diagnostics_status": _record_status(evidence["outcome_tracker_diagnostics"]),
        "source_files": _source_statuses(evidence, names),
        "unknowns": _missing_sources(evidence, names),
        "safety": _jarvis_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(TITAN_TRADE_SUMMARY_PATH, payload)
    return payload


def build_titan_brain_summary() -> dict[str, Any]:
    evidence = _titan_runtime_evidence_map()
    names = ["master_brain_status", "setup_engine_status", "outcome_tracker_status"]
    payload = {
        "schema": "titan.echo.titan_brain_summary.v1",
        "status": _titan_summary_status(evidence, names),
        "master_brain_status": _record_status(evidence["master_brain_status"]),
        "setup_engine_status": _record_status(evidence["setup_engine_status"]),
        "outcome_tracker_status": _record_status(evidence["outcome_tracker_status"]),
        "source_files": _source_statuses(evidence, names),
        "unknowns": _missing_sources(evidence, names),
        "safety": _jarvis_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(TITAN_BRAIN_SUMMARY_PATH, payload)
    return payload


def build_titan_runtime_context() -> dict[str, Any]:
    evidence = _titan_runtime_evidence_map()
    payload = {
        "schema": "titan.echo.titan_runtime_context.v1",
        "status": "TITAN_RUNTIME_CONTEXT_LOCAL_ONLY",
        "runtime": {
            "titan_runtime_status": _record_status(evidence["titan_runtime_status"]),
            "health": build_titan_health_summary(),
            "workers": build_titan_worker_summary(),
            "scanner": build_titan_scanner_summary(),
            "trades": build_titan_trade_summary(),
            "brain": build_titan_brain_summary(),
        },
        "source_files": _source_statuses(evidence, list(TITAN_RUNTIME_EVIDENCE_FILES)),
        "unknowns": _missing_sources(evidence, list(TITAN_RUNTIME_EVIDENCE_FILES)),
        "truth_rule": "UNKNOWN_NOT_PROVEN when unavailable from TITAN runtime evidence files.",
        "safety": _jarvis_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(TITAN_RUNTIME_CONTEXT_PATH, payload)
    return payload


def get_titan_status() -> dict[str, Any]:
    return build_titan_runtime_context()


def get_titan_health() -> dict[str, Any]:
    return build_titan_health_summary()


def get_titan_workers() -> dict[str, Any]:
    return build_titan_worker_summary()


def get_titan_scanner() -> dict[str, Any]:
    return build_titan_scanner_summary()


def get_titan_trades() -> dict[str, Any]:
    return build_titan_trade_summary()


def get_titan_brain() -> dict[str, Any]:
    return build_titan_brain_summary()


def get_titan_runtime_context() -> dict[str, Any]:
    return build_titan_runtime_context()


def _deep_titan_context_summary(evidence: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "runtime": _record_status(evidence["titan_runtime_status"]),
        "health": {
            "worker_health": _record_status(evidence["worker_health"]),
            "dashboard_sync_status": _record_status(evidence["dashboard_sync_status"]),
            "ohlc_refresh_status": _record_status(evidence["ohlc_refresh_status"]),
        },
        "scanner": {
            "scanner_status": _record_status(evidence["scanner_status"]),
            "runtime_selector_status": _record_status(evidence["runtime_selector_status"]),
            "setup_engine_status": _record_status(evidence["setup_engine_status"]),
            "near_pass_setup_count": _count_rows(evidence["near_pass_setups"]["data"]),
        },
        "trades": {
            "active_trade_count": _count_rows(evidence["active_trades"]["data"]),
            "trade_outcome_count": _count_rows(evidence["trade_outcomes"]["data"]),
            "paper_account_status": _record_status(evidence["paper_account"]),
            "trade_contract_diagnostics_status": _record_status(evidence["trade_contract_diagnostics"]),
            "trade_journal_diagnostics_status": _record_status(evidence["trade_journal_diagnostics"]),
            "outcome_tracker_diagnostics_status": _record_status(evidence["outcome_tracker_diagnostics"]),
        },
        "brain": {
            "master_brain_status": _record_status(evidence["master_brain_status"]),
            "setup_engine_status": _record_status(evidence["setup_engine_status"]),
            "outcome_tracker_status": _record_status(evidence["outcome_tracker_status"]),
        },
        "evolution": _record_status(evidence["evolution_status"]),
        "learning": _record_status(evidence["learning_status"]),
        "memory": _record_status(evidence["memory_consolidation_status"]),
        "news": _record_status(evidence["news_status"]),
        "dashboard": _record_status(evidence["dashboard_sync_status"]),
    }


def build_jarvis_deep_titan_context() -> dict[str, Any]:
    evidence = _titan_runtime_evidence_map()
    names = list(TITAN_RUNTIME_EVIDENCE_FILES)
    payload = {
        "schema": "titan.echo.jarvis_deep_titan_context.v1",
        "status": _titan_summary_status(evidence, names),
        "summary": _deep_titan_context_summary(evidence),
        "evidence": evidence,
        "source_files": _source_statuses(evidence, names),
        "unknowns": _missing_sources(evidence, names),
        "truth_rule": "UNKNOWN_NOT_PROVEN when unavailable from TITAN runtime evidence files.",
        "safety": _jarvis_core_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(JARVIS_DEEP_TITAN_CONTEXT_PATH, payload)
    return payload


def build_jarvis_runtime_intelligence() -> dict[str, Any]:
    echo_evidence = _phase_omega_evidence_map()
    titan_context = build_jarvis_deep_titan_context()
    governance = _runtime_intelligence_summary(echo_evidence)
    unknowns = [
        f"echo:{name}"
        for name, record in echo_evidence.items()
        if record["status"] == "UNKNOWN_NOT_PROVEN"
    ]
    unknowns.extend(f"titan:{name}" for name in titan_context["unknowns"])
    payload = {
        "schema": "titan.echo.jarvis_runtime_intelligence.v1",
        "status": "EVIDENCE_PRESENT" if not unknowns else "PARTIAL_EVIDENCE",
        "echo_context": _runtime_intelligence_summary(echo_evidence),
        "titan_context": titan_context["summary"],
        "governance_context": governance,
        "safety_context": _jarvis_core_safety(),
        "unknowns": unknowns,
        "safety": _jarvis_core_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(JARVIS_RUNTIME_INTELLIGENCE_PATH, payload)
    return payload


def _source_status_value(evidence: dict[str, dict[str, Any]], name: str) -> str:
    record = evidence.get(name, {})
    data = record.get("data")
    if not isinstance(data, dict):
        return "UNKNOWN_NOT_PROVEN"
    value = data.get("status") or data.get("gate_decision") or data.get("approval_gate")
    return str(value) if value not in (None, "") else "UNKNOWN_NOT_PROVEN"


def _current_mission_from_evidence(evidence: dict[str, dict[str, Any]]) -> Any:
    data = evidence.get("mission_plan", {}).get("data")
    if not isinstance(data, dict):
        return "UNKNOWN_NOT_PROVEN"
    mission = data.get("current_mission") or data.get("active_mission") or data.get("mission")
    return mission if mission is not None else "UNKNOWN_NOT_PROVEN"


def _approval_state_from_evidence(evidence: dict[str, dict[str, Any]]) -> Any:
    queue = evidence.get("approval_queue", {}).get("data")
    if not isinstance(queue, dict):
        return "UNKNOWN_NOT_PROVEN"
    approvals = queue.get("approvals")
    if not isinstance(approvals, list):
        return "UNKNOWN_NOT_PROVEN"
    counts = Counter(str(item.get("status", "UNKNOWN_NOT_PROVEN")).upper() for item in approvals if isinstance(item, dict))
    return {
        "total": sum(counts.values()),
        "pending": counts.get("PENDING", 0),
        "approved": counts.get("APPROVED", 0),
        "rejected": counts.get("REJECTED", 0),
    }


def _governance_chain_from_evidence(evidence: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {
        "readiness_state": _source_status_value(evidence, "execution_readiness_report"),
        "preview_state": _source_status_value(evidence, "execution_preview"),
        "authorization_state": _source_status_value(evidence, "execution_authorization"),
        "lock_state": _source_status_value(evidence, "execution_lock"),
        "evidence_state": _source_status_value(evidence, "execution_evidence"),
        "ledger_state": _source_status_value(evidence, "execution_ledger"),
        "policy_state": _source_status_value(evidence, "execution_policy"),
        "execution_gate_state": _source_status_value(evidence, "execution_gate"),
    }


def _runtime_intelligence_summary(evidence: dict[str, dict[str, Any]]) -> dict[str, Any]:
    governance_chain = _governance_chain_from_evidence(evidence)
    return {
        "current_mission": _current_mission_from_evidence(evidence),
        "approval_state": _approval_state_from_evidence(evidence),
        "governance_chain": governance_chain,
        "execution_gate_state": governance_chain["execution_gate_state"],
        "readiness_state": governance_chain["readiness_state"],
        "preview_state": governance_chain["preview_state"],
        "authorization_state": governance_chain["authorization_state"],
        "lock_state": governance_chain["lock_state"],
        "evidence_state": governance_chain["evidence_state"],
        "ledger_state": governance_chain["ledger_state"],
        "chatgpt_readiness_state": _source_status_value(evidence, "chatgpt_connection_readiness"),
    }


def build_chat_session() -> dict[str, Any]:
    payload = {
        "schema": "titan.echo.chat_session.v1",
        "session_id": _stable_id("echo-chat-session", _timestamp_ist()),
        "status": "CHAT_SESSION_LOCAL_ONLY",
        "chatgpt_connection_enabled": False,
        "external_api_calls_enabled": False,
        "public_exposure_allowed": False,
        "created_at_ist": _timestamp_ist(),
        "safety": _jarvis_safety(),
    }
    _write_echo_json(CHAT_SESSION_PATH, payload)
    return payload


def get_chat_session() -> dict[str, Any]:
    payload = _read_json(CHAT_SESSION_PATH)
    if not isinstance(payload, dict):
        payload = build_chat_session()
    payload["safety"] = _jarvis_safety()
    return payload


def post_chat_session_create() -> dict[str, Any]:
    return build_chat_session()


def build_echo_context() -> dict[str, Any]:
    evidence = _phase_omega_evidence_map()
    payload = {
        "schema": "titan.echo.context.v1",
        "status": "ECHO_CONTEXT_LOCAL_ONLY",
        "runtime_intelligence": _runtime_intelligence_summary(evidence),
        "sources": {name: {"source": record["source"], "status": record["status"]} for name, record in evidence.items()},
        "truth_rule": "UNKNOWN_NOT_PROVEN when unavailable from runtime evidence files.",
        "safety": _jarvis_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(ECHO_CONTEXT_PATH, payload)
    return payload


def build_echo_runtime_context() -> dict[str, Any]:
    evidence = _phase_omega_evidence_map()
    payload = {
        "schema": "titan.echo.runtime_context.v1",
        "status": "ECHO_RUNTIME_CONTEXT_LOCAL_ONLY",
        "runtime_intelligence": _runtime_intelligence_summary(evidence),
        "safety": _jarvis_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(ECHO_RUNTIME_CONTEXT_PATH, payload)
    return payload


def build_echo_evidence_context() -> dict[str, Any]:
    evidence = _phase_omega_evidence_map()
    payload = {
        "schema": "titan.echo.evidence_context.v1",
        "status": "ECHO_EVIDENCE_CONTEXT_LOCAL_ONLY",
        "evidence": evidence,
        "truth_rule": "UNKNOWN_NOT_PROVEN when unavailable from runtime evidence files.",
        "safety": _jarvis_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(ECHO_EVIDENCE_CONTEXT_PATH, payload)
    return payload


def get_echo_context() -> dict[str, Any]:
    return build_echo_context()


def get_echo_runtime() -> dict[str, Any]:
    return build_echo_runtime_context()


def get_echo_evidence() -> dict[str, Any]:
    return build_echo_evidence_context()


QUESTION_CATEGORY_KEYWORDS = {
    "titan_runtime_status": ("what is titan doing", "titan doing", "runtime status"),
    "titan_health": ("titan healthy", "titan health", "healthy"),
    "titan_workers": ("workers", "worker", "alive"),
    "titan_scanner": ("scanner", "scan"),
    "titan_trades": ("open trades", "taking trades", "trades", "trade"),
    "titan_brain": ("master brain", "brain"),
    "titan_blockers": ("what is blocked", "blocked", "not taking trades", "blockers"),
    "titan_status": ("titan", "system"),
    "echo_status": ("echo",),
    "mission_status": ("mission",),
    "approval_status": ("approval", "approved", "rejected", "pending"),
    "governance_status": ("governance", "chain", "policy"),
    "execution_gate_status": ("execution gate", "gate", "execution"),
    "chatgpt_readiness": ("chatgpt", "readiness", "connection"),
    "blocked_actions": ("blocked", "forbidden", "not allowed", "prevented"),
    "safety_status": ("safety", "safe", "permissions"),
}

JARVIS_ASK_CATEGORY_KEYWORDS = {
    "titan_summary": ("what is titan doing", "titan summary", "summarize titan", "titan status"),
    "titan_health": ("healthy", "health"),
    "titan_runtime": ("runtime", "running"),
    "titan_scanner": ("scanner", "scan"),
    "titan_workers": ("workers", "worker", "alive"),
    "titan_trades": ("open trades", "taking trades", "trades", "trade"),
    "titan_brain": ("master brain", "brain"),
    "titan_evolution": ("evolution", "evolve"),
    "titan_learning": ("learning", "learn"),
    "titan_memory": ("memory", "consolidation"),
    "titan_news": ("news",),
    "titan_dashboard": ("dashboard",),
    "governance_status": ("governance", "chain", "policy"),
    "execution_blockers": ("blocked", "blockers", "not taking trades", "why is titan not taking trades"),
    "chatgpt_bridge_readiness": ("chatgpt", "bridge", "readiness"),
    "safety_status": ("safety", "safe", "permissions"),
}


def _interpret_question_category(question: str) -> str | None:
    text = question.lower()
    for category, keywords in QUESTION_CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category
    return None


def _interpret_jarvis_ask_category(question: str) -> str:
    text = question.lower()
    if any(keyword in text for keyword in JARVIS_ASK_CATEGORY_KEYWORDS["execution_blockers"]):
        return "execution_blockers"
    for category, keywords in JARVIS_ASK_CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category
    return "unknown"


def _ask_status_from_unknowns(unknowns: list[str], evidence_used: list[str]) -> str:
    if not evidence_used:
        return "UNKNOWN_NOT_PROVEN"
    return "PARTIAL_EVIDENCE" if unknowns else "EVIDENCE_PRESENT"


def _ask_unknown_summary() -> str:
    return "ECHO does not have verified TITAN runtime evidence for this yet."


def _deep_context_section(deep_context: dict[str, Any], section: str) -> Any:
    summary = deep_context.get("summary")
    if not isinstance(summary, dict):
        return "UNKNOWN_NOT_PROVEN"
    return summary.get(section, "UNKNOWN_NOT_PROVEN")


def _evidence_names_for_category(category: str) -> list[str]:
    mapping = {
        "titan_summary": list(TITAN_RUNTIME_EVIDENCE_FILES),
        "titan_health": ["titan_runtime_status", "worker_health", "dashboard_sync_status", "ohlc_refresh_status", "filter_engine_diagnostics"],
        "titan_runtime": ["titan_runtime_status"],
        "titan_scanner": ["scanner_status", "runtime_selector_status", "setup_engine_status", "filter_engine_diagnostics", "near_pass_setups"],
        "titan_workers": ["worker_health"],
        "titan_trades": ["trade_contract_diagnostics", "trade_journal_diagnostics", "outcome_tracker_diagnostics", "paper_account", "active_trades", "trade_outcomes"],
        "titan_brain": ["master_brain_status", "setup_engine_status", "outcome_tracker_status"],
        "titan_evolution": ["evolution_status"],
        "titan_learning": ["learning_status"],
        "titan_memory": ["memory_consolidation_status"],
        "titan_news": ["news_status"],
        "titan_dashboard": ["dashboard_sync_status"],
        "governance_status": list(PHASE_OMEGA_EVIDENCE_FILES),
        "execution_blockers": list(PHASE_OMEGA_EVIDENCE_FILES) + list(TITAN_RUNTIME_EVIDENCE_FILES),
        "chatgpt_bridge_readiness": ["execution_ledger", "execution_gate", "execution_policy"],
        "safety_status": ["endpoint_safety_policy"],
    }
    return mapping.get(category, [])


def _ask_details_for_category(
    category: str,
    runtime_intelligence: dict[str, Any],
    deep_context: dict[str, Any],
    bridge: dict[str, Any],
) -> Any:
    if category == "titan_summary":
        return deep_context.get("summary", {})
    if category == "titan_health":
        return _deep_context_section(deep_context, "health")
    if category == "titan_runtime":
        return {"runtime": _deep_context_section(deep_context, "runtime")}
    if category == "titan_scanner":
        return _deep_context_section(deep_context, "scanner")
    if category == "titan_workers":
        return {"workers": _deep_context_section(deep_context, "health").get("worker_health", "UNKNOWN_NOT_PROVEN") if isinstance(_deep_context_section(deep_context, "health"), dict) else "UNKNOWN_NOT_PROVEN"}
    if category == "titan_trades":
        return _deep_context_section(deep_context, "trades")
    if category == "titan_brain":
        return _deep_context_section(deep_context, "brain")
    if category == "titan_evolution":
        return {"evolution": _deep_context_section(deep_context, "evolution")}
    if category == "titan_learning":
        return {"learning": _deep_context_section(deep_context, "learning")}
    if category == "titan_memory":
        return {"memory": _deep_context_section(deep_context, "memory")}
    if category == "titan_news":
        return {"news": _deep_context_section(deep_context, "news")}
    if category == "titan_dashboard":
        return {"dashboard": _deep_context_section(deep_context, "dashboard")}
    if category == "governance_status":
        return runtime_intelligence.get("governance_context", {})
    if category == "execution_blockers":
        return {
            "governance": runtime_intelligence.get("governance_context", {}),
            "missing_evidence": runtime_intelligence.get("unknowns", []),
            "actual_execution_permitted": False,
            "trade_execution_permitted": False,
        }
    if category == "chatgpt_bridge_readiness":
        return bridge
    if category == "safety_status":
        return _jarvis_core_safety()
    return {}


def _ask_summary_for_category(category: str, status: str) -> str:
    if category == "unknown":
        return "ECHO does not have verified evidence for this question yet."
    if status == "UNKNOWN_NOT_PROVEN":
        return _ask_unknown_summary()
    if status == "PARTIAL_EVIDENCE":
        return "ECHO found partial evidence only. Missing evidence is listed in unknowns."
    return "ECHO found verified local evidence for this question. See details and evidence_used."


def _ask_blockers(category: str, unknowns: list[str], bridge: dict[str, Any]) -> list[str]:
    blockers = list(unknowns)
    if category == "execution_blockers":
        blockers.extend(["actual_execution_permitted=false", "trade_execution_permitted=false"])
    if category == "chatgpt_bridge_readiness":
        blockers.extend(str(item) for item in bridge.get("blockers", []) if item)
    return sorted(set(blockers))


def _ask_next_safe_step(category: str, status: str, blockers: list[str]) -> str:
    if blockers:
        return "Resolve or generate the missing local evidence files before drawing operational conclusions."
    if category == "chatgpt_bridge_readiness" and status == "EVIDENCE_PRESENT":
        return "Proceed with local chatbox wiring while keeping ChatGPT connection, external APIs, and public exposure disabled."
    return ""


def _route_exists(path: str, method: str) -> bool:
    app_obj = globals().get("app")
    if app_obj is None:
        return False
    for route in getattr(app_obj, "routes", []):
        if getattr(route, "path", "") == path and method.upper() in getattr(route, "methods", set()):
            return True
    return False


def build_chatgpt_bridge_readiness() -> dict[str, Any]:
    ledger = _read_json(EXECUTION_LEDGER_PATH)
    gate = _read_json(EXECUTION_GATE_PATH)
    policy = _read_json(EXECUTION_POLICY_PATH)
    ledger = ledger if isinstance(ledger, dict) else {}
    gate = gate if isinstance(gate, dict) else {}
    policy = policy if isinstance(policy, dict) else {}
    checks = {
        "governance_chain_complete": ledger.get("status") == "GOVERNANCE_CHAIN_COMPLETE",
        "execution_gate_blocks_execution": gate.get("gate_decision") == "BLOCK_EXECUTION",
        "jarvis_ask_endpoint_exists": _route_exists("/jarvis/ask", "POST") or "post_jarvis_ask" in globals(),
        "auth_required": "/jarvis/ask" in PROTECTED_ENDPOINTS and "/chatgpt/bridge/readiness" in PROTECTED_ENDPOINTS,
        "localhost_only": True,
        "public_exposure_false": False is False,
        "external_api_false": False is False,
        "actual_execution_false": policy.get("actual_execution_permitted") is False or gate.get("safety", {}).get("actual_execution_permitted") is False,
    }
    blockers = [name for name, passed in checks.items() if not passed]
    ready = not blockers
    payload = {
        "schema": "titan.echo.chatgpt_bridge_readiness.v1",
        "status": "CHATGPT_BRIDGE_READY_LOCAL_ONLY" if ready else "NOT_READY",
        "chatgpt_bridge_ready": ready,
        "chatgpt_connection_enabled": False,
        "external_api_calls_enabled": False,
        "public_exposure_allowed": False,
        "checks": checks,
        "blockers": blockers,
        "source_files": {
            "execution_ledger": {"source": _relative(EXECUTION_LEDGER_PATH), "status": "EVIDENCE_PRESENT" if ledger else "UNKNOWN_NOT_PROVEN"},
            "execution_gate": {"source": _relative(EXECUTION_GATE_PATH), "status": "EVIDENCE_PRESENT" if gate else "UNKNOWN_NOT_PROVEN"},
            "execution_policy": {"source": _relative(EXECUTION_POLICY_PATH), "status": "EVIDENCE_PRESENT" if policy else "UNKNOWN_NOT_PROVEN"},
        },
        "safety": _jarvis_core_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(CHATGPT_BRIDGE_READINESS_PATH, payload)
    return payload


def get_chatgpt_bridge_readiness() -> dict[str, Any]:
    return build_chatgpt_bridge_readiness()


def _connector_safety() -> dict[str, bool]:
    return {
        "chatgpt_connection_enabled": False,
        "external_api_calls_enabled": False,
        "public_exposure_allowed": False,
        "actual_execution_permitted": False,
        "codex_execution": False,
        "shell_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "titan_runtime_changed": False,
    }


def build_chatgpt_connector_plan() -> dict[str, Any]:
    payload = {
        "schema": "titan.echo.chatgpt_connector_plan.v1",
        "status": "CHATGPT_CONNECTOR_READY_LOCAL_ONLY",
        "enabled_mode": "LOCAL_MANUAL_BRIDGE",
        "supported_future_modes": {
            "LOCAL_MANUAL_BRIDGE": {
                "status": "ENABLED_LOCAL_ONLY",
                "description": "Manual local copy/paste bridge between ChatGPT and protected ECHO endpoints.",
            },
            "SECURE_RELAY_BRIDGE": {
                "status": "DESIGN_ONLY_DISABLED",
                "description": "Future authenticated relay design; no relay is configured or exposed.",
            },
            "CUSTOM_GPT_ACTION_BRIDGE": {
                "status": "DESIGN_ONLY_DISABLED",
                "description": "Future Custom GPT action design; no public URL or external API integration is enabled.",
            },
        },
        "constraints": {
            "public_url_configured": False,
            "ports_opened": False,
            "openai_api_calls": False,
            "external_api_calls_enabled": False,
            "chatgpt_connection_enabled": False,
        },
        "safety": _connector_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(CHATGPT_CONNECTOR_PLAN_PATH, payload)
    return payload


def get_chatgpt_connector_plan() -> dict[str, Any]:
    return build_chatgpt_connector_plan()


def build_chatgpt_handshake_status() -> dict[str, Any]:
    gate = _read_json(EXECUTION_GATE_PATH)
    gate = gate if isinstance(gate, dict) else {}
    checks = {
        "echo_api_alive": True,
        "auth_required": (
            "/chatgpt/connector/plan" in PROTECTED_ENDPOINTS
            and "/chatgpt/handshake/status" in PROTECTED_ENDPOINTS
            and "/chatgpt/handshake/test" in PROTECTED_ENDPOINTS
        ),
        "jarvis_ask_available": _route_exists("/jarvis/ask", "POST") or "post_jarvis_ask" in globals(),
        "chatgpt_bridge_readiness_available": _route_exists("/chatgpt/bridge/readiness", "GET") or "get_chatgpt_bridge_readiness" in globals(),
        "execution_gate_blocks_execution": gate.get("gate_decision") == "BLOCK_EXECUTION",
        "public_exposure_disabled": True,
        "external_api_calls_disabled": True,
    }
    blockers = [name for name, passed in checks.items() if not passed]
    payload = {
        "schema": "titan.echo.chatgpt_handshake_status.v1",
        "status": "CHATGPT_CONNECTOR_READY_LOCAL_ONLY" if not blockers else "NOT_READY",
        "checks": checks,
        "blockers": blockers,
        "enabled_mode": "LOCAL_MANUAL_BRIDGE",
        "chatgpt_connection_enabled": False,
        "external_api_calls_enabled": False,
        "public_exposure_allowed": False,
        "actual_execution_permitted": False,
        "source_files": {
            "execution_gate": {
                "source": _relative(EXECUTION_GATE_PATH),
                "status": "EVIDENCE_PRESENT" if gate else "UNKNOWN_NOT_PROVEN",
            }
        },
        "safety": _connector_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(CHATGPT_HANDSHAKE_STATUS_PATH, payload)
    return payload


def get_chatgpt_handshake_status() -> dict[str, Any]:
    existing = _read_json(CHATGPT_HANDSHAKE_STATUS_PATH)
    if isinstance(existing, dict):
        existing["safety"] = _connector_safety()
        return existing
    return build_chatgpt_handshake_status()


def post_chatgpt_handshake_test() -> dict[str, Any]:
    return build_chatgpt_handshake_status()


CHATGPT_EVIDENCE_GROUPS = {
    "governance evidence": list(PHASE_OMEGA_EVIDENCE_FILES),
    "runtime evidence": ["titan_runtime_status", "runtime_selector_status", "setup_engine_status", "ohlc_refresh_status"],
    "scanner evidence": ["scanner_status", "filter_engine_diagnostics", "near_pass_setups"],
    "worker evidence": ["worker_health"],
    "trade evidence": [
        "trade_contract_diagnostics",
        "trade_journal_diagnostics",
        "outcome_tracker_diagnostics",
        "paper_account",
        "active_trades",
        "trade_outcomes",
    ],
    "master brain evidence": ["master_brain_status", "outcome_tracker_status"],
    "evolution evidence": ["evolution_status"],
    "learning evidence": ["learning_status"],
    "memory evidence": ["memory_consolidation_status"],
    "news evidence": ["news_status"],
    "dashboard evidence": ["dashboard_sync_status"],
}


def _evidence_source_for_name(name: str) -> str:
    if name in PHASE_OMEGA_EVIDENCE_FILES:
        return _relative(PHASE_OMEGA_EVIDENCE_FILES[name])
    if name in TITAN_RUNTIME_EVIDENCE_FILES:
        return _relative(TITAN_RUNTIME_EVIDENCE_FILES[name])
    return "UNKNOWN_NOT_PROVEN"


def _evidence_contract_group(group_name: str, names: list[str]) -> dict[str, Any]:
    return {
        "evidence_type": group_name,
        "source_files": {name: _evidence_source_for_name(name) for name in names},
        "confidence_source": "LOCAL_RUNTIME_FILE_PRESENCE_AND_SCHEMA_FIELDS",
        "truth_source": "ECHO_READ_ONLY_EVIDENCE_FILES",
        "missing_file_truth": "UNKNOWN_NOT_PROVEN",
    }


def build_chatgpt_evidence_contract() -> dict[str, Any]:
    payload = {
        "schema": "titan.echo.chatgpt_evidence_contract.v1",
        "status": "CHATGPT_EVIDENCE_CONTRACT_READY_LOCAL_ONLY",
        "chatgpt_brain_expected": True,
        "echo_role": "EVIDENCE_LAYER",
        "jarvis_role": "CHATGPT_SIDE",
        "chatgpt_connection_enabled": False,
        "external_api_calls_enabled": False,
        "public_exposure_allowed": False,
        "evidence_groups": {
            group: _evidence_contract_group(group, names)
            for group, names in CHATGPT_EVIDENCE_GROUPS.items()
        },
        "truth_rule": "Never claim live integration exists; missing files return UNKNOWN_NOT_PROVEN.",
        "safety": _connector_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(CHATGPT_EVIDENCE_CONTRACT_PATH, payload)
    return payload


def get_chatgpt_evidence_contract() -> dict[str, Any]:
    return build_chatgpt_evidence_contract()


def get_chatgpt_evidence_catalog() -> dict[str, Any]:
    contract = build_chatgpt_evidence_contract()
    endpoints = {
        "governance evidence": ["/echo/context", "/echo/runtime", "/echo/evidence"],
        "runtime evidence": ["/titan/status", "/titan/runtime/context"],
        "scanner evidence": ["/titan/scanner"],
        "worker evidence": ["/titan/workers"],
        "trade evidence": ["/titan/trades"],
        "master brain evidence": ["/titan/brain"],
        "evolution evidence": ["/jarvis/ask"],
        "learning evidence": ["/jarvis/ask"],
        "memory evidence": ["/jarvis/ask"],
        "news evidence": ["/jarvis/ask"],
        "dashboard evidence": ["/jarvis/ask"],
    }
    catalog = []
    for evidence_type, group in contract["evidence_groups"].items():
        catalog.append(
            {
                "endpoint_name": endpoints.get(evidence_type, []),
                "evidence_type": evidence_type,
                "source_files": group["source_files"],
                "confidence_source": group["confidence_source"],
                "truth_source": group["truth_source"],
            }
        )
    return {
        "schema": "titan.echo.chatgpt_evidence_catalog.v1",
        "status": "CHATGPT_EVIDENCE_CATALOG_READY_LOCAL_ONLY",
        "chatgpt_brain_expected": True,
        "echo_role": "EVIDENCE_LAYER",
        "jarvis_role": "CHATGPT_SIDE",
        "chatgpt_connection_enabled": False,
        "catalog": catalog,
        "safety": _connector_safety(),
        "generated_at_ist": _timestamp_ist(),
    }


def get_chatgpt_integration_status() -> dict[str, Any]:
    bridge = build_chatgpt_bridge_readiness()
    checks = {
        "governance_complete": bridge.get("checks", {}).get("governance_chain_complete") is True,
        "execution_blocked": bridge.get("checks", {}).get("execution_gate_blocks_execution") is True,
        "jarvis_ask_exists": bridge.get("checks", {}).get("jarvis_ask_endpoint_exists") is True,
        "auth_enabled": (
            "/chatgpt/evidence/contract" in PROTECTED_ENDPOINTS
            and "/chatgpt/evidence/catalog" in PROTECTED_ENDPOINTS
            and "/chatgpt/integration/status" in PROTECTED_ENDPOINTS
        ),
        "localhost_only": True,
        "public_exposure_disabled": True,
        "external_api_disabled": True,
    }
    blockers = [name for name, passed in checks.items() if not passed]
    return {
        "schema": "titan.echo.chatgpt_integration_status.v1",
        "status": "CHATGPT_EVIDENCE_INTEGRATION_READY" if not blockers else "NOT_READY",
        "checks": checks,
        "blockers": blockers,
        "chatgpt_brain_expected": True,
        "echo_role": "EVIDENCE_LAYER",
        "jarvis_role": "CHATGPT_SIDE",
        "chatgpt_connection_enabled": False,
        "external_api_calls_enabled": False,
        "public_exposure_allowed": False,
        "live_integration_exists": False,
        "safety": _connector_safety(),
        "generated_at_ist": _timestamp_ist(),
    }


def build_jarvis_ask_response(question: str = "") -> dict[str, Any]:
    category = _interpret_jarvis_ask_category(question)
    runtime_intelligence = build_jarvis_runtime_intelligence()
    deep_context = build_jarvis_deep_titan_context()
    bridge = build_chatgpt_bridge_readiness()
    evidence_used = _evidence_names_for_category(category)
    unknowns = []
    if category == "unknown":
        unknowns = ["unsupported_question_category"]
    elif category == "safety_status":
        unknowns = []
    else:
        source_files = deep_context.get("source_files", {})
        echo_sources = _source_statuses(_phase_omega_evidence_map(), list(PHASE_OMEGA_EVIDENCE_FILES))
        titan_names = set(TITAN_RUNTIME_EVIDENCE_FILES)
        echo_names = set(PHASE_OMEGA_EVIDENCE_FILES)
        unknowns.extend(
            name
            for name in evidence_used
            if name in titan_names and source_files.get(name, {}).get("status") == "UNKNOWN_NOT_PROVEN"
        )
        unknowns.extend(
            name
            for name in evidence_used
            if name in echo_names and echo_sources.get(name, {}).get("status") == "UNKNOWN_NOT_PROVEN"
        )
    if category == "chatgpt_bridge_readiness" and bridge["status"] != "CHATGPT_BRIDGE_READY_LOCAL_ONLY":
        unknowns.extend(str(item) for item in bridge.get("blockers", []))
    status = _ask_status_from_unknowns(unknowns, evidence_used)
    details = _ask_details_for_category(category, runtime_intelligence, deep_context, bridge)
    blockers = _ask_blockers(category, unknowns, bridge)
    payload = {
        "schema": "titan.echo.jarvis_ask.v1",
        "status": status,
        "question": question,
        "interpreted_category": category,
        "summary": _ask_summary_for_category(category, status),
        "details": details if status != "UNKNOWN_NOT_PROVEN" else {},
        "evidence_used": evidence_used,
        "unknowns": sorted(set(unknowns)),
        "blockers": blockers,
        "recommended_next_safe_step": _ask_next_safe_step(category, status, blockers),
        "chatgpt_bridge": {
            "chatgpt_bridge_ready": bridge["status"] == "CHATGPT_BRIDGE_READY_LOCAL_ONLY",
            "chatgpt_connection_enabled": False,
            "external_api_calls_enabled": False,
            "public_exposure_allowed": False,
        },
        "safety": _jarvis_core_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(JARVIS_ASK_RESPONSE_PATH, payload)
    return payload


def post_jarvis_ask(payload: dict[str, Any]) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    return build_jarvis_ask_response(str(body.get("question") or ""))


def _unknown_titan_answer() -> str:
    return "ECHO does not have verified TITAN runtime evidence for this yet."


def _titan_answer_payload(category: str) -> tuple[str, Any, list[str], list[str]]:
    if category == "titan_runtime_status":
        summary = build_titan_runtime_context()
        if summary["unknowns"]:
            return "UNKNOWN_NOT_PROVEN", _unknown_titan_answer(), list(summary["source_files"]), summary["unknowns"]
        return summary["status"], summary["runtime"], list(summary["source_files"]), []
    if category == "titan_health":
        summary = build_titan_health_summary()
        if summary["status"] == "UNKNOWN_NOT_PROVEN":
            return "UNKNOWN_NOT_PROVEN", _unknown_titan_answer(), list(summary["source_files"]), summary["unknowns"]
        return summary["status"], summary, list(summary["source_files"]), []
    if category == "titan_workers":
        summary = build_titan_worker_summary()
        if summary["status"] == "UNKNOWN_NOT_PROVEN":
            return "UNKNOWN_NOT_PROVEN", _unknown_titan_answer(), list(summary["source_files"]), summary["unknowns"]
        return summary["status"], summary["worker_health"], list(summary["source_files"]), []
    if category == "titan_scanner":
        summary = build_titan_scanner_summary()
        if summary["status"] == "UNKNOWN_NOT_PROVEN":
            return "UNKNOWN_NOT_PROVEN", _unknown_titan_answer(), list(summary["source_files"]), summary["unknowns"]
        return summary["status"], summary, list(summary["source_files"]), []
    if category == "titan_trades":
        summary = build_titan_trade_summary()
        if summary["status"] == "UNKNOWN_NOT_PROVEN":
            return "UNKNOWN_NOT_PROVEN", _unknown_titan_answer(), list(summary["source_files"]), summary["unknowns"]
        return summary["status"], summary, list(summary["source_files"]), []
    if category == "titan_brain":
        summary = build_titan_brain_summary()
        if summary["status"] == "UNKNOWN_NOT_PROVEN":
            return "UNKNOWN_NOT_PROVEN", _unknown_titan_answer(), list(summary["source_files"]), summary["unknowns"]
        return summary["status"], summary, list(summary["source_files"]), []
    if category == "titan_blockers":
        summary = build_titan_runtime_context()
        blockers = {
            "missing_evidence": summary["unknowns"],
            "trade_execution_permitted": False,
            "actual_execution_permitted": False,
        }
        status = "UNKNOWN_NOT_PROVEN" if summary["unknowns"] else "EVIDENCE_PRESENT"
        answer = _unknown_titan_answer() if status == "UNKNOWN_NOT_PROVEN" else blockers
        return status, answer, list(summary["source_files"]), summary["unknowns"]
    return "UNKNOWN_NOT_PROVEN", _unknown_titan_answer(), [], ["unsupported_titan_question_category"]


def _jarvis_answer_for_category(category: str | None, summary: dict[str, Any], evidence: dict[str, dict[str, Any]]) -> tuple[str, Any, list[str], list[str]]:
    if category is None:
        return (
            "UNKNOWN_NOT_PROVEN",
            "ECHO does not have verified evidence for this question yet.",
            [],
            ["unsupported_question_category"],
        )
    if category.startswith("titan_") and category != "titan_status":
        return _titan_answer_payload(category)
    if category == "titan_status":
        return _titan_answer_payload("titan_runtime_status")
    if category == "echo_status":
        return "ECHO_CONTEXT_LOCAL_ONLY", "ECHO local context is available from runtime evidence files only.", ["echo_context"], []
    if category == "mission_status":
        return "EVIDENCE_PRESENT" if summary["current_mission"] != "UNKNOWN_NOT_PROVEN" else "UNKNOWN_NOT_PROVEN", summary["current_mission"], ["mission_plan"], []
    if category == "approval_status":
        return "EVIDENCE_PRESENT" if summary["approval_state"] != "UNKNOWN_NOT_PROVEN" else "UNKNOWN_NOT_PROVEN", summary["approval_state"], ["approval_queue"], []
    if category == "governance_status":
        return "EVIDENCE_PRESENT", summary["governance_chain"], [name for name in PHASE_OMEGA_EVIDENCE_FILES if name.startswith("execution_")], []
    if category == "execution_gate_status":
        return summary["execution_gate_state"], summary["execution_gate_state"], ["execution_gate"], []
    if category == "chatgpt_readiness":
        return summary["chatgpt_readiness_state"], summary["chatgpt_readiness_state"], ["chatgpt_connection_readiness"], []
    if category == "blocked_actions":
        blocked = [key for key, value in _jarvis_safety().items() if value is False]
        return "EVIDENCE_PRESENT", blocked, ["endpoint_safety_policy"], []
    if category == "safety_status":
        return "EVIDENCE_PRESENT", _jarvis_safety(), ["endpoint_safety_policy"], []
    return "UNKNOWN_NOT_PROVEN", "ECHO does not have verified evidence for this question yet.", [], ["unsupported_question_category"]


def build_jarvis_response(question: str = "") -> dict[str, Any]:
    evidence = _phase_omega_evidence_map()
    summary = _runtime_intelligence_summary(evidence)
    category = _interpret_question_category(question)
    status, answer, evidence_used, unknowns = _jarvis_answer_for_category(category, summary, evidence)
    payload = {
        "schema": "titan.echo.jarvis_response.v1",
        "status": status,
        "question": question,
        "interpreted_category": category or "unsupported",
        "answer": answer,
        "evidence_used": evidence_used,
        "unknowns": unknowns,
        "safety": _jarvis_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(JARVIS_RESPONSE_PATH, payload)
    return payload


def get_jarvis_status() -> dict[str, Any]:
    evidence = _phase_omega_evidence_map()
    payload = {
        "schema": "titan.echo.jarvis_status.v1",
        "status": "JARVIS_LOCAL_ONLY",
        "allowed_question_categories": sorted(QUESTION_CATEGORY_KEYWORDS),
        "runtime_intelligence": _runtime_intelligence_summary(evidence),
        "safety": _jarvis_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(JARVIS_STATUS_PATH, payload)
    return payload


def get_jarvis_question() -> dict[str, Any]:
    return build_jarvis_response("")


def post_jarvis_question(payload: dict[str, Any]) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    return build_jarvis_response(str(body.get("question") or ""))


def get_jarvis_explain() -> dict[str, Any]:
    return build_jarvis_response("governance status")


def get_jarvis_investigate() -> dict[str, Any]:
    evidence = _phase_omega_evidence_map()
    payload = {
        "schema": "titan.echo.jarvis_investigation.v1",
        "status": "JARVIS_INVESTIGATION_LOCAL_ONLY",
        "runtime_intelligence": _runtime_intelligence_summary(evidence),
        "evidence_used": list(evidence),
        "unknowns": [name for name, record in evidence.items() if record["status"] == "UNKNOWN_NOT_PROVEN"],
        "safety": _jarvis_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(JARVIS_INVESTIGATION_PATH, payload)
    return payload


def get_jarvis_mission() -> dict[str, Any]:
    return build_jarvis_response("mission status")


def _approval_queue_record(mission_id: str, approval_id: str) -> dict[str, Any] | None:
    queue = _load_approval_queue()
    approvals = queue.get("approvals")
    if not isinstance(approvals, list):
        return None
    for item in approvals:
        if not isinstance(item, dict):
            continue
        if str(item.get("mission_id") or "") == mission_id and str(item.get("approval_id") or "") == approval_id:
            return item
    return None


def _false_flag(data: dict[str, Any], key: str) -> bool:
    value = data.get(key)
    if value is None and isinstance(data.get("safety"), dict):
        value = data["safety"].get(key)
    return value is False


def _source_status(name: str, missing_status: str) -> dict[str, Any]:
    path = READ_ONLY_EVIDENCE[name]
    data = _sanitize(_read_json(path))
    return {
        "source": _relative(path),
        "data": data,
        "status": "EVIDENCE_PRESENT" if data is not None else missing_status,
    }


def get_health() -> dict[str, Any]:
    return {
        "echo_api": "AVAILABLE",
        "api_mode": "FASTAPI_APP" if FASTAPI_AVAILABLE else "FALLBACK_FUNCTIONS",
        "fastapi_available": FASTAPI_AVAILABLE,
        "read_only": True,
        "shell_execution": False,
        "codex_execution": False,
        "broker_risk_scanner_changes": False,
        "deploy_or_restart": False,
        "public_exposure": False,
    }


def get_status() -> dict[str, Any]:
    status = build_status()
    status["api_mode"] = "FASTAPI_APP" if FASTAPI_AVAILABLE else "FALLBACK_FUNCTIONS"
    status["fastapi_available"] = FASTAPI_AVAILABLE
    return status


def get_projects() -> dict[str, Any]:
    sources = read_sources()
    return {
        "source": "data/runtime/echo/project_state_registry.json",
        "data": sources["projects"],
        "status": "EVIDENCE_PRESENT" if sources["projects"] is not None else "UNKNOWN",
    }


def get_unified_brain() -> dict[str, Any]:
    sources = read_sources()
    return {
        "source": "data/runtime/unified_brain_status.json",
        "data": sources["unified_brain"],
        "status": "EVIDENCE_PRESENT" if sources["unified_brain"] is not None else "UNKNOWN",
    }


def get_lineage() -> dict[str, Any]:
    sources = read_sources()
    return {
        "sources": [
            "data/runtime/echo/final_lineage_truth_summary.json",
            "data/runtime/echo/natural_run_lineage_proof.json",
        ],
        "final_lineage_truth": sources["lineage"],
        "natural_run_lineage_proof": sources["natural_run"],
    }


def get_alerts() -> dict[str, Any]:
    sources = read_sources()
    return {
        "source": "data/runtime/echo/alert_queue.json",
        "data": sources["alerts"],
        "status": "EVIDENCE_PRESENT" if sources["alerts"] is not None else "UNKNOWN",
    }


def get_missions() -> dict[str, Any]:
    sources = read_sources()
    return {
        "source": "data/runtime/echo/mission_plan.json",
        "data": sources["missions"],
        "status": "EVIDENCE_PRESENT" if sources["missions"] is not None else "UNKNOWN",
    }


def get_answer() -> dict[str, Any]:
    answer_payload = _evidence_payload("answer")
    if answer_payload["data"] is not None:
        return answer_payload
    mission_payload = _evidence_payload("mission_center")
    mission_payload["fallback_source"] = mission_payload["source"]
    mission_payload["source"] = answer_payload["source"]
    return mission_payload


def get_query(intent: str = "status") -> dict[str, Any]:
    requested_intent = intent or "status"
    router_payload = _evidence_payload("query_router")
    router_data = router_payload["data"]
    if not isinstance(router_data, dict):
        return {
            "source": router_payload["source"],
            "intent": requested_intent,
            "status": "UNKNOWN",
            "data": None,
        }
    responses = router_data.get("responses")
    if not isinstance(responses, dict):
        return {
            "source": router_payload["source"],
            "intent": requested_intent,
            "status": "UNKNOWN",
            "data": router_data,
        }
    selected = responses.get(requested_intent) or responses.get("unknown")
    resolved_intent = requested_intent if requested_intent in responses else "unknown"
    return {
        "source": router_payload["source"],
        "intent": requested_intent,
        "resolved_intent": resolved_intent,
        "status": "EVIDENCE_PRESENT" if selected is not None else "UNKNOWN",
        "data": selected,
    }


def get_approval_pending() -> dict[str, Any]:
    payload = _source_status("approval_queue", "WAITING_FOR_DATA")
    data = payload["data"]
    approvals = data.get("approvals") if isinstance(data, dict) else []
    if not isinstance(approvals, list):
        approvals = []
    pending = [
        item
        for item in approvals
        if isinstance(item, dict) and str(item.get("status", "")).upper() == "PENDING"
    ]
    return {
        "source": payload["source"],
        "status": payload["status"],
        "pending": pending,
        "pending_count": len(pending),
        "read_only": True,
        "execution_allowed": False,
        "codex_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
    }


def get_mission_current() -> dict[str, Any]:
    payload = _source_status("mission_plan", "UNKNOWN_NOT_PROVEN")
    data = payload["data"]
    active_mission = None
    if isinstance(data, dict):
        active_mission = (
            data.get("current_mission")
            or data.get("active_mission")
            or data.get("mission")
        )
    return {
        "source": payload["source"],
        "status": payload["status"],
        "active_mission": active_mission,
        "active_mission_proven": active_mission is not None,
        "read_only": True,
        "execution_allowed": False,
        "codex_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
    }


def get_verification_latest() -> dict[str, Any]:
    payload = _source_status("verification_report", "UNKNOWN_NOT_PROVEN")
    return {
        "source": payload["source"],
        "status": payload["status"],
        "verification_report": payload["data"],
        "verification_proven": payload["data"] is not None,
        "read_only": True,
        "execution_allowed": False,
        "codex_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
    }


def build_execution_readiness_report() -> dict[str, Any]:
    mission_plan = _load_mission_plan()
    mission = mission_plan.get("current_mission") if isinstance(mission_plan.get("current_mission"), dict) else {}
    mission_id = str(mission.get("mission_id") or "")
    approval_id = str(mission.get("approval_id") or "")
    approval_status = str(mission.get("approval_status") or mission.get("status") or "").upper()
    queue_record = _approval_queue_record(mission_id, approval_id) if mission_id and approval_id else None
    queue_status = str(queue_record.get("status") or "").upper() if isinstance(queue_record, dict) else ""
    approved_registry_present = _mission_collection_contains(APPROVED_MISSIONS_PATH, mission_id, approval_id) if mission_id and approval_id else False
    rejected_registry_present = _mission_collection_contains(REJECTED_MISSIONS_PATH, mission_id, approval_id) if mission_id and approval_id else False
    merged_safety = dict(mission.get("safety") if isinstance(mission.get("safety"), dict) else {})
    for key in ("execution_allowed", "codex_execution", "shell_execution", "git_push_pull", "deploy_or_restart"):
        if key not in merged_safety and key in mission_plan:
            merged_safety[key] = mission_plan.get(key)
        if key not in merged_safety and key in mission:
            merged_safety[key] = mission.get(key)

    checks = {
        "mission_id_exists": bool(mission_id),
        "approval_id_exists": bool(approval_id),
        "mission_status_approved": approval_status == "APPROVED",
        "approval_queue_decision_approved": queue_status == "APPROVED",
        "mission_exists_in_approved_missions": approved_registry_present,
        "mission_absent_from_rejected_missions": not rejected_registry_present,
        "execution_allowed_remains_false": merged_safety.get("execution_allowed") is False,
        "codex_execution_remains_false": merged_safety.get("codex_execution") is False,
        "shell_execution_remains_false": merged_safety.get("shell_execution") is False,
        "git_push_pull_remains_false": merged_safety.get("git_push_pull") is False,
        "deploy_or_restart_remains_false": merged_safety.get("deploy_or_restart") is False,
    }
    blockers = [name for name, passed in checks.items() if not passed]
    status = "READY_DRY_RUN_ONLY" if not blockers else "NOT_READY"
    report = {
        "schema": "titan.echo.execution_readiness_report.v1",
        "status": status,
        "mission_id": mission_id or None,
        "approval_id": approval_id or None,
        "checks": checks,
        "blockers": blockers,
        "safety": {
            "dry_run_only": True,
            "execution_allowed": False,
            "codex_execution": False,
            "shell_execution": False,
            "git_push_pull": False,
            "deploy_or_restart": False,
            "titan_runtime_changed": False,
            "scanner_changed": False,
            "broker_changed": False,
            "risk_changed": False,
            "master_brain_changed": False,
            "unified_brain_changed": False,
            "runtime_workers_changed": False,
        },
        "generated_at_ist": _timestamp_ist(),
        "message": (
            "Mission is approved for dry-run readiness only. No execution is enabled."
            if status == "READY_DRY_RUN_ONLY"
            else "Mission is not execution-ready; blockers must be resolved without enabling execution."
        ),
    }
    _write_echo_json(EXECUTION_READINESS_REPORT_PATH, report)
    return report


def get_execution_readiness() -> dict[str, Any]:
    report = _read_json(EXECUTION_READINESS_REPORT_PATH)
    if not isinstance(report, dict):
        report = build_execution_readiness_report()
    return report


def post_execution_readiness_check() -> dict[str, Any]:
    return build_execution_readiness_report()


def _format_list_for_prompt(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "- none specified"
    return "\n".join(f"- {value}" for value in values)


def _build_proposed_codex_prompt(mission: dict[str, Any], readiness: dict[str, Any]) -> str:
    mission_id = mission.get("mission_id") or readiness.get("mission_id") or "UNKNOWN"
    approval_id = mission.get("approval_id") or readiness.get("approval_id") or "UNKNOWN"
    title = mission.get("title") or "Approved ECHO mission"
    objective = mission.get("objective") or "Execute only the approved mission scope."
    risk_level = mission.get("risk_level") or "UNKNOWN"
    return "\n".join(
        [
            "Approved ECHO mission execution preview.",
            "",
            f"Mission ID: {mission_id}",
            f"Approval ID: {approval_id}",
            f"Title: {title}",
            f"Risk level: {risk_level}",
            "",
            "Objective:",
            str(objective),
            "",
            "Allowed files:",
            _format_list_for_prompt(mission.get("allowed_files")),
            "",
            "Forbidden files:",
            _format_list_for_prompt(mission.get("forbidden_files")),
            "",
            "Validation commands to run after implementation:",
            _format_list_for_prompt(mission.get("validation_commands")),
            "",
            "Safety rules:",
            "- Do not execute shell commands from the ECHO API.",
            "- Do not git push, git pull, deploy, or restart unless a later explicit approval allows it.",
            "- Do not modify TITAN runtime, broker, risk, execution, scanner, Master Brain, Unified Brain, or runtime workers unless the approved mission explicitly permits it.",
            "- Keep work limited to approved files and validation.",
        ]
    )


def build_execution_preview() -> dict[str, Any]:
    readiness = build_execution_readiness_report()
    mission_plan = _load_mission_plan()
    mission = mission_plan.get("current_mission") if isinstance(mission_plan.get("current_mission"), dict) else {}
    if not isinstance(mission, dict):
        mission = {}

    readiness_status = readiness.get("status")
    blockers = list(readiness.get("blockers") or [])
    if readiness_status != "READY_DRY_RUN_ONLY":
        blockers.append("EXECUTION_READINESS_NOT_READY_DRY_RUN_ONLY")

    mission_id = readiness.get("mission_id") or mission.get("mission_id")
    approval_id = readiness.get("approval_id") or mission.get("approval_id")
    status = "PREVIEW_READY" if readiness_status == "READY_DRY_RUN_ONLY" and not blockers else "NOT_READY"
    proposed_command = (
        "PREVIEW ONLY - future command text after separate execution approval: "
        f"codex run --mission-id {mission_id or 'UNKNOWN'} --approval-id {approval_id or 'UNKNOWN'}"
    )

    preview = {
        "schema": "titan.echo.execution_preview.v1",
        "status": status,
        "mission_id": mission_id,
        "approval_id": approval_id,
        "readiness_status": readiness_status,
        "command_preview_only": True,
        "dry_run_only": True,
        "codex_execution": False,
        "shell_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "titan_runtime_changed": False,
        "proposed_codex_prompt": _build_proposed_codex_prompt(mission, readiness),
        "proposed_codex_command_text": proposed_command,
        "blockers": blockers,
        "safety": {
            "preview_only": True,
            "command_preview_only": True,
            "dry_run_only": True,
            "codex_execution": False,
            "shell_execution": False,
            "git_push_pull": False,
            "deploy_or_restart": False,
            "titan_runtime_changed": False,
            "public_exposure_changed": False,
        },
        "source_files": {
            "mission_plan": _relative(MISSION_PLAN_PATH),
            "approval_queue": _relative(APPROVAL_QUEUE_PATH),
            "approved_missions": _relative(APPROVED_MISSIONS_PATH),
            "execution_readiness_report": _relative(EXECUTION_READINESS_REPORT_PATH),
        },
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(EXECUTION_PREVIEW_PATH, preview)
    return preview


def get_execution_preview() -> dict[str, Any]:
    preview = _read_json(EXECUTION_PREVIEW_PATH)
    if not isinstance(preview, dict):
        preview = build_execution_preview()
    return preview


def post_execution_preview_generate() -> dict[str, Any]:
    return build_execution_preview()


def build_execution_authorization() -> dict[str, Any]:
    mission_plan = _load_mission_plan()
    mission = mission_plan.get("current_mission") if isinstance(mission_plan.get("current_mission"), dict) else {}
    if not isinstance(mission, dict):
        mission = {}

    readiness = _read_json(EXECUTION_READINESS_REPORT_PATH)
    if not isinstance(readiness, dict):
        readiness = build_execution_readiness_report()

    preview = _read_json(EXECUTION_PREVIEW_PATH)
    if not isinstance(preview, dict):
        preview = build_execution_preview()

    mission_id = mission.get("mission_id")
    approval_id = mission.get("approval_id")
    readiness_mission_id = readiness.get("mission_id")
    readiness_approval_id = readiness.get("approval_id")
    preview_mission_id = preview.get("mission_id")
    preview_approval_id = preview.get("approval_id")

    safety_sources = [mission, readiness, preview]
    safety_flags = ("codex_execution", "shell_execution", "git_push_pull", "deploy_or_restart", "titan_runtime_changed")

    def _safety_false_everywhere(flag: str) -> bool:
        for source in safety_sources:
            value = source.get(flag)
            safety = source.get("safety") if isinstance(source.get("safety"), dict) else {}
            if value is None:
                value = safety.get(flag)
            if value is None and flag == "titan_runtime_changed":
                granular_flags = (
                    "broker_changed",
                    "risk_changed",
                    "execution_changed",
                    "scanner_changed",
                    "master_brain_changed",
                    "unified_brain_changed",
                    "runtime_workers_changed",
                )
                value = any(safety.get(item) is True or source.get(item) is True for item in granular_flags)
            if value is not False:
                return False
        return True

    checks = {
        "readiness_ready_dry_run_only": readiness.get("status") == "READY_DRY_RUN_ONLY",
        "preview_ready": preview.get("status") == "PREVIEW_READY",
        "mission_id_present": bool(mission_id),
        "approval_id_present": bool(approval_id),
        "mission_id_matches_readiness": bool(mission_id) and mission_id == readiness_mission_id,
        "mission_id_matches_preview": bool(mission_id) and mission_id == preview_mission_id,
        "approval_id_matches_readiness": bool(approval_id) and approval_id == readiness_approval_id,
        "approval_id_matches_preview": bool(approval_id) and approval_id == preview_approval_id,
        "codex_execution_false": _safety_false_everywhere("codex_execution"),
        "shell_execution_false": _safety_false_everywhere("shell_execution"),
        "git_push_pull_false": _safety_false_everywhere("git_push_pull"),
        "deploy_or_restart_false": _safety_false_everywhere("deploy_or_restart"),
        "titan_runtime_changed_false": _safety_false_everywhere("titan_runtime_changed"),
    }
    blockers = [name for name, passed in checks.items() if not passed]
    status = "AUTHORIZED_DRY_RUN_ONLY" if not blockers else "NOT_AUTHORIZED"
    now = _timestamp_ist()
    authorization_id = _stable_id("echo-execution-auth", str(mission_id), str(approval_id), now)
    authorization = {
        "schema": "titan.echo.execution_authorization.v1",
        "status": status,
        "mission_id": mission_id,
        "approval_id": approval_id,
        "authorization_id": authorization_id,
        "checks": checks,
        "blockers": blockers,
        "safety": {
            "dry_run_only": True,
            "authorization_only": True,
            "codex_execution": False,
            "shell_execution": False,
            "git_push_pull": False,
            "deploy_or_restart": False,
            "titan_runtime_changed": False,
            "actual_execution_permitted": False,
        },
        "authorized_at_ist": now,
        "message": (
            "Dry-run authorization record created. Actual execution remains prohibited."
            if status == "AUTHORIZED_DRY_RUN_ONLY"
            else "Authorization not granted; blockers must be resolved without enabling execution."
        ),
    }
    _write_echo_json(EXECUTION_AUTHORIZATION_PATH, authorization)
    return authorization


def get_execution_authorization() -> dict[str, Any]:
    authorization = _read_json(EXECUTION_AUTHORIZATION_PATH)
    if not isinstance(authorization, dict):
        authorization = build_execution_authorization()
    return authorization


def post_execution_authorize() -> dict[str, Any]:
    return build_execution_authorization()


def _execution_governance_safety(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    safety = {
        "dry_run_only": True,
        "codex_execution": False,
        "shell_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "titan_runtime_changed": False,
        "actual_execution_permitted": False,
    }
    if extra:
        safety.update(extra)
    return safety


def _current_chain_sources() -> dict[str, Any]:
    mission_plan = _load_mission_plan()
    mission = mission_plan.get("current_mission") if isinstance(mission_plan.get("current_mission"), dict) else {}
    if not isinstance(mission, dict):
        mission = {}
    readiness = _read_json(EXECUTION_READINESS_REPORT_PATH)
    if not isinstance(readiness, dict):
        readiness = build_execution_readiness_report()
    preview = _read_json(EXECUTION_PREVIEW_PATH)
    if not isinstance(preview, dict):
        preview = build_execution_preview()
    authorization = _read_json(EXECUTION_AUTHORIZATION_PATH)
    if not isinstance(authorization, dict):
        authorization = build_execution_authorization()
    lock = _read_json(EXECUTION_LOCK_PATH)
    return {
        "mission": mission,
        "readiness": readiness,
        "preview": preview,
        "authorization": authorization,
        "lock": lock if isinstance(lock, dict) else {},
    }


def _chain_ids(chain: dict[str, Any]) -> dict[str, Any]:
    mission = chain.get("mission") if isinstance(chain.get("mission"), dict) else {}
    authorization = chain.get("authorization") if isinstance(chain.get("authorization"), dict) else {}
    lock = chain.get("lock") if isinstance(chain.get("lock"), dict) else {}
    return {
        "mission_id": mission.get("mission_id") or authorization.get("mission_id") or lock.get("mission_id"),
        "approval_id": mission.get("approval_id") or authorization.get("approval_id") or lock.get("approval_id"),
        "authorization_id": authorization.get("authorization_id") or lock.get("authorization_id"),
        "lock_id": lock.get("lock_id"),
    }


def build_execution_lock() -> dict[str, Any]:
    chain = _current_chain_sources()
    mission = chain["mission"]
    authorization = chain["authorization"]
    mission_id = mission.get("mission_id")
    approval_id = mission.get("approval_id")
    authorization_id = authorization.get("authorization_id")
    checks = {
        "authorization_status_authorized_dry_run_only": authorization.get("status") == "AUTHORIZED_DRY_RUN_ONLY",
        "mission_id_matches_authorization": bool(mission_id) and mission_id == authorization.get("mission_id"),
        "approval_id_matches_authorization": bool(approval_id) and approval_id == authorization.get("approval_id"),
        "authorization_id_present": bool(authorization_id),
    }
    blockers = [name for name, passed in checks.items() if not passed]
    now = _timestamp_ist()
    lock_id = _stable_id("echo-execution-lock", str(mission_id), str(approval_id), str(authorization_id), now)
    lock = {
        "schema": "titan.echo.execution_lock.v1",
        "lock_id": lock_id,
        "mission_id": mission_id,
        "approval_id": approval_id,
        "authorization_id": authorization_id,
        "status": "LOCKED_DRY_RUN_ONLY" if not blockers else "NOT_LOCKED",
        "checks": checks,
        "blockers": blockers,
        "created_at_ist": now,
        "safety": _execution_governance_safety({"execution_locked": not blockers}),
    }
    _write_echo_json(EXECUTION_LOCK_PATH, lock)
    return lock


def get_execution_lock() -> dict[str, Any]:
    lock = _read_json(EXECUTION_LOCK_PATH)
    if not isinstance(lock, dict):
        lock = build_execution_lock()
    return lock


def post_execution_lock_create() -> dict[str, Any]:
    return build_execution_lock()


def build_execution_evidence() -> dict[str, Any]:
    chain = _current_chain_sources()
    if not chain.get("lock"):
        chain["lock"] = build_execution_lock()
    ids = _chain_ids(chain)
    mission = chain["mission"]
    readiness = chain["readiness"]
    preview = chain["preview"]
    authorization = chain["authorization"]
    lock = chain["lock"]
    chain_integrity = {
        "mission_to_readiness": bool(ids["mission_id"]) and ids["mission_id"] == readiness.get("mission_id"),
        "mission_to_preview": bool(ids["mission_id"]) and ids["mission_id"] == preview.get("mission_id"),
        "mission_to_authorization": bool(ids["mission_id"]) and ids["mission_id"] == authorization.get("mission_id"),
        "mission_to_lock": bool(ids["mission_id"]) and ids["mission_id"] == lock.get("mission_id"),
        "approval_to_readiness": bool(ids["approval_id"]) and ids["approval_id"] == readiness.get("approval_id"),
        "approval_to_preview": bool(ids["approval_id"]) and ids["approval_id"] == preview.get("approval_id"),
        "approval_to_authorization": bool(ids["approval_id"]) and ids["approval_id"] == authorization.get("approval_id"),
        "approval_to_lock": bool(ids["approval_id"]) and ids["approval_id"] == lock.get("approval_id"),
        "authorization_to_lock": bool(ids["authorization_id"]) and ids["authorization_id"] == lock.get("authorization_id"),
        "readiness_ready": readiness.get("status") == "READY_DRY_RUN_ONLY",
        "preview_ready": preview.get("status") == "PREVIEW_READY",
        "authorization_ready": authorization.get("status") == "AUTHORIZED_DRY_RUN_ONLY",
        "lock_ready": lock.get("status") == "LOCKED_DRY_RUN_ONLY",
    }
    blockers = [name for name, passed in chain_integrity.items() if not passed]
    evidence_id = _stable_id(
        "echo-execution-evidence",
        str(ids["mission_id"]),
        str(ids["approval_id"]),
        str(ids["authorization_id"]),
        str(ids["lock_id"]),
    )
    evidence = {
        "schema": "titan.echo.execution_evidence.v1",
        "evidence_id": evidence_id,
        "status": "EVIDENCE_READY" if not blockers else "EVIDENCE_NOT_READY",
        "mission_id": ids["mission_id"],
        "approval_id": ids["approval_id"],
        "authorization_id": ids["authorization_id"],
        "lock_id": ids["lock_id"],
        "readiness_status": readiness.get("status"),
        "preview_status": preview.get("status"),
        "authorization_status": authorization.get("status"),
        "lock_status": lock.get("status"),
        "chain_integrity": chain_integrity,
        "blockers": blockers,
        "generated_at_ist": _timestamp_ist(),
        "safety": _execution_governance_safety(),
    }
    _write_echo_json(EXECUTION_EVIDENCE_PATH, evidence)
    return evidence


def get_execution_evidence() -> dict[str, Any]:
    evidence = _read_json(EXECUTION_EVIDENCE_PATH)
    if not isinstance(evidence, dict):
        evidence = build_execution_evidence()
    return evidence


def build_execution_ledger() -> dict[str, Any]:
    evidence = _read_json(EXECUTION_EVIDENCE_PATH)
    if not isinstance(evidence, dict):
        evidence = build_execution_evidence()
    timestamp = _timestamp_ist()
    ledger = {
        "schema": "titan.echo.execution_ledger.v1",
        "status": "GOVERNANCE_CHAIN_COMPLETE" if evidence.get("status") == "EVIDENCE_READY" else "GOVERNANCE_CHAIN_INCOMPLETE",
        "mission_id": evidence.get("mission_id"),
        "approval_id": evidence.get("approval_id"),
        "authorization_id": evidence.get("authorization_id"),
        "lock_id": evidence.get("lock_id"),
        "evidence_id": evidence.get("evidence_id"),
        "timestamp": timestamp,
        "entries": [
            {
                "event": "GOVERNANCE_CHAIN_RECORDED",
                "mission_id": evidence.get("mission_id"),
                "approval_id": evidence.get("approval_id"),
                "authorization_id": evidence.get("authorization_id"),
                "lock_id": evidence.get("lock_id"),
                "evidence_id": evidence.get("evidence_id"),
                "timestamp": timestamp,
            }
        ],
        "safety": _execution_governance_safety(),
    }
    _write_echo_json(EXECUTION_LEDGER_PATH, ledger)
    return ledger


def get_execution_ledger() -> dict[str, Any]:
    ledger = _read_json(EXECUTION_LEDGER_PATH)
    if not isinstance(ledger, dict):
        ledger = build_execution_ledger()
    return ledger


def build_execution_policy() -> dict[str, Any]:
    policy = {
        "schema": "titan.echo.execution_policy.v1",
        "status": "EXECUTION_DISABLED_BY_POLICY",
        "execution_mode": "DISABLED",
        "actual_execution_permitted": False,
        "required_chain": [
            "mission_prepared",
            "mission_approved",
            "approval_audited",
            "readiness_ready",
            "preview_ready",
            "authorization_dry_run_only",
            "lock_created",
            "evidence_ready",
            "ledger_complete",
        ],
        "forbidden_actions": [
            "codex_execution",
            "shell_execution",
            "git_push_pull",
            "deploy_or_restart",
            "titan_runtime_modification",
            "broker_change",
            "risk_change",
            "scanner_change",
            "master_brain_change",
            "unified_brain_change",
        ],
        "safety": _execution_governance_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(EXECUTION_POLICY_PATH, policy)
    return policy


def get_execution_policy() -> dict[str, Any]:
    policy = _read_json(EXECUTION_POLICY_PATH)
    if not isinstance(policy, dict):
        policy = build_execution_policy()
    return policy


def build_execution_gate() -> dict[str, Any]:
    readiness = _read_json(EXECUTION_READINESS_REPORT_PATH)
    if not isinstance(readiness, dict):
        readiness = build_execution_readiness_report()
    preview = _read_json(EXECUTION_PREVIEW_PATH)
    if not isinstance(preview, dict):
        preview = build_execution_preview()
    authorization = _read_json(EXECUTION_AUTHORIZATION_PATH)
    if not isinstance(authorization, dict):
        authorization = build_execution_authorization()
    lock = _read_json(EXECUTION_LOCK_PATH)
    if not isinstance(lock, dict):
        lock = build_execution_lock()
    evidence = _read_json(EXECUTION_EVIDENCE_PATH)
    if not isinstance(evidence, dict):
        evidence = build_execution_evidence()
    ledger = _read_json(EXECUTION_LEDGER_PATH)
    if not isinstance(ledger, dict):
        ledger = build_execution_ledger()
    policy = _read_json(EXECUTION_POLICY_PATH)
    if not isinstance(policy, dict):
        policy = build_execution_policy()

    checks = {
        "readiness_ready_dry_run_only": readiness.get("status") == "READY_DRY_RUN_ONLY",
        "preview_ready": preview.get("status") == "PREVIEW_READY",
        "authorization_authorized_dry_run_only": authorization.get("status") == "AUTHORIZED_DRY_RUN_ONLY",
        "lock_locked_dry_run_only": lock.get("status") == "LOCKED_DRY_RUN_ONLY",
        "evidence_ready": evidence.get("status") == "EVIDENCE_READY",
        "ledger_governance_chain_complete": ledger.get("status") == "GOVERNANCE_CHAIN_COMPLETE",
        "policy_execution_disabled": policy.get("status") == "EXECUTION_DISABLED_BY_POLICY",
        "actual_execution_permitted_false": policy.get("actual_execution_permitted") is False,
    }
    blockers = [name for name, passed in checks.items() if not passed]
    gate = {
        "schema": "titan.echo.execution_gate.v1",
        "status": "EXECUTION_BLOCKED_POLICY_LOCKED",
        "gate_decision": "BLOCK_EXECUTION",
        "reason": "POLICY_DISABLED_EXECUTION",
        "mission_id": readiness.get("mission_id") or preview.get("mission_id") or authorization.get("mission_id"),
        "approval_id": readiness.get("approval_id") or preview.get("approval_id") or authorization.get("approval_id"),
        "authorization_id": authorization.get("authorization_id") or lock.get("authorization_id") or evidence.get("authorization_id"),
        "lock_id": lock.get("lock_id") or evidence.get("lock_id") or ledger.get("lock_id"),
        "evidence_id": evidence.get("evidence_id") or ledger.get("evidence_id"),
        "checks": checks,
        "blockers": blockers,
        "generated_at_ist": _timestamp_ist(),
        "safety": _execution_governance_safety({"execution_mode": "DISABLED"}),
    }
    _write_echo_json(EXECUTION_GATE_PATH, gate)
    return gate


def get_execution_gate() -> dict[str, Any]:
    gate = _read_json(EXECUTION_GATE_PATH)
    if not isinstance(gate, dict):
        gate = build_execution_gate()
    return gate


def post_execution_gate_evaluate() -> dict[str, Any]:
    return build_execution_gate()


def build_chatgpt_connection_readiness() -> dict[str, Any]:
    policy = _read_json(EXECUTION_POLICY_PATH)
    if not isinstance(policy, dict):
        policy = build_execution_policy()
    gate = _read_json(EXECUTION_GATE_PATH)
    if not isinstance(gate, dict):
        gate = build_execution_gate()
    ledger = _read_json(EXECUTION_LEDGER_PATH)
    if not isinstance(ledger, dict):
        ledger = build_execution_ledger()

    safety = {
        "codex_execution": False,
        "shell_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "titan_runtime_changed": False,
        "actual_execution_permitted": False,
        "chatgpt_connection_enabled": False,
        "external_api_calls_enabled": False,
        "public_exposure_allowed": False,
    }
    checks = {
        "echo_service_localhost_only": True,
        "api_key_auth_enabled": "/chatgpt/readiness" in PROTECTED_ENDPOINTS,
        "governance_bridge_exists": ledger.get("status") == "GOVERNANCE_CHAIN_COMPLETE",
        "execution_gate_blocks_execution": gate.get("gate_decision") == "BLOCK_EXECUTION",
        "execution_mode_disabled": policy.get("execution_mode") == "DISABLED" or gate.get("safety", {}).get("execution_mode") == "DISABLED",
        "actual_execution_permitted_false": policy.get("actual_execution_permitted") is False and gate.get("safety", {}).get("actual_execution_permitted") is False,
        "no_public_exposure": safety["public_exposure_allowed"] is False,
        "no_shell_execution": safety["shell_execution"] is False,
        "no_codex_execution": safety["codex_execution"] is False,
        "no_git_push_pull": safety["git_push_pull"] is False,
        "no_deploy_restart": safety["deploy_or_restart"] is False,
    }
    blockers = [name for name, passed in checks.items() if not passed]
    report = {
        "schema": "titan.echo.chatgpt_connection_readiness.v1",
        "status": "CHATGPT_CONNECTION_READY_LOCAL_ONLY" if not blockers else "NOT_READY",
        "bridge_status": ledger.get("status"),
        "governance_gate_status": gate.get("status"),
        "localhost_only": checks["echo_service_localhost_only"],
        "auth_required": checks["api_key_auth_enabled"],
        "public_exposure_allowed": False,
        "chatgpt_connection_enabled": False,
        "external_api_calls_enabled": False,
        "actual_execution_permitted": False,
        "checks": checks,
        "blockers": blockers,
        "safety": safety,
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(CHATGPT_CONNECTION_READINESS_PATH, report)
    return report


def get_chatgpt_readiness() -> dict[str, Any]:
    report = _read_json(CHATGPT_CONNECTION_READINESS_PATH)
    if not isinstance(report, dict):
        report = build_chatgpt_connection_readiness()
    return report


def post_chatgpt_readiness_check() -> dict[str, Any]:
    return build_chatgpt_connection_readiness()


def post_mission_prepare(payload: dict[str, Any]) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    now = _timestamp_ist()
    title = str(body.get("title") or body.get("mission_title") or "Untitled ECHO mission").strip()
    objective = str(body.get("objective") or "").strip()
    risk_level = str(body.get("risk_level") or "MEDIUM").upper()
    if risk_level not in VALID_RISK_LEVELS:
        risk_level = "MEDIUM"
    allowed_files = _as_string_list(body.get("allowed_files"))
    forbidden_files = _as_string_list(body.get("forbidden_files"))
    validation_commands = _as_string_list(body.get("validation_commands"))
    mission_id = _stable_id("echo-mission", title, objective, risk_level, now)
    approval_id = _stable_id("echo-approval", mission_id, title, now)
    safety = {
        "execution_allowed": False,
        "codex_execution": False,
        "shell_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "broker_changed": False,
        "risk_changed": False,
        "execution_changed": False,
        "scanner_changed": False,
        "master_brain_changed": False,
        "unified_brain_changed": False,
        "runtime_workers_changed": False,
    }
    mission_record = {
        "mission_id": mission_id,
        "approval_id": approval_id,
        "title": title,
        "objective": objective,
        "risk_level": risk_level,
        "allowed_files": allowed_files,
        "forbidden_files": forbidden_files,
        "validation_commands": validation_commands,
        "approval_status": "PENDING",
        "created_at_ist": now,
        "prepared_by": "ECHO_API",
        "requires_ari_approval": True,
        "safety": safety,
    }
    mission_plan = {
        "schema": "titan.echo.mission_prepare_plan.v1",
        "timestamp_ist": now,
        "current_mission": mission_record,
        "approval_gate": "WAITING_FOR_ARI_APPROVAL",
        "execution_allowed": False,
        "codex_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "forbidden_actions": [
            "Do not execute Codex.",
            "Do not run shell commands.",
            "Do not git push or pull.",
            "Do not deploy or restart.",
            "Do not touch broker/risk/execution/scanner/Master Brain/Unified Brain/runtime workers.",
        ],
        "safety": safety,
    }
    approval_record = {
        "approval_id": approval_id,
        "mission_id": mission_id,
        "timestamp_ist": now,
        "title": title,
        "objective": objective,
        "risk_level": risk_level,
        "status": "PENDING",
        "allowed_files": allowed_files,
        "forbidden_files": forbidden_files,
        "validation_commands": validation_commands,
        "requires_ari_approval": True,
        "approval_note": "",
        "decision_timestamp_ist": "",
        "safety": safety,
    }
    queue = _load_approval_queue()
    queue["approvals"].append(approval_record)
    _write_echo_json(MISSION_PLAN_PATH, mission_plan)
    _save_approval_queue(queue)
    return {
        "status": "PENDING",
        "mission_id": mission_id,
        "approval_id": approval_id,
        "mission_plan_path": _relative(MISSION_PLAN_PATH),
        "approval_queue_path": _relative(APPROVAL_QUEUE_PATH),
        "execution_allowed": False,
        "codex_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "safety": safety,
    }


def _update_approval_decision(payload: dict[str, Any], decision: str) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    approval_id = str(body.get("approval_id") or "").strip()
    note = str(body.get("note") or "").strip()
    now = _timestamp_ist()
    safety = _decision_safety()
    if not approval_id:
        return {
            "status": "UNKNOWN_NOT_PROVEN",
            "reason": "APPROVAL_ID_REQUIRED",
            "approval_id": "",
            "execution_allowed": False,
            "codex_execution": False,
            "git_push_pull": False,
            "deploy_or_restart": False,
            "safety": safety,
        }

    queue = _load_approval_queue()
    approvals = [item for item in queue.get("approvals", []) if isinstance(item, dict)]
    matched: dict[str, Any] | None = None
    for item in approvals:
        if str(item.get("approval_id") or "") == approval_id:
            item["status"] = decision
            item["approval_note"] = note
            item["decision_timestamp_ist"] = now
            item["execution_allowed"] = False
            item["codex_execution"] = False
            item["git_push_pull"] = False
            item["deploy_or_restart"] = False
            item["safety"] = safety
            matched = item
            break

    if matched is None:
        return {
            "status": "UNKNOWN_NOT_PROVEN",
            "reason": "APPROVAL_ID_NOT_FOUND",
            "approval_id": approval_id,
            "execution_allowed": False,
            "codex_execution": False,
            "git_push_pull": False,
            "deploy_or_restart": False,
            "safety": safety,
        }

    queue["approvals"] = approvals
    _save_approval_queue(queue)

    mission_plan = _load_mission_plan()
    current = mission_plan.get("current_mission") if isinstance(mission_plan.get("current_mission"), dict) else None
    if current and str(current.get("approval_id") or "") == approval_id:
        current["approval_status"] = decision
        current["approval_note"] = note
        current["decision_timestamp_ist"] = now
        current["safety"] = safety
        mission_plan["current_mission"] = current
        mission_plan["approval_gate"] = f"ARI_{decision}"
        mission_plan["timestamp_ist"] = now
        mission_plan["execution_allowed"] = False
        mission_plan["codex_execution"] = False
        mission_plan["git_push_pull"] = False
        mission_plan["deploy_or_restart"] = False
        mission_plan["safety"] = safety
        _write_echo_json(MISSION_PLAN_PATH, mission_plan)

    history_record = {
        "history_event": decision,
        "approval_id": approval_id,
        "mission_id": matched.get("mission_id"),
        "approval_note": note,
        "decision_timestamp_ist": now,
        "approval_record": matched,
        "execution_allowed": False,
        "codex_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "safety": safety,
    }
    _append_echo_jsonl(APPROVAL_HISTORY_PATH, history_record)
    if decision == "APPROVED":
        _append_mission_decision(APPROVED_MISSIONS_PATH, decision, matched, mission_plan)
        decision_collection_path = APPROVED_MISSIONS_PATH
    else:
        _append_mission_decision(REJECTED_MISSIONS_PATH, decision, matched, mission_plan)
        decision_collection_path = REJECTED_MISSIONS_PATH

    return {
        "status": decision,
        "approval_id": approval_id,
        "mission_id": matched.get("mission_id"),
        "approval_note": note,
        "decision_timestamp_ist": now,
        "approval_queue_path": _relative(APPROVAL_QUEUE_PATH),
        "mission_plan_path": _relative(MISSION_PLAN_PATH),
        "approval_history_path": _relative(APPROVAL_HISTORY_PATH),
        "decision_collection_path": _relative(decision_collection_path),
        "execution_allowed": False,
        "codex_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "safety": safety,
    }


def post_approval_approve(payload: dict[str, Any]) -> dict[str, Any]:
    return _update_approval_decision(payload, "APPROVED")


def post_approval_reject(payload: dict[str, Any]) -> dict[str, Any]:
    return _update_approval_decision(payload, "REJECTED")


# Compatibility aliases for existing local imports and FastAPI route names.
health = get_health
status = get_status
projects = get_projects
unified_brain = get_unified_brain
lineage = get_lineage
alerts = get_alerts
missions = get_missions
answer = get_answer
query = get_query
approval_pending = get_approval_pending
mission_current = get_mission_current
verification_latest = get_verification_latest
execution_readiness = get_execution_readiness
execution_readiness_check = post_execution_readiness_check
execution_preview = get_execution_preview
execution_preview_generate = post_execution_preview_generate
execution_authorization = get_execution_authorization
execution_authorize = post_execution_authorize
execution_lock = get_execution_lock
execution_lock_create = post_execution_lock_create
execution_evidence = get_execution_evidence
execution_ledger = get_execution_ledger
execution_policy = get_execution_policy
execution_gate = get_execution_gate
execution_gate_evaluate = post_execution_gate_evaluate
chatgpt_readiness = get_chatgpt_readiness
chatgpt_readiness_check = post_chatgpt_readiness_check
chat_session = get_chat_session
chat_session_create = post_chat_session_create
echo_context = get_echo_context
echo_runtime = get_echo_runtime
echo_evidence = get_echo_evidence
jarvis_status = get_jarvis_status
jarvis_question = get_jarvis_question
jarvis_question_post = post_jarvis_question
jarvis_ask = post_jarvis_ask
jarvis_explain = get_jarvis_explain
jarvis_investigate = get_jarvis_investigate
jarvis_mission = get_jarvis_mission
titan_status = get_titan_status
titan_health = get_titan_health
titan_workers = get_titan_workers
titan_scanner = get_titan_scanner
titan_trades = get_titan_trades
titan_brain = get_titan_brain
titan_runtime_context = get_titan_runtime_context
chatgpt_bridge_readiness = get_chatgpt_bridge_readiness
chatgpt_connector_plan = get_chatgpt_connector_plan
chatgpt_handshake_status = get_chatgpt_handshake_status
chatgpt_handshake_test = post_chatgpt_handshake_test
chatgpt_evidence_contract = get_chatgpt_evidence_contract
chatgpt_evidence_catalog = get_chatgpt_evidence_catalog
chatgpt_integration_status = get_chatgpt_integration_status
mission_prepare = post_mission_prepare
approval_approve = post_approval_approve
approval_reject = post_approval_reject


app = None
if FASTAPI_AVAILABLE:
    app = FastAPI(
        title="ECHO Read-Only API",
        version="0.2.0",
        description="Read-only local ECHO API for existing TITAN evidence files.",
    )
    auth_dependency = [Depends(require_echo_api_key)]
    app.get("/health")(get_health)
    app.get("/status", dependencies=auth_dependency)(get_status)
    app.get("/projects", dependencies=auth_dependency)(get_projects)
    app.get("/unified-brain", dependencies=auth_dependency)(get_unified_brain)
    app.get("/lineage", dependencies=auth_dependency)(get_lineage)
    app.get("/alerts", dependencies=auth_dependency)(get_alerts)
    app.get("/missions", dependencies=auth_dependency)(get_missions)
    app.get("/answer", dependencies=auth_dependency)(get_answer)
    app.get("/query", dependencies=auth_dependency)(get_query)
    app.get("/approval/pending", dependencies=auth_dependency)(get_approval_pending)
    app.get("/mission/current", dependencies=auth_dependency)(get_mission_current)
    app.get("/verification/latest", dependencies=auth_dependency)(get_verification_latest)
    app.get("/execution/readiness", dependencies=auth_dependency)(get_execution_readiness)
    app.get("/execution/preview", dependencies=auth_dependency)(get_execution_preview)
    app.get("/execution/authorization", dependencies=auth_dependency)(get_execution_authorization)
    app.get("/execution/lock", dependencies=auth_dependency)(get_execution_lock)
    app.get("/execution/evidence", dependencies=auth_dependency)(get_execution_evidence)
    app.get("/execution/ledger", dependencies=auth_dependency)(get_execution_ledger)
    app.get("/execution/policy", dependencies=auth_dependency)(get_execution_policy)
    app.get("/execution/gate", dependencies=auth_dependency)(get_execution_gate)
    app.get("/chatgpt/readiness", dependencies=auth_dependency)(get_chatgpt_readiness)
    app.get("/chat/session", dependencies=auth_dependency)(get_chat_session)
    app.post("/chat/session/create", dependencies=auth_dependency)(post_chat_session_create)
    app.get("/echo/context", dependencies=auth_dependency)(get_echo_context)
    app.get("/echo/runtime", dependencies=auth_dependency)(get_echo_runtime)
    app.get("/echo/evidence", dependencies=auth_dependency)(get_echo_evidence)
    app.get("/jarvis/status", dependencies=auth_dependency)(get_jarvis_status)
    app.get("/jarvis/question", dependencies=auth_dependency)(get_jarvis_question)
    app.post("/jarvis/question", dependencies=auth_dependency)(post_jarvis_question)
    app.post("/jarvis/ask", dependencies=auth_dependency)(post_jarvis_ask)
    app.get("/jarvis/explain", dependencies=auth_dependency)(get_jarvis_explain)
    app.get("/jarvis/investigate", dependencies=auth_dependency)(get_jarvis_investigate)
    app.get("/jarvis/mission", dependencies=auth_dependency)(get_jarvis_mission)
    app.get("/titan/status", dependencies=auth_dependency)(get_titan_status)
    app.get("/titan/health", dependencies=auth_dependency)(get_titan_health)
    app.get("/titan/workers", dependencies=auth_dependency)(get_titan_workers)
    app.get("/titan/scanner", dependencies=auth_dependency)(get_titan_scanner)
    app.get("/titan/trades", dependencies=auth_dependency)(get_titan_trades)
    app.get("/titan/brain", dependencies=auth_dependency)(get_titan_brain)
    app.get("/titan/runtime/context", dependencies=auth_dependency)(get_titan_runtime_context)
    app.get("/chatgpt/bridge/readiness", dependencies=auth_dependency)(get_chatgpt_bridge_readiness)
    app.get("/chatgpt/connector/plan", dependencies=auth_dependency)(get_chatgpt_connector_plan)
    app.get("/chatgpt/handshake/status", dependencies=auth_dependency)(get_chatgpt_handshake_status)
    app.post("/chatgpt/handshake/test", dependencies=auth_dependency)(post_chatgpt_handshake_test)
    app.get("/chatgpt/evidence/contract", dependencies=auth_dependency)(get_chatgpt_evidence_contract)
    app.get("/chatgpt/evidence/catalog", dependencies=auth_dependency)(get_chatgpt_evidence_catalog)
    app.get("/chatgpt/integration/status", dependencies=auth_dependency)(get_chatgpt_integration_status)
    app.post("/mission/prepare", dependencies=auth_dependency)(post_mission_prepare)
    app.post("/approval/approve", dependencies=auth_dependency)(post_approval_approve)
    app.post("/approval/reject", dependencies=auth_dependency)(post_approval_reject)
    app.post("/execution/readiness/check", dependencies=auth_dependency)(post_execution_readiness_check)
    app.post("/execution/preview/generate", dependencies=auth_dependency)(post_execution_preview_generate)
    app.post("/execution/authorize", dependencies=auth_dependency)(post_execution_authorize)
    app.post("/execution/lock/create", dependencies=auth_dependency)(post_execution_lock_create)
    app.post("/execution/gate/evaluate", dependencies=auth_dependency)(post_execution_gate_evaluate)
    app.post("/chatgpt/readiness/check", dependencies=auth_dependency)(post_chatgpt_readiness_check)


__all__ = [
    "FASTAPI_AVAILABLE",
    "app",
    "get_health",
    "get_status",
    "get_projects",
    "get_unified_brain",
    "get_lineage",
    "get_alerts",
    "get_missions",
    "get_answer",
    "get_query",
    "get_approval_pending",
    "get_mission_current",
    "get_verification_latest",
    "get_execution_readiness",
    "post_execution_readiness_check",
    "get_execution_preview",
    "post_execution_preview_generate",
    "get_execution_authorization",
    "post_execution_authorize",
    "get_execution_lock",
    "post_execution_lock_create",
    "get_execution_evidence",
    "get_execution_ledger",
    "get_execution_policy",
    "get_execution_gate",
    "post_execution_gate_evaluate",
    "get_chatgpt_readiness",
    "post_chatgpt_readiness_check",
    "get_chat_session",
    "post_chat_session_create",
    "get_echo_context",
    "get_echo_runtime",
    "get_echo_evidence",
    "get_jarvis_status",
    "get_jarvis_question",
    "post_jarvis_question",
    "post_jarvis_ask",
    "get_jarvis_explain",
    "get_jarvis_investigate",
    "get_jarvis_mission",
    "get_titan_status",
    "get_titan_health",
    "get_titan_workers",
    "get_titan_scanner",
    "get_titan_trades",
    "get_titan_brain",
    "get_titan_runtime_context",
    "get_chatgpt_bridge_readiness",
    "get_chatgpt_connector_plan",
    "get_chatgpt_handshake_status",
    "post_chatgpt_handshake_test",
    "get_chatgpt_evidence_contract",
    "get_chatgpt_evidence_catalog",
    "get_chatgpt_integration_status",
    "post_mission_prepare",
    "post_approval_approve",
    "post_approval_reject",
    "health",
    "status",
    "projects",
    "unified_brain",
    "lineage",
    "alerts",
    "missions",
    "answer",
    "query",
    "approval_pending",
    "mission_current",
    "verification_latest",
    "execution_readiness",
    "execution_readiness_check",
    "execution_preview",
    "execution_preview_generate",
    "execution_authorization",
    "execution_authorize",
    "execution_lock",
    "execution_lock_create",
    "execution_evidence",
    "execution_ledger",
    "execution_policy",
    "execution_gate",
    "execution_gate_evaluate",
    "chatgpt_readiness",
    "chatgpt_readiness_check",
    "chat_session",
    "chat_session_create",
    "echo_context",
    "echo_runtime",
    "echo_evidence",
    "jarvis_status",
    "jarvis_question",
    "jarvis_question_post",
    "jarvis_ask",
    "jarvis_explain",
    "jarvis_investigate",
    "jarvis_mission",
    "titan_status",
    "titan_health",
    "titan_workers",
    "titan_scanner",
    "titan_trades",
    "titan_brain",
    "titan_runtime_context",
    "chatgpt_bridge_readiness",
    "chatgpt_connector_plan",
    "chatgpt_handshake_status",
    "chatgpt_handshake_test",
    "chatgpt_evidence_contract",
    "chatgpt_evidence_catalog",
    "chatgpt_integration_status",
    "mission_prepare",
    "approval_approve",
    "approval_reject",
]
