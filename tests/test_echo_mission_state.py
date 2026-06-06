import json

import pytest

from titan_echo import echo_mission_state as state_store
from titan_echo.echo_relay_auth import relay_execution_hardening_status
from titan_echo.echo_mission_runner import APPROVAL_CONFIRM, approve_mission, create_mission, mission_report, run_next
from titan_echo.echo_relay_api import FASTAPI_AVAILABLE, app


pytestmark = pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI unavailable")


@pytest.fixture()
def echo_runtime(tmp_path, monkeypatch):
    echo_dir = tmp_path / "data" / "runtime" / "echo"
    monkeypatch.setattr(state_store, "ECHO_DIR", echo_dir)
    monkeypatch.setattr(state_store, "MISSIONS_DIR", echo_dir / "missions")
    monkeypatch.setattr(state_store, "EVIDENCE_DIR", echo_dir / "evidence")
    monkeypatch.setenv("ECHO_RELAY_ENABLED", "true")
    monkeypatch.setenv("ECHO_RELAY_API_KEY", "test-relay-key")
    monkeypatch.setenv("ECHO_RELAY_LOCALHOST_ONLY", "true")
    return echo_dir


@pytest.fixture()
def client(echo_runtime):
    from fastapi.testclient import TestClient

    return TestClient(app)


def _approve_payload(mission):
    return {
        "mission_id": mission["mission_id"],
        "approval_id": mission["approval_id"],
        "confirm": APPROVAL_CONFIRM,
    }


def test_create_mission_gives_created_or_approval_required(echo_runtime):
    mission = create_mission({"objective": "test mission"})

    assert mission["status"] in {"CREATED", "APPROVAL_REQUIRED"}
    assert state_store.mission_path(mission["mission_id"]).exists()


def test_run_without_approval_blocks(echo_runtime):
    mission = create_mission({"objective": "approval gate"})

    result = run_next({"mission_id": mission["mission_id"]})

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "APPROVAL_REQUIRED"


def test_approve_mission_works_only_with_valid_approval(echo_runtime):
    mission = create_mission({"objective": "approval"})

    bad = approve_mission({**_approve_payload(mission), "approval_id": "wrong"})
    good = approve_mission(_approve_payload(mission))

    assert bad["status"] == "BLOCKED"
    assert bad["reason"] == "APPROVAL_ID_MISMATCH"
    assert good["status"] == "APPROVED"


def test_codex_step_cannot_run_before_approval(echo_runtime):
    mission = create_mission({"objective": "codex guard"})

    result = run_next({"mission_id": mission["mission_id"], "step": "codex"})

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "APPROVAL_REQUIRED"


def test_verify_cannot_run_before_codex_done(echo_runtime):
    mission = create_mission({"objective": "verify guard"})
    approve_mission(_approve_payload(mission))

    result = run_next({"mission_id": mission["mission_id"], "step": "verify"})

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "VERIFY_CANNOT_RUN_FROM_APPROVED"


def test_commit_cannot_run_before_verify_done(echo_runtime):
    mission = create_mission({"objective": "commit guard"})
    approve_mission(_approve_payload(mission))
    codex = run_next({"mission_id": mission["mission_id"], "step": "codex"})

    result = run_next({"mission_id": codex["mission_id"], "step": "commit"})

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "COMMIT_CANNOT_RUN_FROM_CODEX_DONE"


def test_push_cannot_run_before_commit_done(echo_runtime):
    mission = create_mission({"objective": "push guard"})
    approve_mission(_approve_payload(mission))
    run_next({"mission_id": mission["mission_id"], "step": "codex"})
    run_next({"mission_id": mission["mission_id"], "step": "verify"})

    result = run_next({"mission_id": mission["mission_id"], "step": "push"})

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "PUSH_CANNOT_RUN_FROM_COMMIT_READY"


def test_pull_cannot_run_before_push_done(echo_runtime):
    mission = create_mission({"objective": "pull guard"})
    approve_mission(_approve_payload(mission))
    run_next({"mission_id": mission["mission_id"], "step": "codex"})
    run_next({"mission_id": mission["mission_id"], "step": "verify"})
    run_next({"mission_id": mission["mission_id"], "step": "commit"})

    result = run_next({"mission_id": mission["mission_id"], "step": "pull"})

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "PULL_CANNOT_RUN_FROM_COMMITTED"


def test_report_requires_evidence(echo_runtime):
    mission = create_mission({"objective": "report guard"})
    mission["status"] = "PULLED"
    mission["next_step"] = "report"
    state_store.save_mission_state(mission)

    result = mission_report(mission["mission_id"])

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "REPORT_REQUIRES_EVIDENCE"


def test_invalid_mission_id_fails_closed(echo_runtime):
    result = run_next({"mission_id": "../escape", "step": "codex"})

    assert result["status"] == "FAILED"
    assert result["error"] == "INVALID_MISSION_ID"


def test_disabled_relay_blocks_execution(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.delenv("ECHO_RELAY_ENABLED", raising=False)
    monkeypatch.delenv("ECHO_RELAY_API_KEY", raising=False)
    response = TestClient(app).post("/relay/mission/run_next", json={"mission_id": "echo-disabled"})

    assert response.status_code == 200
    assert response.json()["status"] == "RELAY_DISABLED"


def test_invalid_auth_fails_closed(client):
    response = client.post(
        "/relay/mission/create",
        headers={"X-ECHO-RELAY-KEY": "wrong"},
        json={"objective": "auth guard"},
    )

    assert response.status_code == 401


def test_invalid_auth_blocks_execution(client):
    response = client.post(
        "/relay/mission/run_next",
        headers={"X-ECHO-RELAY-KEY": "wrong"},
        json={"mission_id": "echo-auth-invalid"},
    )

    assert response.status_code == 401


def test_missing_auth_blocks_execution(client):
    response = client.post("/relay/mission/run_next", json={"mission_id": "echo-auth-missing"})

    assert response.status_code == 401


def test_non_localhost_execution_request_blocks_when_localhost_only_enabled(echo_runtime):
    from fastapi.testclient import TestClient

    remote_client = TestClient(app, client=("203.0.113.7", 50000))
    response = remote_client.post(
        "/relay/mission/run_next",
        headers={"X-ECHO-RELAY-KEY": "test-relay-key"},
        json={"mission_id": "echo-remote"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "NON_LOCALHOST_EXECUTION_BLOCKED"
    assert response.json()["detail"]["localhost_only_execution"] is True
    assert response.json()["detail"]["execution_allowed"] is False


def test_localhost_execution_request_passes_guard_when_auth_and_enabled_mode_are_valid(client):
    mission = create_mission({"objective": "localhost pass"})
    approve_mission(_approve_payload(mission))

    response = client.post(
        "/relay/mission/run_next",
        headers={"X-ECHO-RELAY-KEY": "test-relay-key"},
        json={"mission_id": mission["mission_id"], "step": "codex"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "CODEX_DONE"


def test_hardening_status_reports_exact_reason_when_blocked(echo_runtime):
    payload = relay_execution_hardening_status(
        provided_key=None,
        client_host="127.0.0.1",
        execution_requested=True,
    )

    assert payload["relay_enabled"] is True
    assert payload["auth_configured"] is True
    assert payload["localhost_only_execution"] is True
    assert payload["execution_allowed"] is False
    assert payload["reason"] == "AUTH_MISSING"


def test_mission_run_next_respects_service_hardening_guard(echo_runtime):
    from fastapi.testclient import TestClient

    mission = create_mission({"objective": "remote run_next guard"})
    approve_mission(_approve_payload(mission))
    remote_client = TestClient(app, client=("198.51.100.10", 50000))

    response = remote_client.post(
        "/relay/mission/run_next",
        headers={"X-ECHO-RELAY-KEY": "test-relay-key"},
        json={"mission_id": mission["mission_id"], "step": "codex"},
    )
    reloaded = state_store.load_mission_state(mission["mission_id"])

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "NON_LOCALHOST_EXECUTION_BLOCKED"
    assert reloaded["status"] == "APPROVED"


def test_evidence_jsonl_is_written_and_survives_reload(echo_runtime):
    mission = create_mission({"objective": "evidence"})
    approve_mission(_approve_payload(mission))
    result = run_next(
        {
            "mission_id": mission["mission_id"],
            "step": "codex",
            "stdout_tail": "ok",
            "files_touched": ["titan_echo/echo_mission_state.py"],
        }
    )

    evidence_path = state_store.evidence_path(mission["mission_id"])
    lines = evidence_path.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    reloaded_state = state_store.load_mission_state(mission["mission_id"])
    reloaded_evidence = state_store.read_evidence(mission["mission_id"])

    assert result["status"] == "CODEX_DONE"
    assert reloaded_state["status"] == "CODEX_DONE"
    assert records
    assert reloaded_evidence[-1]["step"] == "codex"
    assert {"timestamp", "mission_id", "step", "status", "command", "return_code", "stdout_tail", "stderr_tail", "files_touched", "error"} <= set(records[-1])
