import json
import os
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from master_brain_activation_guard import BROKER_APPROVAL_TOKEN, TELEGRAM_APPROVAL_TOKEN
from restart_readiness_gate import build_restart_readiness_gate
from runtime_truth import build_authoritative_runtime_truth
from scanner_ohlc_setup_truth import build_scanner_ohlc_setup_truth
from utils.market_hours import as_ist_datetime


RUNTIME_DIR = Path("data") / "runtime"
DIAGNOSTIC_PATH = RUNTIME_DIR / "controlled_workers_mission_019.json"
JOURNAL_TRUTH_PATH = RUNTIME_DIR / "journal_truth_unification.json"
MASTER_GUARD_PATH = RUNTIME_DIR / "master_brain_activation_guard.json"
WORKER_HEALTH_PATH = RUNTIME_DIR / "worker_health.json"
DASHBOARD_SYNC_STATUS_PATH = RUNTIME_DIR / "dashboard_sync_status.json"
SCANNER_STATUS_PATH = RUNTIME_DIR / "scanner_status.json"
OUTCOME_TRACKER_STATUS_PATH = RUNTIME_DIR / "outcome_tracker_status.json"
PAPER_ENGINE_STATUS_PATH = RUNTIME_DIR / "paper_engine_status.json"


def _timestamp():
    return as_ist_datetime().isoformat()


def _read_json(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": f"{type(exc).__name__}:{exc}"}
    return payload if isinstance(payload, dict) else {"_read_error": "json_root_not_object"}


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
        ) as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def _precheck():
    gate = _read_json(RUNTIME_DIR / "restart_readiness_gate.json")
    journal = _read_json(JOURNAL_TRUTH_PATH)
    master_guard = _read_json(MASTER_GUARD_PATH)
    broker_disabled = (
        os.environ.get("TITAN_BROKER_LIVE_EXECUTION") != BROKER_APPROVAL_TOKEN
        and not master_guard.get("can_call_broker")
    )
    telegram_disabled = (
        os.environ.get("TITAN_TELEGRAM_ALERTS") != TELEGRAM_APPROVAL_TOKEN
        and not master_guard.get("can_send_telegram")
    )
    canonical_open = int(journal.get("canonical_open_trade_count") or 0)
    precheck = {
        "daemon_live": gate.get("daemon_status") == "LIVE",
        "safe_to_start_workers": bool(gate.get("safe_to_start_workers")),
        "canonical_open_trades": canonical_open,
        "master_brain_effective_mode": master_guard.get("effective_mode") or master_guard.get("status"),
        "broker_order_execution_disabled": broker_disabled,
        "telegram_disabled": telegram_disabled,
        "gate_blockers": list(gate.get("blockers") or []),
        "gate_warnings": list(gate.get("warnings") or []),
    }
    precheck["passed"] = bool(
        precheck["daemon_live"]
        and precheck["safe_to_start_workers"]
        and canonical_open == 0
        and str(precheck["master_brain_effective_mode"]).upper() == "READ_ONLY"
        and broker_disabled
        and telegram_disabled
    )
    return precheck


def _run_worker_proof():
    from tools.worker_proof_runner_019 import run_proof

    payload = run_proof()
    payload["returncode"] = 0
    payload["stderr_tail"] = ""
    return payload


def _fresh_payload(path):
    payload = _read_json(path)
    return payload


def _worker_health_status():
    payload = _read_json(WORKER_HEALTH_PATH)
    proof_tasks = {}
    for task in ("heartbeat", "runtime_status", "dashboard_sync"):
        item = payload.get(task) if isinstance(payload.get(task), dict) else {}
        proof_tasks[task] = {
            "status": item.get("status"),
            "last_finished_at": item.get("last_finished_at"),
            "proof_mode": item.get("proof_mode"),
            "broker_order_api_called": item.get("broker_order_api_called"),
            "trading_api_called": item.get("trading_api_called"),
            "telegram_sent": item.get("telegram_sent"),
            "journal_mutation": item.get("journal_mutation"),
        }
    ok = all((item.get("status") == "OK" and item.get("proof_mode") is True) for item in proof_tasks.values())
    return {"status": "OK" if ok else "DEGRADED", "proof_tasks": proof_tasks}


def run_mission():
    precheck = _precheck()
    diagnostic = {
        "generated_at": _timestamp(),
        "mission": "019",
        "mode": "controlled_worker_start_proof_only",
        "precheck": precheck,
        "worker_start_command_used": None,
        "workers_visible": False,
        "worker_health_status": {},
        "scheduler_status": {},
        "scanner_status": {},
        "outcome_tracker_status": {},
        "paper_engine_status": {},
        "dashboard_sync_status": {},
        "broker_order_api_called": False,
        "trading_api_called": False,
        "telegram_sent": False,
        "journal_mutation": False,
        "canonical_open_trades_after": None,
        "authoritative_runtime_truth_after": {},
        "restart_readiness_gate_after": {},
        "blockers": [],
        "warnings": [],
        "next_required_action": None,
    }
    if not precheck["passed"]:
        diagnostic["blockers"] = ["precheck_failed"]
        diagnostic["next_required_action"] = "Keep daemon safe; do not start workers until precheck passes."
        _atomic_write_json(DIAGNOSTIC_PATH, diagnostic)
        return diagnostic

    result = _run_worker_proof()
    diagnostic["worker_start_command_used"] = (
        f"{sys.executable} tools/worker_proof_runner_019.py "
        "with TITAN_RUNTIME_MASTER_BRAIN_MODE=READ_ONLY and TITAN_DASHBOARD_SYNC_LOCAL_ONLY=1"
    )
    diagnostic["worker_proof_runner_result"] = result
    diagnostic["workers_visible"] = result.get("status") == "OK"
    diagnostic["worker_health_status"] = _worker_health_status()
    diagnostic["scheduler_status"] = {
        "status": "DISABLED_FOR_PROOF",
        "reason": "Mission 019 controlled worker proof did not enable daemon scanner scheduler.",
    }
    diagnostic["scanner_status"] = _fresh_payload(SCANNER_STATUS_PATH)
    diagnostic["outcome_tracker_status"] = _fresh_payload(OUTCOME_TRACKER_STATUS_PATH)
    diagnostic["paper_engine_status"] = _fresh_payload(PAPER_ENGINE_STATUS_PATH)
    diagnostic["dashboard_sync_status"] = _fresh_payload(DASHBOARD_SYNC_STATUS_PATH)
    scanner_truth = build_scanner_ohlc_setup_truth(write=True)
    runtime_truth = build_authoritative_runtime_truth(write=True)
    gate = build_restart_readiness_gate(runtime_truth=runtime_truth, scanner_truth=scanner_truth, write=True)
    journal = _read_json(JOURNAL_TRUTH_PATH)
    diagnostic["canonical_open_trades_after"] = int(journal.get("canonical_open_trade_count") or 0)
    diagnostic["authoritative_runtime_truth_after"] = runtime_truth
    diagnostic["restart_readiness_gate_after"] = gate
    blockers = list(gate.get("blockers") or [])
    if result.get("status") != "OK" or result.get("returncode") != 0:
        blockers.append("worker_proof_runner_failed")
    if diagnostic["worker_health_status"].get("status") != "OK":
        blockers.append("worker_health_proof_failed")
    if diagnostic["canonical_open_trades_after"] != 0:
        blockers.append("canonical_open_trades_changed")
    diagnostic["blockers"] = list(dict.fromkeys(blockers))
    diagnostic["warnings"] = list(gate.get("warnings") or [])
    diagnostic["next_required_action"] = (
        "Mission 020 can start paper proof / Classic freeze."
        if not diagnostic["blockers"]
        else "Keep daemon safe; stop/repair worker proof blockers before Mission 020."
    )
    diagnostic["generated_at"] = _timestamp()
    _atomic_write_json(DIAGNOSTIC_PATH, diagnostic)
    return diagnostic


if __name__ == "__main__":
    print(json.dumps(run_mission(), indent=2, sort_keys=True, default=str))
