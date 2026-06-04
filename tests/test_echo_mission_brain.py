import json

from titan_echo.echo_mission_brain import (
    approve_step,
    create_mission,
    load_mission,
    mission_status,
    resume_mission,
    rollback_status,
)


def _approve_current(payload):
    state = load_mission(payload["mission_id"])
    step = state["current_step"]
    approval_id = state["approvals"][step]["approval_id"]
    return approve_step({"mission_id": payload["mission_id"], "step": step, "approval_id": approval_id})


def test_create_mission_persists_and_waits_for_codex_approval():
    payload = create_mission({"title": "pytest echo mission brain", "objective": "prove waiting approval"})

    assert payload["status"] == "APPROVAL_WAITING"
    assert payload["phase"] == "APPROVAL_WAITING"
    assert payload["current_step"] == "codex"
    assert payload["blocked_reason"] == "APPROVAL_REQUIRED_CODEX"
    assert payload["approvals_remaining"]

    state = load_mission(payload["mission_id"])
    assert state["continuity"]["survives_api_restart"] is True
    assert state["continuity"]["survives_pc_off_then_resume"] is True


def test_resume_blocks_codex_without_approval_from_persisted_state():
    payload = create_mission({"title": "pytest blocked codex", "objective": "prove codex approval gate"})

    blocked = resume_mission({"mission_id": payload["mission_id"]})
    restored = mission_status(payload["mission_id"])

    assert blocked["status"] == "BLOCKED_APPROVAL_REQUIRED"
    assert blocked["phase"] == "APPROVAL_WAITING"
    assert blocked["blocked_reason"] == "APPROVAL_REQUIRED_CODEX"
    assert restored["mission_id"] == payload["mission_id"]
    assert restored["current_step"] == "codex"


def test_approved_resume_advances_through_compact_report_state():
    payload = create_mission({"title": "pytest final report", "objective": "prove complete compact state"})

    for _ in range(7):
        _approve_current(payload)
        result = resume_mission({"mission_id": payload["mission_id"]})

    assert result["status"] == "COMPLETE"
    assert result["phase"] == "COMPLETE"
    assert result["progress_percent"] == 100
    assert result["latest_evidence"]["step"] == "report"
    assert result["safety"]["git_push_pull"] is False
    assert result["safety"]["automatic_reset_revert"] is False

    state = load_mission(payload["mission_id"])
    report_path = state["latest_evidence"]["evidence_path"]
    with open(report_path, "r", encoding="utf-8") as handle:
        report = json.load(handle)
    assert report["report"]["rollback_available"] is True


def test_rollback_status_exists_and_is_approval_gated():
    payload = create_mission({"title": "pytest rollback status", "objective": "prove rollback status"})

    status = rollback_status(payload["mission_id"])

    assert status["status"] == "ROLLBACK_STATUS_PRESENT"
    assert status["mission_id"] == payload["mission_id"]
    assert status["blocked_reason"] == "ROLLBACK_REQUIRES_EXPLICIT_APPROVAL"
    assert status["safety"]["automatic_reset_revert"] is False
