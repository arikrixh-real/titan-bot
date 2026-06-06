import json

import pytest

from titan_echo import echo_mission_state as state_store
from titan_echo.echo_relay_api import FASTAPI_AVAILABLE, app


pytestmark = pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI unavailable")


class Completed:
    def __init__(self, returncode=0, stdout="started", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


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


@pytest.fixture()
def external_client(echo_runtime):
    from fastapi.testclient import TestClient

    return TestClient(app, client=("203.0.113.44", 50000))


def headers():
    return {"X-ECHO-RELAY-KEY": "test-relay-key"}


def valid_payload(**overrides):
    payload = {
        "approved_by": "ari",
        "approval_id": "approval-intake-1",
        "title": "ECHO diagnostics status",
        "instructions": "Inspect ECHO relay mission status and write evidence only.",
        "execution_scope": "echo_only",
        "dry_run": True,
    }
    payload.update(overrides)
    return payload


def test_valid_intake_creates_approved_mission(client, echo_runtime, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Completed()

    monkeypatch.setattr("titan_echo.echo_relay_api.subprocess.run", fake_run)

    response = client.post("/relay/mission/intake-approved", headers=headers(), json=valid_payload())
    payload = response.json()
    mission = state_store.load_mission_state(payload["mission_id"])

    assert response.status_code == 200
    assert payload["status"] == "APPROVED"
    assert payload["runner_triggered"] is True
    assert payload["reason"] == "RUNNER_TRIGGERED"
    assert (echo_runtime / "missions" / f"{payload['mission_id']}.json").exists()
    assert mission["status"] == "APPROVED"
    assert mission["execution_allowed"] is True
    assert mission["dry_run"] is True
    assert calls[0][0] == ["sudo", "systemctl", "start", "titan-echo-runner"]


def test_invalid_auth_blocks_intake(client):
    response = client.post(
        "/relay/mission/intake-approved",
        headers={"X-ECHO-RELAY-KEY": "wrong"},
        json=valid_payload(),
    )

    assert response.status_code == 401


def test_external_intake_approved_reachable_with_valid_auth(external_client, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return Completed()

    monkeypatch.setattr("titan_echo.echo_relay_api.subprocess.run", fake_run)

    response = external_client.post("/relay/mission/intake-approved", headers=headers(), json=valid_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
    assert response.json()["runner_triggered"] is True
    assert calls == [["sudo", "systemctl", "start", "titan-echo-runner"]]


def test_external_intake_approved_blocks_invalid_auth(external_client):
    response = external_client.post(
        "/relay/mission/intake-approved",
        headers={"X-ECHO-RELAY-KEY": "wrong"},
        json=valid_payload(),
    )

    assert response.status_code == 401


def test_external_other_mission_routes_remain_blocked(external_client):
    for path in (
        "/relay/mission/create",
        "/relay/mission/approve",
        "/relay/mission/status",
        "/relay/mission/resume",
        "/relay/mission/approve-step",
    ):
        response = external_client.post(path, headers=headers(), json={"objective": "blocked"})
        assert response.status_code == 403
        assert response.json()["reason"] == "ONLY_MISSION_INTAKE_APPROVED_EXPOSED"


def test_external_execution_codex_deploy_rollback_remain_blocked(external_client):
    paths = (
        "/relay/execution/authorize",
        "/relay/codex/run-approved",
        "/relay/deploy/run-approved",
        "/relay/rollback/request",
        "/relay/actions/status",
    )

    for path in paths:
        response = external_client.post(path, headers=headers(), json={"mission_id": "blocked"})
        assert response.status_code == 403
        assert response.json()["status"] == "RELAY_EXTERNAL_ROUTE_BLOCKED"


def test_missing_approval_blocks(client, monkeypatch):
    calls = []
    monkeypatch.setattr("titan_echo.echo_relay_api.subprocess.run", lambda *args, **kwargs: calls.append(args))

    response = client.post(
        "/relay/mission/intake-approved",
        headers=headers(),
        json=valid_payload(approval_id=""),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "BLOCKED"
    assert response.json()["reason"] == "MISSING_APPROVAL_FIELDS"
    assert calls == []


def test_unsafe_scope_blocks(client, monkeypatch):
    calls = []
    monkeypatch.setattr("titan_echo.echo_relay_api.subprocess.run", lambda *args, **kwargs: calls.append(args))

    response = client.post(
        "/relay/mission/intake-approved",
        headers=headers(),
        json=valid_payload(execution_scope="filesystem_mutation"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "BLOCKED"
    assert response.json()["reason"] == "UNSAFE_SCOPE"
    assert calls == []


def test_trading_scope_blocks(client, monkeypatch):
    calls = []
    monkeypatch.setattr("titan_echo.echo_relay_api.subprocess.run", lambda *args, **kwargs: calls.append(args))

    response = client.post(
        "/relay/mission/intake-approved",
        headers=headers(),
        json=valid_payload(instructions="Mutate broker trading execution and risk settings."),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "BLOCKED"
    assert response.json()["reason"] == "TRADING_OR_PROTECTED_SCOPE_BLOCKED"
    assert calls == []


def test_arbitrary_command_impossible(client, monkeypatch):
    calls = []
    monkeypatch.setattr("titan_echo.echo_relay_api.subprocess.run", lambda *args, **kwargs: calls.append(args))

    response = client.post(
        "/relay/mission/intake-approved",
        headers=headers(),
        json=valid_payload(command=["sh", "-c", "touch /tmp/unsafe"]),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "BLOCKED"
    assert response.json()["reason"] == "ARBITRARY_COMMAND_NOT_ALLOWED"
    assert calls == []


def test_runner_trigger_uses_fixed_systemctl_only(client, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return Completed(returncode=5, stdout="", stderr="failed")

    monkeypatch.setattr("titan_echo.echo_relay_api.subprocess.run", fake_run)

    response = client.post("/relay/mission/intake-approved", headers=headers(), json=valid_payload())
    payload = response.json()
    evidence = state_store.read_evidence(payload["mission_id"])

    assert response.status_code == 200
    assert payload["status"] == "APPROVED"
    assert payload["runner_triggered"] is False
    assert payload["reason"] == "SYSTEMCTL_FAILED"
    assert calls == [["sudo", "systemctl", "start", "titan-echo-runner"]]
    assert evidence[-1]["command"] == "sudo systemctl start titan-echo-runner"


def test_mission_file_contains_approval_and_instructions(client, echo_runtime, monkeypatch):
    monkeypatch.setattr("titan_echo.echo_relay_api.subprocess.run", lambda *args, **kwargs: Completed())

    response = client.post(
        "/relay/mission/intake-approved",
        headers=headers(),
        json=valid_payload(instructions="Check ECHO mission intake evidence."),
    )
    mission_path = echo_runtime / "missions" / f"{response.json()['mission_id']}.json"
    mission = json.loads(mission_path.read_text(encoding="utf-8"))

    assert mission["approval"]["approved_by"] == "ari"
    assert mission["approval"]["approval_id"] == "approval-intake-1"
    assert mission["instructions"] == "Check ECHO mission intake evidence."
    assert mission["safety"]["arbitrary_subprocess_command"] is False
