import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from master_brain_activation_guard import BROKER_APPROVAL_TOKEN, TELEGRAM_APPROVAL_TOKEN
from restart_readiness_gate import build_restart_readiness_gate, classify_lock
from runtime_truth import build_authoritative_runtime_truth, process_visible
from scanner_ohlc_setup_truth import build_scanner_ohlc_setup_truth
from utils.market_hours import as_ist_datetime


RUNTIME_DIR = Path("data") / "runtime"
DIAGNOSTIC_PATH = RUNTIME_DIR / "controlled_daemon_restart_mission_018.json"
DAEMON_HEALTH_PATH = RUNTIME_DIR / "daemon_health.json"
DAEMON_HEARTBEAT_PATH = RUNTIME_DIR / "titan_heartbeat.json"
DAEMON_LOCK_PATH = RUNTIME_DIR / "locks" / "titan_daemon.lock"
JOURNAL_TRUTH_PATH = RUNTIME_DIR / "journal_truth_unification.json"
MASTER_GUARD_PATH = RUNTIME_DIR / "master_brain_activation_guard.json"
WORKER_HEALTH_PATH = RUNTIME_DIR / "worker_health.json"
DAEMON_STDOUT_PATH = RUNTIME_DIR / "controlled_daemon_restart_mission_018_daemon.log"


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
        "safe_to_start_daemon": bool(gate.get("safe_to_start_daemon")),
        "safe_to_start_workers": bool(gate.get("safe_to_start_workers")),
        "lock_status": gate.get("lock_status"),
        "canonical_open_trades": canonical_open,
        "master_brain_effective_mode": master_guard.get("effective_mode") or master_guard.get("status"),
        "broker_order_execution_disabled": broker_disabled,
        "telegram_disabled": telegram_disabled,
        "gate_blockers": list(gate.get("blockers") or []),
        "gate_warnings": list(gate.get("warnings") or []),
    }
    precheck["passed"] = bool(
        precheck["safe_to_start_daemon"]
        and not precheck["safe_to_start_workers"]
        and precheck["lock_status"] == "NO_LOCKS"
        and canonical_open == 0
        and str(precheck["master_brain_effective_mode"]).upper() == "READ_ONLY"
        and broker_disabled
        and telegram_disabled
    )
    return precheck


def _worker_snapshot():
    payload = _read_json(WORKER_HEALTH_PATH)
    fresh_live = []
    for name, item in payload.items():
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").upper()
        if status in {"RUNNING", "STARTING", "ALIVE"}:
            fresh_live.append(name)
    return {
        "path": str(WORKER_HEALTH_PATH).replace("\\", "/"),
        "mtime_ns": WORKER_HEALTH_PATH.stat().st_mtime_ns if WORKER_HEALTH_PATH.exists() else None,
        "running_or_starting_markers": fresh_live,
    }


def _start_daemon():
    env = os.environ.copy()
    env["TITAN_RUNTIME_MASTER_BRAIN_MODE"] = "READ_ONLY"
    env["TITAN_CONTINUOUS_WORKERS"] = "0"
    env["TITAN_SCANNER_SCHEDULER_ENABLED"] = "0"
    env["TITAN_DAEMON_PROOF_ONLY"] = "1"
    env.pop("TITAN_BROKER_LIVE_EXECUTION", None)
    env.pop("TITAN_TELEGRAM_ALERTS", None)
    DAEMON_STDOUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    stdout = DAEMON_STDOUT_PATH.open("a", encoding="utf-8")
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    process = subprocess.Popen(
        [sys.executable, "titan_daemon.py"],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        close_fds=True,
    )
    stdout.close()
    return process.pid


def _fresh(payload, max_age_seconds=15):
    value = payload.get("timestamp_ist") or payload.get("acquired_at_ist")
    try:
        dt = as_ist_datetime(__import__("datetime").datetime.fromisoformat(str(value)))
    except Exception:
        return False
    return (as_ist_datetime() - dt).total_seconds() <= max_age_seconds


def _wait_for_proof(start_pid, timeout_seconds=20):
    deadline = time.monotonic() + timeout_seconds
    latest = {}
    while time.monotonic() < deadline:
        health = _read_json(DAEMON_HEALTH_PATH)
        heartbeat = _read_json(DAEMON_HEARTBEAT_PATH)
        lock = _read_json(DAEMON_LOCK_PATH)
        lock_status = classify_lock(DAEMON_LOCK_PATH)
        daemon_pid = health.get("pid") or heartbeat.get("pid") or lock.get("pid") or start_pid
        visible = process_visible(daemon_pid)
        latest = {
            "daemon_pid": daemon_pid,
            "daemon_process_visible": visible,
            "daemon_lock_status": lock_status.get("status"),
            "daemon_lock_fresh": lock_status.get("status") == "ACTIVE_LOCK",
            "daemon_health_status": health.get("status"),
            "daemon_health_fresh": _fresh(health),
            "daemon_heartbeat_status": heartbeat.get("status"),
            "daemon_heartbeat_fresh": _fresh(heartbeat),
            "daemon_runtime_mode": health.get("runtime_mode"),
            "daemon_mode": health.get("mode"),
            "daemon_proof_passed": bool(
                visible
                and lock_status.get("status") == "ACTIVE_LOCK"
                and str(health.get("status") or "").upper() in {"RUNNING", "STARTING", "IDLE"}
                and _fresh(health)
                and str(heartbeat.get("status") or "").upper() in {"ALIVE", "RUNNING"}
                and _fresh(heartbeat)
            ),
        }
        if latest["daemon_proof_passed"]:
            return latest
        time.sleep(1)
    return latest


def run_mission():
    precheck = _precheck()
    before_workers = _worker_snapshot()
    diagnostic = {
        "generated_at": _timestamp(),
        "mission": "018",
        "mode": "controlled_daemon_start_proof_only",
        "precheck": precheck,
        "start_command_used": None,
        "daemon_pid": None,
        "daemon_process_visible": False,
        "daemon_lock_status": None,
        "daemon_heartbeat_status": None,
        "workers_started": False,
        "broker_order_api_called": False,
        "trading_api_called": False,
        "telegram_sent": False,
        "journal_mutation": False,
        "canonical_open_trades_after": None,
        "authoritative_runtime_truth_after": {},
        "restart_readiness_gate_after": {},
        "safe_to_start_workers": False,
        "blockers": [],
        "warnings": [],
        "next_required_action": None,
        "safety": {
            "daemon_only": True,
            "continuous_workers": False,
            "live_trading": False,
            "telegram_sent": False,
            "journal_mutation": False,
            "supabase_trade_order_state": False,
            "hft_built": False,
        },
    }
    if not precheck["passed"]:
        diagnostic["blockers"] = ["precheck_failed"]
        diagnostic["next_required_action"] = "Do not start daemon; repair precheck blockers first."
        _atomic_write_json(DIAGNOSTIC_PATH, diagnostic)
        return diagnostic

    start_pid = _start_daemon()
    diagnostic["start_command_used"] = (
        "TITAN_RUNTIME_MASTER_BRAIN_MODE=READ_ONLY "
        "TITAN_CONTINUOUS_WORKERS=0 "
        "TITAN_SCANNER_SCHEDULER_ENABLED=0 "
        "TITAN_DAEMON_PROOF_ONLY=1 "
        f"{sys.executable} titan_daemon.py"
    )
    proof = _wait_for_proof(start_pid)
    diagnostic.update(
        {
            "daemon_pid": proof.get("daemon_pid"),
            "daemon_process_visible": bool(proof.get("daemon_process_visible")),
            "daemon_lock_status": proof.get("daemon_lock_status"),
            "daemon_heartbeat_status": proof.get("daemon_heartbeat_status"),
            "daemon_health_status": proof.get("daemon_health_status"),
            "daemon_health_fresh": proof.get("daemon_health_fresh"),
            "daemon_heartbeat_fresh": proof.get("daemon_heartbeat_fresh"),
            "daemon_runtime_mode": proof.get("daemon_runtime_mode"),
            "daemon_mode": proof.get("daemon_mode"),
        }
    )

    scanner_truth = build_scanner_ohlc_setup_truth(write=True)
    runtime_truth = build_authoritative_runtime_truth(write=True)
    gate = build_restart_readiness_gate(runtime_truth=runtime_truth, scanner_truth=scanner_truth, write=True)
    after_workers = _worker_snapshot()
    journal = _read_json(JOURNAL_TRUTH_PATH)
    diagnostic["workers_started"] = bool(after_workers.get("mtime_ns") != before_workers.get("mtime_ns"))
    diagnostic["worker_status_proof"] = {
        "before": before_workers,
        "after": after_workers,
        "no_worker_health_update": not diagnostic["workers_started"],
    }
    diagnostic["canonical_open_trades_after"] = int(journal.get("canonical_open_trade_count") or 0)
    diagnostic["authoritative_runtime_truth_after"] = runtime_truth
    diagnostic["restart_readiness_gate_after"] = gate
    diagnostic["safe_to_start_workers"] = bool(gate.get("safe_to_start_workers"))
    diagnostic["blockers"] = list(gate.get("blockers") or [])
    if not proof.get("daemon_proof_passed"):
        diagnostic["blockers"].append("daemon_proof_failed")
    if diagnostic["workers_started"]:
        diagnostic["blockers"].append("worker_health_changed_during_daemon_proof")
    if diagnostic["canonical_open_trades_after"] != 0:
        diagnostic["blockers"].append("canonical_open_trades_changed")
    diagnostic["warnings"] = list(gate.get("warnings") or [])
    diagnostic["next_required_action"] = (
        "Mission 019 can start controlled workers."
        if not diagnostic["blockers"] and diagnostic["safe_to_start_workers"]
        else "Keep workers stopped; resolve daemon proof blockers."
    )
    diagnostic["generated_at"] = _timestamp()
    _atomic_write_json(DIAGNOSTIC_PATH, diagnostic)
    return diagnostic


if __name__ == "__main__":
    print(json.dumps(run_mission(), indent=2, sort_keys=True, default=str))
