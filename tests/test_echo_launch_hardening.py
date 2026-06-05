import pytest

from titan_echo.echo_relay_api import FASTAPI_AVAILABLE, app
from titan_echo.echo_relay_auth import require_relay_key


pytestmark = pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI unavailable")


def _client():
    from fastapi.testclient import TestClient

    return TestClient(app)


def test_relay_key_fails_closed_when_relay_disabled(monkeypatch):
    monkeypatch.delenv("ECHO_RELAY_ENABLED", raising=False)
    monkeypatch.delenv("ECHO_RELAY_API_KEY", raising=False)

    with pytest.raises(Exception):
        require_relay_key(None)


def test_disabled_mode_blocks_everything_except_health(monkeypatch):
    monkeypatch.delenv("ECHO_RELAY_ENABLED", raising=False)
    monkeypatch.delenv("ECHO_RELAY_API_KEY", raising=False)

    client = _client()

    health = client.get("/relay/health")
    blocked = client.get("/relay/inspect/health")
    codex = client.post(
        "/relay/codex/run-approved",
        json={"mission_id": "fake", "approval_id": "fake", "prompt": "inspect relay"},
    )

    assert health.status_code == 200
    assert health.json()["status"] == "RELAY_DISABLED"
    assert blocked.status_code == 200
    assert blocked.json()["status"] == "RELAY_DISABLED"
    assert codex.status_code == 200
    assert codex.json()["status"] == "RELAY_DISABLED"


def test_direct_actions_reject_raw_approval_without_persisted_mission(monkeypatch):
    monkeypatch.setenv("ECHO_RELAY_ENABLED", "true")
    monkeypatch.setenv("ECHO_RELAY_API_KEY", "test-relay-key")

    client = _client()
    headers = {"X-ECHO-RELAY-KEY": "test-relay-key"}

    codex = client.post(
        "/relay/codex/run-approved",
        headers=headers,
        json={"mission_id": "missing-mission", "approval_id": "raw-approval", "prompt": "inspect relay"},
    )
    push = client.post(
        "/relay/git/push-approved",
        headers=headers,
        json={"mission_id": "missing-mission", "approval_id": "raw-approval", "confirm": "I_APPROVE_GIT_PUSH"},
    )
    pull = client.post(
        "/relay/vps/pull-approved",
        headers=headers,
        json={"mission_id": "missing-mission", "approval_id": "raw-approval", "confirm": "I_APPROVE_VPS_PULL"},
    )

    for response in (codex, push, pull):
        payload = response.json()
        assert response.status_code == 200
        assert payload["execution_performed"] is False
        assert payload["approval_validated"] is False
        assert payload["reason"] == "MISSION_NOT_FOUND"

    assert codex.json()["status"] == "CODEX_BLOCKED"
    assert push.json()["status"] == "GIT_PUSH_BLOCKED"
    assert pull.json()["status"] == "VPS_PULL_BLOCKED"
