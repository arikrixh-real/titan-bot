import pytest

from titan_echo import echo_mission_state as state_store
from titan_echo import echo_local_runner as runner


@pytest.fixture()
def echo_runtime(tmp_path, monkeypatch):
    echo_dir = tmp_path / "data" / "runtime" / "echo"
    monkeypatch.setattr(state_store, "ECHO_DIR", echo_dir)
    monkeypatch.setattr(state_store, "MISSIONS_DIR", echo_dir / "missions")
    monkeypatch.setattr(state_store, "EVIDENCE_DIR", echo_dir / "evidence")
    return echo_dir


def _mission(echo_runtime, mission_id="echo-local-test", **overrides):
    payload = {
        "schema": "titan.echo.mission_state.v2",
        "mission_id": mission_id,
        "status": "APPROVED",
        "execution_allowed": True,
        "approval": {"approved_by": "ari", "approved_at": "2026-06-06T00:00:00Z"},
        "approval_id": "approval-local",
        "approved_at": "2026-06-06T00:00:00Z",
        "next_step": "codex",
        "files": ["titan_echo/echo_local_runner.py"],
        "history": [],
    }
    payload.update(overrides)
    state_store.save_mission_state(payload)
    return payload


def _evidence(mission_id):
    return state_store.read_evidence(mission_id)


def test_unapproved_mission_blocked(echo_runtime):
    mission = _mission(echo_runtime, status="APPROVAL_REQUIRED", execution_allowed=True)

    result = runner.run_once(mission_id=mission["mission_id"], dry_run=True)

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "APPROVED_STATUS_REQUIRED"
    assert state_store.load_mission_state(mission["mission_id"])["status"] == "APPROVAL_REQUIRED"


def test_non_localhost_blocked(echo_runtime):
    mission = _mission(echo_runtime)

    result = runner.run_once(mission_id=mission["mission_id"], client_host="203.0.113.9", dry_run=True)

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "NON_LOCALHOST_EXECUTION_BLOCKED"


def test_approved_mission_runs_next_step(echo_runtime):
    mission = _mission(echo_runtime)

    result = runner.run_once(mission_id=mission["mission_id"], dry_run=True)
    reloaded = state_store.load_mission_state(mission["mission_id"])

    assert result["status"] == "CODEX_DONE"
    assert result["step"] == "codex"
    assert reloaded["status"] == "CODEX_DONE"
    assert reloaded["next_step"] == "verify"


def test_blocked_file_path_stops_mission(echo_runtime):
    mission = _mission(echo_runtime, files=["runtime_risk_watchdog.py"])

    result = runner.run_once(mission_id=mission["mission_id"], dry_run=True)
    reloaded = state_store.load_mission_state(mission["mission_id"])

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "BLOCKED_FILE_PATH"
    assert reloaded["status"] == "BLOCKED"


def test_evidence_written(echo_runtime):
    mission = _mission(echo_runtime)

    runner.run_once(mission_id=mission["mission_id"], dry_run=True)
    evidence = _evidence(mission["mission_id"])

    assert evidence
    assert evidence[-1]["step"] == "codex"
    assert evidence[-1]["status"] == "CODEX_DONE"


def test_resume_works_from_last_safe_step(echo_runtime):
    mission = _mission(echo_runtime, status="CODEX_DONE", next_step="verify")

    result = runner.run_once(mission_id=mission["mission_id"], dry_run=True)
    reloaded = state_store.load_mission_state(mission["mission_id"])

    assert result["step"] == "verify"
    assert result["status"] == "COMMIT_READY"
    assert reloaded["next_step"] == "commit"


def test_diagnostics_status_only_mission_reports_without_git(echo_runtime):
    mission = _mission(echo_runtime, execution_scope="diagnostics_status_only")

    codex = runner.run_once(mission_id=mission["mission_id"], dry_run=True)
    verify = runner.run_once(mission_id=mission["mission_id"], dry_run=True)
    report = runner.run_once(mission_id=mission["mission_id"], dry_run=True)
    reloaded = state_store.load_mission_state(mission["mission_id"])
    evidence = _evidence(mission["mission_id"])

    assert codex["status"] == "CODEX_DONE"
    assert verify["status"] == "VERIFY_DONE"
    assert verify["next_step"] == "report"
    assert report["status"] == "REPORTED"
    assert reloaded["status"] == "REPORTED"
    assert reloaded["next_step"] == ""
    assert [item["step"] for item in evidence] == ["codex", "verify", "report"]
    assert {item["step"] for item in evidence}.isdisjoint({"commit", "push", "pull"})


def test_normal_mission_still_requires_git_after_verify(echo_runtime):
    mission = _mission(echo_runtime, status="CODEX_DONE", next_step="verify")

    verify = runner.run_once(mission_id=mission["mission_id"], dry_run=True)
    commit = runner.run_once(mission_id=mission["mission_id"], dry_run=True)
    blocked = runner.run_once(mission_id=mission["mission_id"], dry_run=True)

    assert verify["status"] == "COMMIT_READY"
    assert verify["next_step"] == "commit"
    assert commit["status"] == "COMMITTED"
    assert commit["next_step"] == "push"
    assert blocked["status"] == "BLOCKED"
    assert blocked["reason"] == "GIT_PUSH_PULL_APPROVAL_REQUIRED"


def test_git_push_blocked_without_approval_flag(echo_runtime):
    mission = _mission(echo_runtime, status="COMMITTED", next_step="push")

    result = runner.run_once(mission_id=mission["mission_id"], dry_run=True)

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "GIT_PUSH_PULL_APPROVAL_REQUIRED"


def test_dry_run_mission_reaches_pushed_without_git_approval(echo_runtime):
    mission = _mission(echo_runtime, status="COMMITTED", next_step="push", dry_run=True)

    result = runner.run_once(mission_id=mission["mission_id"], dry_run=True)
    evidence = _evidence(mission["mission_id"])

    assert result["status"] == "PUSHED"
    assert state_store.load_mission_state(mission["mission_id"])["next_step"] == "pull"
    assert evidence[-1]["command"] == "SIMULATED_PUSH_DRY_RUN"
    assert "SIMULATED_PUSH_DRY_RUN" in evidence[-1]["stdout_tail"]


def test_dry_run_mission_reaches_pulled_without_git_approval(echo_runtime):
    mission = _mission(echo_runtime, status="PUSHED", next_step="pull", dry_run=True)

    result = runner.run_once(mission_id=mission["mission_id"], dry_run=True)
    evidence = _evidence(mission["mission_id"])

    assert result["status"] == "PULLED"
    assert state_store.load_mission_state(mission["mission_id"])["next_step"] == "report"
    assert evidence[-1]["command"] == "SIMULATED_PULL_DRY_RUN"
    assert "SIMULATED_PULL_DRY_RUN" in evidence[-1]["stdout_tail"]


def test_dry_run_push_pull_do_not_execute_subprocess(echo_runtime, monkeypatch):
    calls = []

    def fail_if_called(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("subprocess.run must not execute during dry-run push/pull")

    monkeypatch.setattr("titan_echo.echo_git_adapter.subprocess.run", fail_if_called)
    mission = _mission(echo_runtime, status="COMMITTED", next_step="push", dry_run=True)

    push = runner.run_once(mission_id=mission["mission_id"], dry_run=True)
    pull = runner.run_once(mission_id=mission["mission_id"], dry_run=True)

    assert push["status"] == "PUSHED"
    assert pull["status"] == "PULLED"
    assert calls == []


def test_git_push_runs_with_approval_flag(echo_runtime):
    mission = _mission(echo_runtime, status="COMMITTED", next_step="push", git_push_pull_approved=True)

    result = runner.run_once(mission_id=mission["mission_id"], dry_run=True)

    assert result["status"] == "PUSHED"
    assert state_store.load_mission_state(mission["mission_id"])["next_step"] == "pull"


def test_deploy_restart_blocked_without_approval_flag(echo_runtime):
    mission = _mission(echo_runtime, deploy_requested=True)

    result = runner.run_once(mission_id=mission["mission_id"], dry_run=True)

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "DEPLOY_RESTART_APPROVAL_REQUIRED"


def test_runner_processes_one_mission_then_stops(echo_runtime):
    first = _mission(echo_runtime, mission_id="echo-local-one")
    second = _mission(echo_runtime, mission_id="echo-local-two")

    result = runner.run_once(dry_run=True)

    assert result["runner_stopped"] is True
    assert state_store.load_mission_state(first["mission_id"])["status"] == "CODEX_DONE"
    assert state_store.load_mission_state(second["mission_id"])["status"] == "APPROVED"


def test_missions_are_read_from_runtime_missions_dir(echo_runtime):
    mission = _mission(echo_runtime)

    assert (echo_runtime / "missions" / f"{mission['mission_id']}.json").exists()
    result = runner.run_once(dry_run=True)

    assert result["mission_id"] == mission["mission_id"]
