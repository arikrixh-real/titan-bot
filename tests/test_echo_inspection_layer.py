from titan_echo.echo_inspection_layer import (
    inspect_file,
    inspect_git,
    inspect_health,
    inspect_search,
    inspect_tree,
)
from titan_echo.echo_relay_api import app


def test_inspection_routes_are_registered():
    routes = {route.path for route in app.routes}

    assert "/relay/inspect/tree" in routes
    assert "/relay/inspect/file" in routes
    assert "/relay/inspect/runtime" in routes
    assert "/relay/inspect/health" in routes
    assert "/relay/inspect/git" in routes
    assert "/relay/inspect/search" in routes
    assert "/relay/inspect/connections" in routes


def test_tree_blocks_parent_traversal():
    payload = inspect_tree("../")

    assert payload["status"] == "BLOCKED"
    assert payload["reason"] == "parent_traversal_blocked"
    assert payload["read_performed"] is False
    assert payload["safety"]["traversal_blocked"] is True
    assert payload["audit"]["persistent_write_performed"] is False


def test_file_blocks_env_and_allows_safe_file():
    blocked = inspect_file(".env")
    allowed = inspect_file("README.md")

    assert blocked["status"] == "BLOCKED"
    assert blocked["reason"] == "sensitive_file_blocked"
    assert allowed["status"] == "OK"
    assert allowed["path"] == "README.md"
    assert allowed["safety"]["read_only"] is True


def test_search_redacts_sensitive_query_and_reports_audit():
    payload = inspect_search("token", "titan_echo", 5)

    assert payload["status"] == "OK"
    assert payload["query"] == "[REDACTED]"
    assert payload["audit"]["action"] == "search"
    assert payload["safety"]["secrets_redacted"] is True


def test_git_inspection_is_read_only():
    payload = inspect_git()

    assert payload["status"] == "OK"
    assert payload["safety"]["git_push_pull"] is False
    assert "git status --short" in payload["git_commands_executed"]
    assert "push" in payload["blocked_git_mutations"]


def test_health_inspection_has_no_mutation_flags():
    payload = inspect_health()

    assert payload["status"] == "OK"
    assert payload["safety"]["write_delete_edit_restart_deploy"] is False
    assert payload["audit"]["recorded_in_response"] is True
