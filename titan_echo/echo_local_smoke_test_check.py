"""Checker for the local-only ECHO fallback smoke test.

This checker validates the smoke-test artifacts and statically checks the
local smoke-test files for unsafe command/server/network behavior. It does not
start a server and does not write any files.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
SMOKE_PATH = REPO_ROOT / "titan_echo" / "echo_local_smoke_test.py"
CHECK_PATH = REPO_ROOT / "titan_echo" / "echo_local_smoke_test_check.py"
REPORT_PATH = ECHO_DIR / "echo_local_smoke_test.json"
SUMMARY_PATH = ECHO_DIR / "echo_local_smoke_test_summary.json"

SOURCE_FILES = (SMOKE_PATH, CHECK_PATH)
EXPECTED_WRITES = {
    "data/runtime/echo/echo_local_smoke_test.json",
    "data/runtime/echo/echo_local_smoke_test_summary.json",
}
EXPECTED_TESTS = {
    "get_health",
    "get_status",
    "get_answer",
    "get_query_status",
    "get_query_runtime",
    "get_query_scanner",
    "get_query_workers",
    "get_query_unified_brain",
    "get_query_what_next",
    "get_query_what_not_to_do",
    "get_query_unknown_test",
}

DANGEROUS_IMPORT_ROOTS = {
    "http",
    "os",
    "requests",
    "shlex",
    "socket",
    "subprocess",
    "urllib",
    "uvicorn",
}
DANGEROUS_CALL_ROOTS = {
    "os.system",
    "os.popen",
    "subprocess",
    "shlex",
    "socket",
    "requests",
    "urllib",
    "uvicorn",
}
SERVER_CALL_NAMES = {"run", "serve", "listen", "bind", "start_server"}
POST_LIKE_NAMES = {"post", "put", "patch", "delete"}
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
SAFE_SECRET_WORDS = {"changeme", "dummy", "example", "none", "null", "placeholder", "redacted"}


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
                if leaf in SERVER_CALL_NAMES and not call_name.startswith("ast."):
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
            if value.lower() not in SAFE_SECRET_WORDS:
                findings.append(match.group(1))
        for match in SECRET_VALUE_RE.finditer(text):
            findings.append(match.group(1)[:8] + "...")
    return sorted(set(findings))


def writes_only_to_echo(report: dict[str, Any]) -> bool:
    writes = report.get("safety", {}).get("writes_only")
    if not isinstance(writes, list):
        return False
    return set(writes) == EXPECTED_WRITES and all(str(item).startswith("data/runtime/echo/") for item in writes)


def build_check() -> dict[str, Any]:
    failures: list[str] = []
    if not REPORT_PATH.exists():
        failures.append(f"missing {relative(REPORT_PATH)}")
    if not SUMMARY_PATH.exists():
        failures.append(f"missing {relative(SUMMARY_PATH)}")
    report = read_json(REPORT_PATH) if REPORT_PATH.exists() else {}
    summary = read_json(SUMMARY_PATH) if SUMMARY_PATH.exists() else {}

    tests = report.get("tests", [])
    test_names = {test.get("name") for test in tests if isinstance(test, dict)}
    failed_tests = [test.get("name") for test in tests if isinstance(test, dict) and not test.get("passed")]
    scan = source_scan(SOURCE_FILES)
    secrets = secret_like_findings(SOURCE_FILES, (report, summary))

    if report.get("tests_failed") != 0:
        failures.append("smoke report has failed tests")
    if report.get("tests_passed") != len(EXPECTED_TESTS):
        failures.append("smoke report passed-test count mismatch")
    if test_names != EXPECTED_TESTS:
        failures.append("smoke report test set mismatch")
    if failed_tests:
        failures.append("one or more smoke test entries failed")
    if summary.get("tests_failed") != 0:
        failures.append("summary has failed tests")
    if summary.get("safety_result") != "PASS" or report.get("safety_result") != "PASS":
        failures.append("safety_result is not PASS")
    if report.get("local_only") is not True:
        failures.append("local_only flag is not true")
    if report.get("server_started") is not False:
        failures.append("server_started flag is not false")
    safety = report.get("safety", {})
    expected_false_flags = (
        "command_execution",
        "codex_execution",
        "shell_execution",
        "server_started",
        "uvicorn_started",
        "fastapi_install",
        "deploy",
        "push",
        "restart",
        "public_exposure",
        "broker_risk_scanner_changes",
        "master_unified_brain_changes",
    )
    for flag in expected_false_flags:
        if safety.get(flag) is not False:
            failures.append(f"safety flag {flag} is not false")
    if safety.get("read_only") is not True:
        failures.append("read_only safety flag is not true")
    if not writes_only_to_echo(report):
        failures.append("writes_only is not limited to requested data/runtime/echo artifacts")
    for key, values in scan.items():
        if values:
            failures.append(f"{key} found")
    if secrets:
        failures.append("secret-like value found")

    return {
        "schema": "titan.echo.local_smoke_test_check.v1",
        "checked_files": [relative(path) for path in SOURCE_FILES],
        "checked_artifacts": [relative(REPORT_PATH), relative(SUMMARY_PATH)],
        "tests_passed": report.get("tests_passed", 0),
        "tests_failed": report.get("tests_failed", 0),
        "failed_test_names": failed_tests,
        "sample_get_answer_output": summary.get("sample_get_answer_output"),
        "sample_get_query_what_next_output": summary.get("sample_get_query_what_next_output"),
        "source_scan": scan,
        "secret_like_findings": secrets,
        "writes_only_to_data_runtime_echo": writes_only_to_echo(report),
        "safety_result": "PASS" if not failures else "FAIL",
        "failures": failures,
        "next_recommended_step": summary.get(
            "next_recommended_step",
            "Keep ECHO local; review FastAPI dependency readiness before any server smoke test.",
        ),
    }


def main() -> None:
    check = build_check()
    print("ECHO local smoke test check complete.")
    print(f"tests_passed={check['tests_passed']}")
    print(f"tests_failed={check['tests_failed']}")
    print(f"sample_get_answer_output={json.dumps(check['sample_get_answer_output'], sort_keys=True)}")
    print(f"sample_get_query_what_next_output={json.dumps(check['sample_get_query_what_next_output'], sort_keys=True)}")
    print(f"safety_result={check['safety_result']}")
    print(f"next_recommended_step={check['next_recommended_step']}")
    if check["failures"]:
        print("failures=" + "; ".join(check["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
