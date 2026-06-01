"""Batch 9A checker for ECHO localhost smoke and VPS readiness plan."""

from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
SMOKE_PATH = ECHO_DIR / "echo_uvicorn_local_smoke_test.json"
VPS_PLAN_PATH = ECHO_DIR / "echo_vps_deployment_readiness_plan.json"
SUMMARY_PATH = ECHO_DIR / "echo_batch9a_summary.json"
SMOKE_SOURCE = REPO_ROOT / "titan_echo" / "echo_uvicorn_local_smoke_test.py"
VPS_SOURCE = REPO_ROOT / "titan_echo" / "echo_vps_deployment_readiness_plan.py"
CHECK_SOURCE = REPO_ROOT / "titan_echo" / "echo_batch9a_check.py"
SOURCE_FILES = (SMOKE_SOURCE, VPS_SOURCE, CHECK_SOURCE)
IST = timezone(timedelta(hours=5, minutes=30))

EXPECTED_WRITES = {
    "data/runtime/echo/echo_uvicorn_local_smoke_test.json",
    "data/runtime/echo/echo_vps_deployment_readiness_plan.json",
    "data/runtime/echo/echo_batch9a_summary.json",
}
PLACEHOLDER_KEYS = {"temporary-test-key", "wrong-temporary-test-key"}
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
    *PLACEHOLDER_KEYS,
}
DANGEROUS_IMPORT_ROOTS = {"requests", "shlex"}
DANGEROUS_CALL_ROOTS = {"requests", "shlex"}
POST_LIKE_NAMES = {"delete", "patch", "post", "put"}
UNSAFE_ENDPOINT_TOKENS = ("command", "shell", "deploy", "restart", "broker", "risk", "order", "codex")


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def write_echo_json(path: Path, payload: Any) -> None:
    resolved_echo = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_echo not in (resolved_path, *resolved_path.parents):
        raise ValueError("Batch 9A checker writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


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
                if call_name.rsplit(".", 1)[-1].lower() in POST_LIKE_NAMES:
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


def unsafe_endpoint_found(smoke: dict[str, Any]) -> bool:
    endpoints = [test.get("path", "") for test in smoke.get("tests", []) if isinstance(test, dict)]
    allowed_runtime_paths = {"/health", "/answer", "/query"}
    for endpoint in endpoints:
        text = str(endpoint).lower()
        if endpoint in allowed_runtime_paths:
            continue
        if endpoint.startswith("/query"):
            continue
        if any(token in text for token in UNSAFE_ENDPOINT_TOKENS):
            return True
    return False


def build_summary() -> dict[str, Any]:
    failures: list[str] = []
    if not SMOKE_PATH.exists():
        failures.append(f"missing {relative(SMOKE_PATH)}")
    if not VPS_PLAN_PATH.exists():
        failures.append(f"missing {relative(VPS_PLAN_PATH)}")
    smoke = read_json(SMOKE_PATH) if SMOKE_PATH.exists() else {}
    vps_plan = read_json(VPS_PLAN_PATH) if VPS_PLAN_PATH.exists() else {}
    scan = source_scan(SOURCE_FILES)
    secrets = secret_like_findings(SOURCE_FILES, (smoke, vps_plan))

    if smoke.get("local_server_smoke_result") != "PASS":
        failures.append("local server smoke did not pass")
    if smoke.get("auth_result") != "PASS":
        failures.append("auth result did not pass")
    if smoke.get("server_stopped_confirmation") is not True:
        failures.append("server stopped confirmation is not true")
    if smoke.get("bind_host") != "127.0.0.1":
        failures.append("bind host is not 127.0.0.1")
    if smoke.get("port") != 8765:
        failures.append("port is not 8765")
    if smoke.get("safety", {}).get("public_exposure") is not False:
        failures.append("public exposure is not false")
    if smoke.get("safety", {}).get("bind_0_0_0_0") is not False:
        failures.append("0.0.0.0 bind flag is not false")
    if smoke.get("safety", {}).get("real_secret_written") is not False:
        failures.append("real secret written flag is not false")
    if smoke.get("safety", {}).get("deploy") is not False or smoke.get("safety", {}).get("push") is not False or smoke.get("safety", {}).get("restart") is not False:
        failures.append("deploy/push/restart flag is not false in smoke")
    if smoke.get("safety_result") != "PASS":
        failures.append("smoke safety_result is not PASS")
    if vps_plan.get("documentation_only") is not True:
        failures.append("VPS plan is not documentation-only")
    if vps_plan.get("vps_required_path") != "/home/ubuntu/titan-bot":
        failures.append("VPS required path mismatch")
    if vps_plan.get("bind_host") != "127.0.0.1":
        failures.append("VPS bind host mismatch")
    if vps_plan.get("port") != 8765:
        failures.append("VPS port mismatch")
    if vps_plan.get("env_var") != "ECHO_API_KEY":
        failures.append("VPS env var mismatch")
    for flag in ("public_exposure_allowed", "nginx_allowed_now", "cloudflare_allowed_now", "https_allowed_now", "chatgpt_action_allowed_now", "deploy_performed", "push_performed", "restart_performed"):
        if vps_plan.get(flag) is not False:
            failures.append(f"VPS flag {flag} is not false")
    if vps_plan.get("safety_result") != "PASS":
        failures.append("VPS plan safety_result is not PASS")
    if unsafe_endpoint_found(smoke):
        failures.append("unsafe endpoint found")
    for source_name, payload in (("smoke", smoke), ("vps_plan", vps_plan)):
        writes = payload.get("safety", {}).get("writes_only")
        if not isinstance(writes, list) or not all(str(item).startswith("data/runtime/echo/") for item in writes):
            failures.append(f"{source_name} writes_only is invalid")
    for key, values in scan.items():
        if values:
            failures.append(f"{key} found")
    if secrets:
        failures.append("secret-like value found")

    summary = {
        "schema": "titan.echo.batch9a_summary.v1",
        "timestamp_ist": timestamp_ist(),
        "local_server_smoke_result": smoke.get("local_server_smoke_result"),
        "auth_result": smoke.get("auth_result"),
        "server_stopped_confirmation": smoke.get("server_stopped_confirmation"),
        "vps_readiness_status": vps_plan.get("vps_readiness_status"),
        "bind_host": smoke.get("bind_host"),
        "port": smoke.get("port"),
        "tests_passed": smoke.get("tests_passed", 0),
        "tests_failed": smoke.get("tests_failed", 0),
        "public_exposure": False,
        "unsafe_endpoint_count": 0 if not unsafe_endpoint_found(smoke) else 1,
        "deploy_push_restart_performed": False,
        "source_scan": scan,
        "secret_like_findings": secrets,
        "safety_result": "PASS" if not failures else "FAIL",
        "failures": failures,
        "next_recommended_step": vps_plan.get("next_recommended_step"),
        "safety": {
            "local_server_test_passed": smoke.get("local_server_smoke_result") == "PASS",
            "server_stopped": smoke.get("server_stopped_confirmation") is True,
            "bind_127_0_0_1_only": smoke.get("bind_host") == "127.0.0.1",
            "auth_worked": smoke.get("auth_result") == "PASS",
            "no_public_exposure": True,
            "no_real_key_written": True,
            "no_deploy_push_restart": True,
            "vps_plan_documentation_only": vps_plan.get("documentation_only") is True,
            "writes_only": sorted(EXPECTED_WRITES),
        },
    }
    write_echo_json(SUMMARY_PATH, summary)
    return summary


def main() -> None:
    summary = build_summary()
    print("ECHO Batch 9A check complete.")
    print(f"local_server_smoke_result={summary['local_server_smoke_result']}")
    print(f"auth_result={summary['auth_result']}")
    print(f"server_stopped_confirmation={summary['server_stopped_confirmation']}")
    print(f"vps_readiness_status={summary['vps_readiness_status']}")
    print(f"safety_result={summary['safety_result']}")
    print(f"next_recommended_step={summary['next_recommended_step']}")
    if summary["failures"]:
        print("failures=" + "; ".join(summary["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
