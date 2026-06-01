"""Safety checker for ECHO Query Router."""

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

from titan_echo.echo_api_status import CONTRACT_PATH, generate_reports
from titan_echo.echo_query_router import (
    ECHO_DIR,
    QUERY_ROUTER_PATH,
    QUERY_ROUTER_SUMMARY_PATH,
    SUPPORTED_INTENTS,
    generate_query_router,
)


REQUIRED_INTENTS = {
    "status",
    "runtime",
    "scanner",
    "workers",
    "master_brain",
    "unified_brain",
    "outcome_tracking",
    "lineage",
    "alerts",
    "missions",
    "what_next",
    "what_not_to_do",
    "unknown",
}
REQUIRED_RESPONSE_KEYS = {
    "intent",
    "short_answer",
    "evidence_used",
    "proven_facts",
    "unknowns_or_waiting",
    "recommended_next_action",
    "what_not_to_do",
    "confidence",
}
SOURCE_FILES = [
    REPO_ROOT / "titan_echo" / "echo_query_router.py",
    REPO_ROOT / "titan_echo" / "echo_query_router_check.py",
    REPO_ROOT / "titan_echo" / "echo_api.py",
    REPO_ROOT / "titan_echo" / "echo_api_status.py",
    REPO_ROOT / "titan_echo" / "echo_api_check.py",
]
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
    report, summary = generate_query_router()
    generate_reports()
    router_file = read_json(QUERY_ROUTER_PATH)
    summary_file = read_json(QUERY_ROUTER_SUMMARY_PATH)
    contract = read_json(CONTRACT_PATH)
    endpoint_paths = {
        endpoint.get("path")
        for endpoint in contract.get("endpoints", [])
        if isinstance(endpoint, dict)
    }
    answer_intent_documented = any(
        isinstance(endpoint, dict)
        and endpoint.get("path") == "/answer"
        and "intent" in json.dumps(endpoint, sort_keys=True).lower()
        for endpoint in contract.get("endpoints", [])
    )
    supported = set(report.get("supported_intents", []))
    responses = report.get("responses", {})
    dangerous_found = dangerous_source_findings(SOURCE_FILES)
    secrets_found = secret_like_findings("\n".join(read_text(path) for path in SOURCE_FILES))
    failures: list[str] = []

    if not router_file or not summary_file:
        failures.append("query router outputs missing or invalid")
    if REQUIRED_INTENTS - supported:
        failures.append("required intents missing: " + ", ".join(sorted(REQUIRED_INTENTS - supported)))
    if set(SUPPORTED_INTENTS) != supported:
        failures.append("SUPPORTED_INTENTS does not match generated report")
    if "/query" not in endpoint_paths and not answer_intent_documented:
        failures.append("/query or /answer intent contract missing")
    if not isinstance(responses, dict):
        failures.append("responses must be a dictionary")
    else:
        for intent in sorted(REQUIRED_INTENTS):
            response = responses.get(intent)
            if not isinstance(response, dict):
                failures.append(f"{intent} response missing")
                continue
            missing = REQUIRED_RESPONSE_KEYS - set(response)
            if missing:
                failures.append(f"{intent} response missing keys: " + ", ".join(sorted(missing)))
            evidence_used = response.get("evidence_used")
            if not isinstance(evidence_used, list) or not evidence_used:
                failures.append(f"{intent} response is not evidence-based")
    unknown_sample = report.get("unknown_intent_sample")
    if not isinstance(unknown_sample, dict) or unknown_sample.get("intent") != "unknown":
        failures.append("unknown intent not handled safely")
    if report.get("truth_rule") != "ChatGPT memory is context only. TITAN runtime/report files are proof.":
        failures.append("truth rule missing")
    if report.get("safety", {}).get("runtime_behavior_changed") is not False:
        failures.append("runtime behavior change flag must be false")
    if report.get("safety", {}).get("writes_only_echo_runtime") is not True:
        failures.append("write boundary flag must be true")
    if not inside_echo(QUERY_ROUTER_PATH) or not inside_echo(QUERY_ROUTER_SUMMARY_PATH):
        failures.append("query router writes must stay under data/runtime/echo")
    if dangerous_found:
        failures.append("dangerous shell/network executable source found")
    if secrets_found:
        failures.append("secret-like value found")

    return {
        "schema": "titan.echo.query_router_check.v1",
        "status": "PASS" if not failures else "FAIL",
        "supported_intents": report.get("supported_intents", []),
        "all_required_intents_present": not (REQUIRED_INTENTS - supported),
        "query_contract_exists": "/query" in endpoint_paths or answer_intent_documented,
        "answers_are_evidence_based": not any(
            isinstance(response, dict) and not response.get("evidence_used")
            for response in responses.values()
        )
        if isinstance(responses, dict)
        else False,
        "unknown_intent_handled": isinstance(unknown_sample, dict) and unknown_sample.get("intent") == "unknown",
        "no_dangerous_imports_or_calls": not dangerous_found,
        "secrets_printed_or_embedded": bool(secrets_found),
        "writes_only_echo_runtime": inside_echo(QUERY_ROUTER_PATH) and inside_echo(QUERY_ROUTER_SUMMARY_PATH),
        "sample_status_answer": summary.get("sample_status_answer", {}).get("short_answer") if isinstance(summary.get("sample_status_answer"), dict) else None,
        "sample_unified_brain_answer": summary.get("sample_unified_brain_answer", {}).get("short_answer") if isinstance(summary.get("sample_unified_brain_answer"), dict) else None,
        "sample_what_next_answer": summary.get("sample_what_next_answer", {}).get("short_answer") if isinstance(summary.get("sample_what_next_answer"), dict) else None,
        "unknown_intent_answer": summary.get("unknown_intent_answer", {}).get("short_answer") if isinstance(summary.get("unknown_intent_answer"), dict) else None,
        "failures": failures,
    }


def main() -> None:
    report = build_check()
    print("ECHO Query Router check complete.")
    print(f"status={report['status']}")
    print("supported_intents=" + ", ".join(report.get("supported_intents") or []))
    print(f"query_contract_exists={report['query_contract_exists']}")
    print(f"all_required_intents_present={report['all_required_intents_present']}")
    print(f"answers_are_evidence_based={report['answers_are_evidence_based']}")
    print(f"unknown_intent_handled={report['unknown_intent_handled']}")
    print(f"no_dangerous_imports_or_calls={report['no_dangerous_imports_or_calls']}")
    print(f"secrets_printed_or_embedded={report['secrets_printed_or_embedded']}")
    print(f"writes_only_echo_runtime={report['writes_only_echo_runtime']}")
    print(f"sample_status_answer={report['sample_status_answer']}")
    print(f"sample_unified_brain_answer={report['sample_unified_brain_answer']}")
    print(f"sample_what_next_answer={report['sample_what_next_answer']}")
    print(f"unknown_intent_answer={report['unknown_intent_answer']}")
    print(f"safety_result={'PASS' if report['status'] == 'PASS' else 'FAIL'}")
    if report["failures"]:
        print("failures=" + "; ".join(report["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
