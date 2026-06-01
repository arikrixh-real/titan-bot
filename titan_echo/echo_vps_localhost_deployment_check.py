"""Safety checker for ECHO VPS localhost deployment plan."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
PLAN_SOURCE = REPO_ROOT / "titan_echo" / "echo_vps_localhost_deployment_plan.py"
CHECK_SOURCE = REPO_ROOT / "titan_echo" / "echo_vps_localhost_deployment_check.py"
PLAN_PATH = ECHO_DIR / "echo_vps_localhost_deployment_plan.json"
SUMMARY_PATH = ECHO_DIR / "echo_vps_localhost_deployment_summary.json"

SOURCE_FILES = (PLAN_SOURCE, CHECK_SOURCE)
EXPECTED_WRITES = {
    "data/runtime/echo/echo_vps_localhost_deployment_plan.json",
    "data/runtime/echo/echo_vps_localhost_deployment_summary.json",
}
APPROVAL_PHRASE = "I_APPROVE_ECHO_VPS_LOCALHOST_TEST"
PLACEHOLDER_KEY = "temporary-test-key"
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
SAFE_SECRET_VALUES = {
    "changeme",
    "dummy",
    "example",
    "none",
    "null",
    "placeholder",
    "redacted",
    PLACEHOLDER_KEY,
}
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
SERVER_CALL_NAMES = {"bind", "listen", "serve", "start_server", "run"}
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
                if leaf in SERVER_CALL_NAMES and call_name != "print":
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


def writes_only_to_echo(plan: dict[str, Any]) -> bool:
    writes = plan.get("safety", {}).get("writes_only")
    if not isinstance(writes, list):
        return False
    return set(writes) == EXPECTED_WRITES and all(str(item).startswith("data/runtime/echo/") for item in writes)


def build_check() -> dict[str, Any]:
    failures: list[str] = []
    if not PLAN_PATH.exists():
        failures.append(f"missing {relative(PLAN_PATH)}")
    if not SUMMARY_PATH.exists():
        failures.append(f"missing {relative(SUMMARY_PATH)}")
    plan = read_json(PLAN_PATH) if PLAN_PATH.exists() else {}
    summary = read_json(SUMMARY_PATH) if SUMMARY_PATH.exists() else {}
    scan = source_scan(SOURCE_FILES)
    secrets = secret_like_findings(SOURCE_FILES, (plan, summary))

    gate = plan.get("approval_gate", {})
    preflight = plan.get("preflight_requirements", {})
    commands = plan.get("vps_local_test_command_text_only", {})
    safety = plan.get("safety", {})

    if plan.get("schema") != "titan.echo.vps_localhost_deployment_plan.v1":
        failures.append("invalid plan schema")
    if summary.get("schema") != "titan.echo.vps_localhost_deployment_summary.v1":
        failures.append("invalid summary schema")
    if plan.get("plan_only") is not True:
        failures.append("plan_only is not true")
    if preflight.get("vps_path") != "/home/ubuntu/titan-bot":
        failures.append("VPS path mismatch")
    if preflight.get("python_venv_path") != "/home/ubuntu/titan-bot/.venv":
        failures.append("venv path mismatch")
    if set(preflight.get("required_packages", [])) != {"fastapi", "uvicorn"}:
        failures.append("required package set mismatch")
    if preflight.get("required_env_var") != "ECHO_API_KEY":
        failures.append("required env var mismatch")
    if preflight.get("bind_host") != "127.0.0.1 only":
        failures.append("bind host is not localhost-only")
    if preflight.get("port") != 8765:
        failures.append("port mismatch")
    if commands.get("executed") is not False:
        failures.append("VPS command text is marked executed")
    if "--host 127.0.0.1" not in commands.get("run", ""):
        failures.append("VPS command does not bind 127.0.0.1")
    if "--host 0.0.0.0" in commands.get("run", ""):
        failures.append("VPS command binds 0.0.0.0")
    if PLACEHOLDER_KEY not in commands.get("set_env", ""):
        failures.append("temporary placeholder key text missing")
    if gate.get("approval_required") is not True:
        failures.append("approval_required is not true")
    if gate.get("required_approval_phrase") != APPROVAL_PHRASE:
        failures.append("approval phrase mismatch")
    if gate.get("approved_now") is not False:
        failures.append("plan is marked approved now")
    if gate.get("vps_localhost_test_ready") is not True:
        failures.append("vps_localhost_test_ready is not true")
    for flag in ("public_exposure_allowed", "chatgpt_connection_allowed", "codex_execution_allowed"):
        if gate.get(flag) is not False:
            failures.append(f"approval gate flag {flag} is not false")
    stop_plan = plan.get("rollback_stop_plan", {})
    if stop_plan.get("manual_test_stop") != "CTRL+C":
        failures.append("stop plan missing CTRL+C")
    if stop_plan.get("systemd_service_allowed") is not False or stop_plan.get("auto_start_allowed") is not False:
        failures.append("systemd/auto-start is allowed")
    for flag in (
        "push_github",
        "pull_on_vps",
        "vps_server_started",
        "titan_restart",
        "public_port_exposed",
        "bind_0_0_0_0",
        "broker_risk_scanner_master_unified_changes",
        "real_api_key_written",
        "vps_commands_executed",
        "deploy_automation",
        "command_endpoints",
        "post_execution_endpoints",
    ):
        if safety.get(flag) is not False:
            failures.append(f"safety flag {flag} is not false")
    if safety.get("documentation_readiness_only") is not True:
        failures.append("documentation_readiness_only is not true")
    if not writes_only_to_echo(plan):
        failures.append("writes are not limited to requested data/runtime/echo outputs")
    for key, values in scan.items():
        if values:
            failures.append(f"{key} found")
    if secrets:
        failures.append("secret-like value found")
    if plan.get("safety_result") != "PASS" or summary.get("safety_result") != "PASS":
        failures.append("safety_result is not PASS")

    return {
        "schema": "titan.echo.vps_localhost_deployment_check.v1",
        "checked_files": [relative(path) for path in SOURCE_FILES],
        "checked_artifacts": [relative(PLAN_PATH), relative(SUMMARY_PATH)],
        "vps_localhost_test_ready": summary.get("vps_localhost_test_ready"),
        "approval_required": summary.get("approval_required"),
        "required_approval_phrase": summary.get("required_approval_phrase"),
        "bind_host": summary.get("bind_host"),
        "port": summary.get("port"),
        "public_exposure_allowed": summary.get("public_exposure_allowed"),
        "source_scan": scan,
        "secret_like_findings": secrets,
        "writes_only_to_data_runtime_echo": writes_only_to_echo(plan),
        "safety_result": "PASS" if not failures else "FAIL",
        "failures": failures,
        "next_recommended_step": summary.get("next_recommended_step"),
    }


def main() -> None:
    check = build_check()
    print("ECHO VPS localhost deployment check complete.")
    print(f"vps_localhost_test_ready={check['vps_localhost_test_ready']}")
    print(f"approval_required={check['approval_required']}")
    print(f"required_approval_phrase={check['required_approval_phrase']}")
    print(f"bind_host={check['bind_host']}")
    print(f"port={check['port']}")
    print(f"public_exposure_allowed={check['public_exposure_allowed']}")
    print(f"next_recommended_step={check['next_recommended_step']}")
    print(f"safety_result={check['safety_result']}")
    if check["failures"]:
        print("failures=" + "; ".join(check["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
