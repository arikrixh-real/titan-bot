import json
from datetime import datetime, timedelta
from pathlib import Path

from utils.market_hours import IST

from restart_readiness_gate import build_restart_readiness_gate, classify_lock
from master_brain_activation_guard import BROKER_APPROVAL_TOKEN


NOW = datetime(2026, 6, 7, 12, 0, tzinfo=IST)


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def runtime_truth(scanner="STALE", ohlc="STALE", setup="STALE"):
    return {
        "components": {
            "daemon": {"status": "STOPPED"},
            "workers": {"status": "STALE"},
            "scheduler": {"status": "STALE"},
            "scanner": {"status": scanner},
            "ohlc_health": {"status": ohlc},
            "setup_engine": {"status": setup},
        },
        "summary": {"overall_status": "STOPPED", "restart_blockers": ["daemon"]},
    }


def scanner_truth(scanner="STALE", ohlc="STALE", setup="STALE"):
    return {
        "scanner_status": {"status": scanner},
        "ohlc_status": {"status": ohlc},
        "setup_engine_status": {"status": setup},
    }


def master_guard(status="READ_ONLY"):
    return {
        "status": status,
        "can_call_broker": False,
        "can_send_telegram": False,
    }


def journal_truth(canonical=0, legacy=True):
    return {
        "canonical_open_trade_count": canonical,
        "legacy_open_rows_warning": legacy,
    }


def dashboard_truth():
    return {"dashboard_overall_status": "STOPPED"}


def test_stale_lock_with_no_process_becomes_stale_lock(tmp_path):
    lock = tmp_path / "old.lock"
    _write_json(lock, {"pid": 1234, "acquired_at_ist": (NOW - timedelta(hours=1)).isoformat()})

    result = classify_lock(lock, now=NOW, process_checker=lambda pid: False)

    assert result["status"] == "STALE_LOCK"


def test_active_lock_with_live_pid_blocks_restart(tmp_path):
    lock_dir = tmp_path / "locks"
    _write_json(lock_dir / "active.lock", {"pid": 1234, "acquired_at_ist": NOW.isoformat()})

    gate = build_restart_readiness_gate(
        runtime_truth=runtime_truth("LIVE", "LIVE", "REAL_SETUP_ENGINE_CONNECTED"),
        journal_truth=journal_truth(0, False),
        dashboard_truth=dashboard_truth(),
        master_guard=master_guard(),
        scanner_truth=scanner_truth("LIVE", "LIVE", "REAL_SETUP_ENGINE_CONNECTED"),
        lock_dir=lock_dir,
        env={},
        now=NOW,
        write=False,
        process_checker=lambda pid: True,
    )

    assert gate["lock_status"] == "ACTIVE_LOCK"
    assert "active_locks_present" in gate["blockers"]
    assert gate["overall_restart_allowed"] is False


def test_live_daemon_lock_allows_worker_proof_gate(tmp_path):
    lock_dir = tmp_path / "locks"
    _write_json(lock_dir / "titan_daemon.lock", {"name": "titan_daemon", "pid": 1234, "acquired_at_ist": NOW.isoformat()})

    gate = build_restart_readiness_gate(
        runtime_truth=runtime_truth("LIVE", "LIVE", "REAL_SETUP_ENGINE_CONNECTED") | {"components": {"daemon": {"status": "LIVE"}, "workers": {"status": "STALE"}, "scheduler": {"status": "STALE"}, "scanner": {"status": "LIVE"}, "ohlc_health": {"status": "LIVE"}, "setup_engine": {"status": "REAL_SETUP_ENGINE_CONNECTED"}}},
        journal_truth=journal_truth(0, False),
        dashboard_truth=dashboard_truth(),
        master_guard=master_guard(),
        scanner_truth=scanner_truth("LIVE", "LIVE", "REAL_SETUP_ENGINE_CONNECTED"),
        lock_dir=lock_dir,
        env={},
        now=NOW,
        write=False,
        process_checker=lambda pid: True,
    )

    assert "active_locks_present" not in gate["blockers"]
    assert gate["safe_to_start_workers"] is True


def test_unknown_lock_blocks_restart(tmp_path):
    lock_dir = tmp_path / "locks"
    _write_json(lock_dir / "unknown.lock", {"acquired_at_ist": NOW.isoformat()})

    gate = build_restart_readiness_gate(
        runtime_truth=runtime_truth("LIVE", "LIVE", "REAL_SETUP_ENGINE_CONNECTED"),
        journal_truth=journal_truth(0, False),
        dashboard_truth=dashboard_truth(),
        master_guard=master_guard(),
        scanner_truth=scanner_truth("LIVE", "LIVE", "REAL_SETUP_ENGINE_CONNECTED"),
        lock_dir=lock_dir,
        env={},
        now=NOW,
        write=False,
        process_checker=lambda pid: False,
    )

    assert gate["lock_status"] == "UNKNOWN_LOCK"
    assert "unknown_locks_present" in gate["blockers"]


def test_master_brain_real_blocked_does_not_allow_real_execution(tmp_path):
    gate = build_restart_readiness_gate(
        runtime_truth=runtime_truth("LIVE", "LIVE", "REAL_SETUP_ENGINE_CONNECTED"),
        journal_truth=journal_truth(0, False),
        dashboard_truth=dashboard_truth(),
        master_guard=master_guard("REAL_BLOCKED"),
        scanner_truth=scanner_truth("LIVE", "LIVE", "REAL_SETUP_ENGINE_CONNECTED"),
        lock_dir=tmp_path / "locks",
        env={},
        now=NOW,
        write=False,
        process_checker=lambda pid: False,
    )

    assert gate["master_brain_guard_status"] == "REAL_BLOCKED"
    assert "master_brain_guard_unsafe:REAL_BLOCKED" not in gate["blockers"]


def test_canonical_open_trades_zero_passes_journal_gate_with_legacy_warning(tmp_path):
    gate = build_restart_readiness_gate(
        runtime_truth=runtime_truth("LIVE", "LIVE", "REAL_SETUP_ENGINE_CONNECTED"),
        journal_truth=journal_truth(0, True),
        dashboard_truth=dashboard_truth(),
        master_guard=master_guard(),
        scanner_truth=scanner_truth("LIVE", "LIVE", "REAL_SETUP_ENGINE_CONNECTED"),
        lock_dir=tmp_path / "locks",
        env={},
        now=NOW,
        write=False,
        process_checker=lambda pid: False,
    )

    assert gate["journal_truth_status"] == "CANONICAL_CLEAN_LEGACY_WARNING"
    assert "canonical_open_trades_not_zero" not in gate["blockers"]
    assert "legacy_open_rows_quarantined_warning" in gate["warnings"]


def test_restart_allowed_false_while_scanner_ohlc_setup_stale(tmp_path):
    gate = build_restart_readiness_gate(
        runtime_truth=runtime_truth(),
        journal_truth=journal_truth(0, False),
        dashboard_truth=dashboard_truth(),
        master_guard=master_guard(),
        scanner_truth=scanner_truth(),
        lock_dir=tmp_path / "locks",
        env={},
        now=NOW,
        write=False,
        process_checker=lambda pid: False,
    )

    assert gate["overall_restart_allowed"] is False
    assert "scanner_ohlc_setup_refresh_required" in gate["blockers"]


def test_safe_to_refresh_data_true_only_when_execution_disabled(tmp_path):
    kwargs = dict(
        runtime_truth=runtime_truth(),
        journal_truth=journal_truth(0, False),
        dashboard_truth=dashboard_truth(),
        master_guard=master_guard(),
        scanner_truth=scanner_truth(),
        lock_dir=tmp_path / "locks",
        now=NOW,
        write=False,
        process_checker=lambda pid: False,
    )
    safe = build_restart_readiness_gate(env={}, **kwargs)
    unsafe = build_restart_readiness_gate(
        env={"TITAN_BROKER_LIVE_EXECUTION": BROKER_APPROVAL_TOKEN},
        **kwargs,
    )

    assert safe["safe_to_refresh_data"] is True
    assert unsafe["safe_to_refresh_data"] is False
    assert "broker_live_execution_enabled" in unsafe["blockers"]
