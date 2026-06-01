"""Safety checker for ECHO Mission Center aggregation."""

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

from titan_echo.echo_api_status import CONTRACT_PATH
from titan_echo.echo_mission_center import (
    ECHO_DIR,
    MISSION_CENTER_PATH,
    MISSION_CENTER_SUMMARY_PATH,
    generate_mission_center,
)


SOURCE_FILES = [
    REPO_ROOT / "titan_echo" / "echo_api.py",
    REPO_ROOT / "titan_echo" / "echo_api_status.py",
    REPO_ROOT / "titan_echo" / "echo_api_check.py",
    REPO_ROOT / "titan_echo" / "echo_mission_center.py",
    REPO_ROOT / "titan_echo" / "echo_mission_center_check.py",
]
REQUIRED_KEYS = {
    "current_human_answer",
    "titan_status",
    "proven_healthy",
    "failing_or_stale",
    "waiting_for_runtime_data",
    "alerts_count",
    "next_recommended_action",
    "what_not_to_do",
    "evidence_used",
    "confidence",
}
DANGEROUS_IMPORT_ROOTS = {"subprocess", "shlex", "pexpect", "socket", "socketserver", "requests"}
DANGEROUS_IMPORT_MODULES = {"http.server"}
DANGEROUS_CALL_ROOTS = {"subprocess", "pexpect", "socket", "socketserver", "requests"}
DANGEROUS_CALL_NAMES = {"Popen"}
DANGEROUS_CALL_ATTRS = {("os", "system")}
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
SAFE_SECRET_WORDS = {"placeholder", "example", "redacted", "changeme", "dummy", "none", "null"}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


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
        try:
            tree = ast.parse(read_text(path), filename=str(path))
        except SyntaxError as exc:
            findings.append(f"{path.name}: syntax error while scanning source: {exc.msg}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in DANGEROUS_IMPORT_ROOTS or alias.name in DANGEROUS_IMPORT_MODULES:
                        findings.append(f"{path.name}: dangerous import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                root = module.split(".", 1)[0]
                if root in DANGEROUS_IMPORT_ROOTS or module in DANGEROUS_IMPORT_MODULES:
                    findings.append(f"{path.name}: dangerous import from {module}")
            elif isinstance(node, ast.Call):
                call_name = dotted_name(node.func)
                if not call_name:
                    continue
                parts = call_name.split(".")
                if len(parts) >= 2 and (parts[0], parts[1]) in DANGEROUS_CALL_ATTRS:
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


def inside_echo(path: Path) -> bool:
    resolved_echo = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    return resolved_echo in (resolved_path, *resolved_path.parents)


def build_check() -> dict[str, Any]:
    mission_center, summary = generate_mission_center()
    mission_file = read_json(MISSION_CENTER_PATH)
    summary_file = read_json(MISSION_CENTER_SUMMARY_PATH)
    contract = read_json(CONTRACT_PATH)
    endpoint_paths = {
        endpoint.get("path")
        for endpoint in contract.get("endpoints", [])
        if isinstance(endpoint, dict)
    }
    source = "\n".join(read_text(path) for path in SOURCE_FILES)
    dangerous_found = dangerous_source_findings(SOURCE_FILES)
    secrets_found = secret_like_findings(source)
    missing_keys = sorted(REQUIRED_KEYS - set(mission_center))
    evidence_used = mission_center.get("evidence_used")
    failures: list[str] = []

    if not mission_file or not summary_file:
        failures.append("mission center outputs missing or invalid")
    if "/answer" not in endpoint_paths:
        failures.append("/answer missing from API contract")
    if missing_keys:
        failures.append("mission center missing keys: " + ", ".join(missing_keys))
    if not isinstance(evidence_used, list) or not evidence_used:
        failures.append("mission center evidence_used missing or empty")
    if mission_center.get("truth_rule") != "ChatGPT memory is context only. TITAN runtime/report files are proof.":
        failures.append("truth rule missing")
    if not mission_center.get("current_human_answer") or mission_center.get("current_human_answer") == "UNKNOWN":
        failures.append("current human answer missing")
    if mission_center.get("safety", {}).get("runtime_behavior_changed") is not False:
        failures.append("runtime behavior change flag must be false")
    if mission_center.get("safety", {}).get("writes_only_echo_runtime") is not True:
        failures.append("write boundary flag must be true")
    if not inside_echo(MISSION_CENTER_PATH) or not inside_echo(MISSION_CENTER_SUMMARY_PATH):
        failures.append("mission center writes must stay under data/runtime/echo")
    if dangerous_found:
        failures.append("dangerous shell/network executable source found")
    if secrets_found:
        failures.append("secret-like value found")

    return {
        "schema": "titan.echo.mission_center_check.v1",
        "status": "PASS" if not failures else "FAIL",
        "answer_contract_exists": "/answer" in endpoint_paths,
        "mission_center_exists": bool(mission_file),
        "mission_center_summary_exists": bool(summary_file),
        "answer_is_evidence_based": isinstance(evidence_used, list) and bool(evidence_used),
        "no_dangerous_imports_or_calls": not dangerous_found,
        "secrets_printed_or_embedded": bool(secrets_found),
        "writes_only_echo_runtime": inside_echo(MISSION_CENTER_PATH) and inside_echo(MISSION_CENTER_SUMMARY_PATH),
        "current_human_answer": mission_center.get("current_human_answer"),
        "titan_status": mission_center.get("titan_status"),
        "next_recommended_action": mission_center.get("next_recommended_action"),
        "what_not_to_do": mission_center.get("what_not_to_do"),
        "confidence": mission_center.get("confidence"),
        "safety": mission_center.get("safety", {}),
        "failures": failures,
    }


def main() -> None:
    report = build_check()
    print("ECHO Mission Center check complete.")
    print(f"status={report['status']}")
    print(f"answer_contract_exists={report['answer_contract_exists']}")
    print(f"mission_center_exists={report['mission_center_exists']}")
    print(f"mission_center_summary_exists={report['mission_center_summary_exists']}")
    print(f"answer_is_evidence_based={report['answer_is_evidence_based']}")
    print(f"no_dangerous_imports_or_calls={report['no_dangerous_imports_or_calls']}")
    print(f"secrets_printed_or_embedded={report['secrets_printed_or_embedded']}")
    print(f"writes_only_echo_runtime={report['writes_only_echo_runtime']}")
    print(f"current_human_answer={report['current_human_answer']}")
    print(f"titan_status={report['titan_status']}")
    print(f"next_recommended_action={report['next_recommended_action']}")
    print("what_not_to_do=" + " | ".join(report.get("what_not_to_do") or []))
    print(f"confidence={report['confidence']}")
    print(f"safety_result={'PASS' if report['status'] == 'PASS' else 'FAIL'}")
    if report["failures"]:
        print("failures=" + "; ".join(report["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
