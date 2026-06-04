from titan_echo.echo_relay_api import (
    relay_post_action_status,
    relay_verify_run_approved_status,
)


def test_verify_status_fallback_is_read_only_and_compact():
    payload = relay_verify_run_approved_status("approval-123")

    assert payload["status"] == "ACTION_STATUS_PRESENT"
    assert payload["action"] == "verify_run_approved"
    assert payload["accepted"] is False
    assert payload["blocked"] is False
    assert payload["approval_required"] is True
    assert payload["approval_id"] == "approval-123"
    assert payload["evidence_summary"]["status"] == "VERIFY_POST_BACKEND_AVAILABLE"
    assert payload["safety"]["read_only_get_fallback"] is True
    assert payload["safety"]["git_push_pull"] is False
    assert payload["safety"]["deploy_or_restart"] is False


def test_aggregate_action_status_does_not_execute():
    payload = relay_post_action_status("all", "approval-123")

    assert payload["status"] == "ACTION_STATUS_PRESENT"
    assert payload["action"] == "all"
    assert payload["approval_required"] is True
    assert payload["approval_id"] == "approval-123"
    assert set(payload["evidence_summary"]) == {"verify", "codex", "git_push", "vps_pull"}
    assert payload["safety"]["git_push_pull"] is False
    assert payload["safety"]["deploy_or_restart"] is False
