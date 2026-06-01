"""Checker for ECHO's unified answer engine."""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from titan_echo.echo_answer_engine import ANSWER_PATH, SUMMARY_PATH, generate_answer


ENGINE_PATH = REPO_ROOT / "titan_echo" / "echo_answer_engine.py"
CHECKER_PATH = REPO_ROOT / "titan_echo" / "echo_answer_engine_check.py"
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"

REQUIRED_ANSWER_KEYS = {
    "short_answer",
    "proven_status",
    "failing_status",
    "stale_or_waiting_status",
    "unknown_status",
    "reasoning",
    "recommended_next_action",
    "what_not_to_do",
    "evidence_used",
    "confidence",
    "safety",
}
REQUIRED_SUMMARY_KEYS = {
    "short_answer",
    "recommended_next_action",
    "what_not_to_do",
    "confidence",
    "safety",
}
DANGEROUS_IMPORT_ROOTS = {"subprocess", "shlex", "pexpect", "socket", "socketserver", "requests"}
DANGEROUS_IMPORT_MODULES = {"http.server"}
DANGEROUS_CALL_ROOTS = {"subprocess", "pexpect", "socket", "socketserver", "requests"}
DANGEROUS_CALL_NAMES = {"Popen"}
DANGEROUS_CALL_ATTRS = {("os", "system")}
OVERCLAIM_TERMS = ("fully healthy", "guaranteed", "definitely fixed", "live trading ready", "safe to deploy")
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
SAFE_SECRET_WORDS = {
    "placeholder",
    "example",
    "redacted",
    "changeme",
    "dummy",
    "none",
    "null",
    "false",
    "true",
    "token",
    "secret",
    "password",
    "api_key",
    "private_key",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def inside_echo(path: Path) -> bool:
    resolved_echo = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    return resolved_echo in (resolved_path, *resolved_path.parents)


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
    return None


def dangerous_source_findings(paths: list[Path]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        text = read_text(path)
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            findings.append(f"{path.name}: syntax error while scanning source: {exc.msg}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    root = name.split(".", 1)[0]
                    if root in DANGEROUS_IMPORT_ROOTS or name in DANGEROUS_IMPORT_MODULES:
                        findings.append(f"{path.name}: dangerous import {name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                root = module.split(".", 1)[0]
                if root in DANGEROUS_IMPORT_ROOTS or module in DANGEROUS_IMPORT_MODULES:
                    findings.append(f"{path.name}: dangerous import from {module}")
                for alias in node.names:
                    imported = f"{module}.{alias.name}" if module else alias.name
                    imported_root = alias.name.split(".", 1)[0]
                    if imported_root in DANGEROUS_IMPORT_ROOTS or imported in DANGEROUS_IMPORT_MODULES:
                        findings.append(f"{path.name}: dangerous import {imported}")
            elif isinstance(node, ast.Call):
                call_name = dotted_name(node.func)
                if not call_name:
                    continue
                parts = call_name.split(".")
                if call_name in {f"{root}.system" for root, _ in DANGEROUS_CALL_ATTRS}:
                    findings.append(f"{path.name}: dangerous call {call_name}")
                elif len(parts) >= 2 and (parts[0], parts[1]) in DANGEROUS_CALL_ATTRS:
                    findings.append(f"{path.name}: dangerous call {call_name}")
                elif parts[0] in DANGEROUS_CALL_ROOTS:
                    findings.append(f"{path.name}: dangerous call {call_name}")
                elif parts[-1] in DANGEROUS_CALL_NAMES:
                    findings.append(f"{path.name}: dangerous call {call_name}")
    return sorted(set(findings))


def secret_like_findings(text: str) -> list[str]:
    findings: list[str] = []
    for match in SECRET_ASSIGNMENT_RE.finditer(text):
        value = match.group(2)
        if value.lower() not in SAFE_SECRET_WORDS:
            findings.append(match.group(1))
    for match in SECRET_VALUE_RE.finditer(text):
        findings.append(match.group(1)[:8] + "...")
    return sorted(set(findings))


def build_check() -> dict[str, Any]:
    generate_answer()
    answer = read_json(ANSWER_PATH)
    summary = read_json(SUMMARY_PATH)
    source = read_text(ENGINE_PATH) + "\n" + read_text(CHECKER_PATH)
    rendered = json.dumps(answer, sort_keys=True).lower()

    failures: list[str] = []
    if not ANSWER_PATH.exists() or not SUMMARY_PATH.exists():
        failures.append("answer outputs missing")
    if not answer or not summary:
        failures.append("answer outputs invalid JSON")

    missing_answer = sorted(REQUIRED_ANSWER_KEYS - set(answer))
    if missing_answer:
        failures.append("answer missing keys: " + ", ".join(missing_answer))
    missing_summary = sorted(REQUIRED_SUMMARY_KEYS - set(summary))
    if missing_summary:
        failures.append("summary missing keys: " + ", ".join(missing_summary))

    evidence_used = answer.get("evidence_used")
    if not isinstance(evidence_used, list) or not evidence_used:
        failures.append("evidence_used missing or empty")
    elif not all(isinstance(item, dict) and item.get("path") for item in evidence_used):
        failures.append("evidence_used entries must include paths")

    safety = answer.get("safety") if isinstance(answer.get("safety"), dict) else {}
    expected_false = {
        "shell_execution",
        "runtime_repair",
        "scanner_changed",
        "workers_changed",
        "master_brain_changed",
        "unified_brain_changed",
        "broker_risk_changed",
        "restart",
        "deploy",
        "push",
    }
    for key in sorted(expected_false):
        if safety.get(key) is not False:
            failures.append(f"safety.{key} must be false")
    if safety.get("read_only_answer_engine") is not True:
        failures.append("safety.read_only_answer_engine must be true")
    if safety.get("writes_only_echo_runtime") is not True:
        failures.append("safety.writes_only_echo_runtime must be true")

    if not inside_echo(ANSWER_PATH) or not inside_echo(SUMMARY_PATH):
        failures.append("outputs must stay under data/runtime/echo")

    dangerous_found = dangerous_source_findings([ENGINE_PATH, CHECKER_PATH])
    secrets_found = secret_like_findings(source + "\n" + json.dumps(answer, sort_keys=True))
    overclaims_found = [term for term in OVERCLAIM_TERMS if term in rendered]
    if dangerous_found:
        failures.append("dangerous shell/network executable source found")
    if secrets_found:
        failures.append("secret-like value found")
    if overclaims_found:
        failures.append("overclaiming language found")

    if answer.get("confidence") not in {"HIGH", "MEDIUM", "LOW"}:
        failures.append("confidence must be HIGH/MEDIUM/LOW")
    if not answer.get("short_answer"):
        failures.append("short_answer missing")
    if not answer.get("recommended_next_action"):
        failures.append("recommended_next_action missing")

    return {
        "schema": "titan.echo.answer_engine_check.v1",
        "status": "PASS" if not failures else "FAIL",
        "answer_exists": ANSWER_PATH.exists(),
        "summary_exists": SUMMARY_PATH.exists(),
        "json_valid": bool(answer) and bool(summary),
        "required_sections_present": not missing_answer and not missing_summary,
        "evidence_files_listed": isinstance(evidence_used, list) and bool(evidence_used),
        "no_shell_execution": not dangerous_found and safety.get("shell_execution") is False,
        "writes_only_echo_runtime": safety.get("writes_only_echo_runtime") is True and inside_echo(ANSWER_PATH) and inside_echo(SUMMARY_PATH),
        "secrets_found": secrets_found,
        "secrets_printed_or_embedded": bool(secrets_found),
        "overclaims_found": overclaims_found,
        "failures": failures,
        "short_answer": answer.get("short_answer"),
        "recommended_next_action": answer.get("recommended_next_action"),
        "what_not_to_do": answer.get("what_not_to_do"),
        "confidence": answer.get("confidence"),
    }


def main() -> None:
    result = build_check()
    print("ECHO answer engine check complete.")
    print(f"status={result['status']}")
    print(f"short_answer={result['short_answer']}")
    print(f"recommended_next_action={result['recommended_next_action']}")
    print("what_not_to_do=" + " | ".join(result.get("what_not_to_do") or []))
    print(f"confidence={result['confidence']}")
    print(f"json_valid={result['json_valid']}")
    print(f"required_sections_present={result['required_sections_present']}")
    print(f"evidence_files_listed={result['evidence_files_listed']}")
    print(f"no_shell_execution={result['no_shell_execution']}")
    print(f"writes_only_echo_runtime={result['writes_only_echo_runtime']}")
    print(f"secrets_printed_or_embedded={result['secrets_printed_or_embedded']}")
    print(f"secrets_found={result['secrets_found']}")
    print(f"overclaims_found={result['overclaims_found']}")
    if result["failures"]:
        print("failures=" + "; ".join(result["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
