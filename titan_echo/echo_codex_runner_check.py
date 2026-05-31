"""Import-only checker for the disabled Codex runner skeleton."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from titan_echo import echo_codex_runner


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    REPO_ROOT / "titan_echo" / "echo_codex_runner.py",
    REPO_ROOT / "titan_echo" / "echo_codex_runner_check.py",
)
DANGEROUS_IMPORTS = {"subprocess", "shlex", "pexpect"}
DANGEROUS_CALLS = {"os.system", "os.popen", "subprocess.run", "subprocess.Popen"}


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
    return None


def _source_findings() -> list[str]:
    findings: list[str] = []
    for path in SOURCE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".", 1)[0] in DANGEROUS_IMPORTS:
                        findings.append(f"{path.name}: dangerous import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.split(".", 1)[0] in DANGEROUS_IMPORTS:
                    findings.append(f"{path.name}: dangerous import from {module}")
            elif isinstance(node, ast.Call):
                call_name = _dotted_name(node.func)
                if call_name in DANGEROUS_CALLS:
                    findings.append(f"{path.name}: dangerous call {call_name}")
    return sorted(set(findings))


def build_check() -> dict[str, Any]:
    status = echo_codex_runner.build_codex_runner_status()
    policy = echo_codex_runner.build_codex_runner_policy()
    findings = _source_findings()
    failures = []
    if status.get("status") != "CODEX_RUNNER_DISABLED":
        failures.append("runner status is not disabled")
    if policy.get("current_action") != "RECORD_ONLY":
        failures.append("policy is not record-only")
    if policy.get("codex_execution") is not False:
        failures.append("codex execution is not false")
    if findings:
        failures.append("dangerous source token found")
    return {
        "schema": "titan.echo.codex_runner_check.v1",
        "status": "PASS" if not failures else "FAIL",
        "runner_status": status,
        "runner_policy": policy,
        "source_findings": findings,
        "failures": failures,
    }


if __name__ == "__main__":
    report = build_check()
    print("ECHO Codex runner check complete.")
    print(f"status={report['status']}")
    print(f"runner_status={report['runner_status']['status']}")
    print(f"current_action={report['runner_policy']['current_action']}")
    if report["failures"]:
        print("failures=" + "; ".join(report["failures"]))
        raise SystemExit(1)
