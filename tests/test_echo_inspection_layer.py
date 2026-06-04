from titan_echo.echo_inspection_layer import (
    inspect_file,
    inspect_git,
    inspect_health,
    inspect_json_path,
    inspect_search,
    inspect_tree,
)
from titan_echo.echo_relay_api import app


def test_inspection_routes_are_registered():
    routes = {route.path for route in app.routes}

    assert "/relay/inspect/tree" in routes
    assert "/relay/inspect/file" in routes
    assert "/relay/inspect/json-path" in routes
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


def test_json_path_reads_valid_nested_path_compactly():
    payload = inspect_json_path(
        "tests/fixtures/inspection_sample.json",
        "authoritative_runtime_health.stale_artifacts",
    )

    assert payload["status"] == "OK"
    assert payload["path"] == "tests/fixtures/inspection_sample.json"
    assert payload["json_path"] == "authoritative_runtime_health.stale_artifacts"
    assert payload["found"] is True
    assert payload["value"] == 3
    assert payload["value_type"] == "int"
    assert payload["audit"]["persistent_write_performed"] is False


def test_json_path_missing_path_reports_not_found():
    payload = inspect_json_path(
        "tests/fixtures/inspection_sample.json",
        "authoritative_runtime_health.missing",
    )

    assert payload["status"] == "OK"
    assert payload["found"] is False
    assert payload["value"] is None
    assert payload["value_type"] == "missing"


def test_json_path_blocks_traversal():
    payload = inspect_json_path("../outside.json", "anything")

    assert payload["status"] == "BLOCKED"
    assert payload["found"] is False
    assert payload["safety"]["traversal_blocked"] is True
    assert payload["audit"]["persistent_write_performed"] is False


def test_json_path_blocks_sensitive_file():
    payload = inspect_json_path(".env", "anything")

    assert payload["status"] == "BLOCKED"
    assert payload["found"] is False
    assert payload["value"] is None
    assert payload["safety"]["secrets_redacted"] is True


def test_json_path_oversized_value_is_compacted():
    payload = inspect_json_path("tests/fixtures/inspection_sample.json", "large_value")

    assert payload["status"] == "OK"
    assert payload["found"] is True
    assert payload["value_type"] == "str"
    assert payload["value"]["truncated"] is True
    assert len(payload["value"]["preview"]) == 300
