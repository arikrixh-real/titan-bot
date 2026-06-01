"""Checker for the ECHO FastAPI local GET smoke test."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
SMOKE_SOURCE = REPO_ROOT / "titan_echo" / "echo_fastapi_local_smoke_test.py"
CHECK_SOURCE = REPO_ROOT / "titan_echo" / "echo_fastapi_local_smoke_check.py"
REPORT_PATH = ECHO_DIR / "echo_fastapi_local_smoke_test.json"
SUMMARY_PATH = ECHO_DIR / "echo_fastapi_local_smoke_summary.json"

SOURCE_FILES = (SMOKE_SOURCE, CHECK_SOURCE)
EXPECTED_WRITES = {
    "data/runtime/echo/echo_fastapi_local_smoke_test.json",
    "data/runtime/echo/echo_fastapi_local_smoke_summary.json",
}
EXPECTED_TEST_NAMES = {
    "GET /health",
    "GET /status",
    "GET /answer",
    "GET /query?intent=status",
    "GET /query?intent=unified_brain",
    "GET /query?intent=what_next",
    "GET /query?intent=unknown_test",
}
SECRET_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    \b(api[_-]?key|token|secret|password|private[_-]?key)\b
    \s*[:=]\s*
    ['\"]([^'\"\s]{16,})['\"]
    """
)
SECRET_VALUE_RE = re.compile(
    r"""(?x)
    \b(
        sk-[A-Za-z0-9_-]{20,}
        |ghp_[A-Za-z0-9_]{20,}
        |github_pat_[A-Za-z0-9_]{20,}
        |xox[baprs]-[A-Za-z0-9-]{20,}
        |AKIA[0-9A-Z]{16}
    )\b
    """
)
SAFE_SECRET_VALUES = {"changeme", "dummy", "example", "none", "null", "placeholder", "redacted"}
DANGEROUS_IMPORT_ROOTS = {"os", "requests", "shlex", "socket", "subprocess", "urllib", "uvicorn"}
DANGEROUS_CALL_ROOTS = {
    "os.system",
    "os.popen",
    "requests",
    "shlex",
    "socket",
    "subprocess",
    "urllib",
    "uvicorn",
}
SERVER_CALL_NAMES = {"bind", "listen", "serve", "start_server"}
POST_LIKE_NAMES = {"delete", "patch", "post", "put"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
    return None


def source_scan(paths: tuple[Path, ...]) -> dict[str, list[str]]:
    findings = {
        "dangerous_imports": [],
        "dangerous_calls": [],
        "server_start_calls": [],
        "post_or_mutation_calls": [],
        "syntax_errors": [],
    }
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            findings["syntax_errors"].append(f"{relative(path)}: {exc.msg}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in DANGEROUS_IMPORT_ROOTS:
                        findings["dangerous_imports"].append(f"{relative(path)}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                root = module.split(".", 1)[0]
                if root in DANGEROUS_IMPORT_ROOTS:
                    findings["dangerous_imports"].append(f"{relative(path)}: from {module} import ...")
            elif isinstance(node, ast.Call):
                call_name = dotted_name(node.func)
                if not call_name:
                    continue
                if any(call_name == root or call_name.startswith(root + ".") for root in DANGEROUS_CALL_ROOTS):
                    findings["dangerous_calls"].append(f"{relative(path)}: {call_name}")
                leaf = call_name.rsplit(".", 1)[-1].lower()
                if leaf in SERVER_CALL_NAMES:
                    findings["server_start_calls"].append(f"{relative(path)}: {call_name}")
                if leaf in POST_LIKE_NAMES:
                    findings["post_or_mutation_calls"].append(f"{relative(path)}: {call_name}")
    return {key: sorted(set(value)) for key, value in findings.items()}


def secret_like_findings(paths: tuple[Path, ...], payloads: tuple[Any, ...]) -> list[str]:
    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore") for path in paths if path.exists()
    )
    payload_text = json.dumps(payloads, sort_keys=True)
    findings: list[str] = []
    for text in (source_text, payload_text):
        for match in SECRET_ASSIGNMENT_RE.finditer(text):
            value = match.group(2)
            if value.lower() not in SAFE_SECRET_VALUES:
                findings.append(match.group(1))
        for match in SECRET_VALUE_RE.finditer(text):
            findings.append(match.group(1)[:8] + "...")
    return sorted(set(findings))


def writes_only_to_echo(report: dict[str, Any]) -> bool:
    writes = report.get("safety", {}).get("writes_only")
    if not isinstance(writes, list):
        return False
    return set(writes) == EXPECTED_WRITES and all(str(item).startswith("data/runtime/echo/") for item in writes)


def no_post_routes(report: dict[str, Any]) -> bool:
    route_methods = report.get("route_methods")
    if not isinstance(route_methods, dict):
        return False
    return all(
        isinstance(methods, list) and all(method == "GET" for method in methods)
        for methods in route_methods.values()
    )


def build_check() -> dict[str, Any]:
    failures: list[str] = []
    if not REPORT_PATH.exists():
        failures.append(f"missing {relative(REPORT_PATH)}")
    if not SUMMARY_PATH.exists():
        failures.append(f"missing {relative(SUMMARY_PATH)}")
    report = read_json(REPORT_PATH) if REPORT_PATH.exists() else {}
    summary = read_json(SUMMARY_PATH) if SUMMARY_PATH.exists() else {}
    scan = source_scan(SOURCE_FILES)
    secrets = secret_like_findings(SOURCE_FILES, (report, summary))

    tests = report.get("tests", [])
    test_names = {test.get("name") for test in tests if isinstance(test, dict)}
    failed_tests = [test.get("name") for test in tests if isinstance(test, dict) and not test.get("passed")]
    safety = report.get("safety", {})

    if report.get("schema") != "titan.echo.fastapi_local_smoke_test.v1":
        failures.append("invalid smoke report schema")
    if summary.get("schema") != "titan.echo.fastapi_local_smoke_summary.v1":
        failures.append("invalid summary schema")
    if report.get("fastapi_available") is not True:
        failures.append("FastAPI is not available")
    if report.get("app_exists") is not True:
        failures.append("FastAPI app does not exist")
    if report.get("transport") != "fastapi_testclient_in_process":
        failures.append("transport is not TestClient in-process")
    if report.get("base_url") != "http://127.0.0.1":
        failures.append("base_url is not 127.0.0.1")
    if report.get("bind_host") != "127.0.0.1":
        failures.append("bind host is not 127.0.0.1")
    if report.get("server_started") is not False:
        failures.append("report indicates a server started")
    if report.get("uvicorn_used") is not False:
        failures.append("report indicates uvicorn was used")
    if report.get("tests_failed") != 0:
        failures.append("one or more GET tests failed")
    if report.get("tests_passed") != len(EXPECTED_TEST_NAMES):
        failures.append("passed-test count mismatch")
    if test_names != EXPECTED_TEST_NAMES:
        failures.append("GET test set mismatch")
    if failed_tests:
        failures.append("failed GET test entries found")
    if not no_post_routes(report):
        failures.append("non-GET route found")
    if report.get("non_get_routes"):
        failures.append("non_get_routes is not empty")
    expected_safety = {
        "localhost_only": True,
        "bind_only": "127.0.0.1",
        "public_exposure": False,
        "post_endpoints": False,
        "command_endpoints": False,
        "command_execution": False,
        "shell_execution": False,
        "uvicorn_used": False,
        "server_started": False,
        "deploy": False,
        "push": False,
        "restart": False,
        "scanner_master_unified_broker_risk_changes": False,
        "secrets_exposed": False,
    }
    for key, expected in expected_safety.items():
        if safety.get(key) != expected:
            failures.append(f"safety flag {key} mismatch")
    if not writes_only_to_echo(report):
        failures.append("writes are not limited to requested data/runtime/echo outputs")
    for key, values in scan.items():
        if values:
            failures.append(f"{key} found")
    if secrets:
        failures.append("secret-like value found")
    if report.get("safety_result") != "PASS" or summary.get("safety_result") != "PASS":
        failures.append("safety_result is not PASS")

    return {
        "schema": "titan.echo.fastapi_local_smoke_check.v1",
        "checked_files": [relative(path) for path in SOURCE_FILES],
        "checked_artifacts": [relative(REPORT_PATH), relative(SUMMARY_PATH)],
        "tests_passed": report.get("tests_passed", 0),
        "tests_failed": report.get("tests_failed", 0),
        "failed_test_names": failed_tests,
        "sample_answer_response": summary.get("sample_answer_response"),
        "sample_query_what_next_response": summary.get("sample_query_what_next_response"),
        "source_scan": scan,
        "secret_like_findings": secrets,
        "writes_only_to_data_runtime_echo": writes_only_to_echo(report),
        "safety_result": "PASS" if not failures else "FAIL",
        "failures": failures,
    }


def main() -> None:
    check = build_check()
    print("ECHO FastAPI local smoke check complete.")
    print(f"tests_passed={check['tests_passed']}")
    print(f"tests_failed={check['tests_failed']}")
    print(f"sample_answer_response={json.dumps(check['sample_answer_response'], sort_keys=True)}")
    print(f"sample_query_what_next_response={json.dumps(check['sample_query_what_next_response'], sort_keys=True)}")
    print(f"safety_result={check['safety_result']}")
    if check["failures"]:
        print("failures=" + "; ".join(check["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
