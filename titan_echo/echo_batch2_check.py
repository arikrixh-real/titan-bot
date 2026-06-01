"""Batch 2 checker for ECHO observer/proof/operator skeletons.

This checker calls internal Python functions only. It does not spawn shell
commands, invoke git, restart services, deploy, or mutate TITAN runtime files.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from titan_echo.echo_api import (
    app,
    get_echo_alerts,
    get_echo_auto_report,
    get_echo_deploy_plan,
    get_echo_evolution_proof,
    get_echo_integration_proof,
    get_echo_observer,
    get_echo_rollback_plan,
    get_echo_verify_plan,
)
from titan_echo.echo_api_auth import PROTECTED_ENDPOINTS
from titan_echo.echo_batch2_common import REPO_ROOT, echo_path, read_json, safety, write_echo_json


CHECK_OUTPUT_PATH = echo_path("echo_batch2_check.json")

EXPECTED_OUTPUTS = {
    "observations": (echo_path("observations.json"), {"OBSERVATION_READY", "PARTIAL_EVIDENCE", "UNKNOWN_NOT_PROVEN"}),
    "alert_queue": (echo_path("alert_queue.json"), {"ALERT_ENGINE_DRAFT_ONLY"}),
    "integration_proof": (echo_path("integration_proof_report.json"), {"INTEGRATION_PROOF_READY", "PARTIAL_EVIDENCE", "UNKNOWN_NOT_PROVEN"}),
    "evolution_proof": (echo_path("evolution_proof_report.json"), {"EVOLUTION_PROOF_READY", "PARTIAL_EVIDENCE", "UNKNOWN_NOT_PROVEN"}),
    "verification_plan": (echo_path("verification_plan.json"), {"VERIFIER_PLAN_ONLY"}),
    "deployment_plan": (echo_path("deployment_plan.json"), {"DEPLOYER_DISABLED_PLAN_ONLY"}),
    "rollback_plan": (echo_path("rollback_plan.json"), {"ROLLBACK_DISABLED_PLAN_ONLY"}),
    "auto_report": (echo_path("auto_report.json"), {"AUTO_REPORT_READY"}),
}

EXPECTED_ROUTES = {
    "/echo/observer",
    "/echo/alerts",
    "/echo/proof/integration",
    "/echo/proof/evolution",
    "/echo/verify/plan",
    "/echo/deploy/plan",
    "/echo/rollback/plan",
    "/echo/report/auto",
}

API_FUNCTIONS = {
    "/echo/observer": get_echo_observer,
    "/echo/alerts": get_echo_alerts,
    "/echo/proof/integration": get_echo_integration_proof,
    "/echo/proof/evolution": get_echo_evolution_proof,
    "/echo/verify/plan": get_echo_verify_plan,
    "/echo/deploy/plan": get_echo_deploy_plan,
    "/echo/rollback/plan": get_echo_rollback_plan,
    "/echo/report/auto": get_echo_auto_report,
}

BATCH2_MODULES = [
    REPO_ROOT / "titan_echo" / "echo_observer.py",
    REPO_ROOT / "titan_echo" / "echo_alert_engine.py",
    REPO_ROOT / "titan_echo" / "echo_integration_proof_engine.py",
    REPO_ROOT / "titan_echo" / "echo_evolution_proof_engine.py",
    REPO_ROOT / "titan_echo" / "echo_verifier.py",
    REPO_ROOT / "titan_echo" / "echo_deployer.py",
    REPO_ROOT / "titan_echo" / "echo_rollback.py",
    REPO_ROOT / "titan_echo" / "echo_auto_reporter.py",
    REPO_ROOT / "titan_echo" / "echo_batch2_common.py",
    REPO_ROOT / "titan_echo" / "echo_batch2_check.py",
]

FORBIDDEN_IMPORTS = {"subprocess"}
FORBIDDEN_CALL_NAMES = {"system", "popen", "execv", "execve", "spawnv", "spawnve"}


def _safety_ok(payload: dict[str, Any]) -> bool:
    return payload.get("safety") == safety()


def _api_response_ok(response: Any) -> bool:
    if not isinstance(response, dict):
        return False
    if set(response) != {"source", "status", "data"}:
        return False
    data = response.get("data")
    return data is None or (isinstance(data, dict) and data.get("safety") == safety())


def _route_auth_map() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if app is None:
        return result
    route_map = {route.path: route for route in app.routes}
    for path in EXPECTED_ROUTES:
        route = route_map.get(path)
        if route is None:
            continue
        dependency_attr = getattr(route, "dependencies", None)
        names = []
        for dependency in dependency_attr or []:
            call = getattr(dependency, "dependency", None)
            names.append(getattr(call, "__name__", str(call)))
        methods = getattr(route, "methods", set()) or set()
        result[path] = {
            "methods": sorted(methods),
            "protected": "require_echo_api_key" in names if dependency_attr is not None else None,
            "dependencies": names,
            "dependency_inspectable": dependency_attr is not None,
        }
    return result


def _discovered_echo_paths() -> list[str]:
    if app is None:
        return []
    return sorted(
        path
        for path in (getattr(route, "path", None) for route in app.routes)
        if isinstance(path, str) and path.startswith("/echo/")
    )


def _source_safety_scan() -> list[str]:
    failures = []
    for path in BATCH2_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name.split(".")[0] for alias in getattr(node, "names", [])]
                module = getattr(node, "module", None)
                if module:
                    names.append(str(module).split(".")[0])
                if any(name in FORBIDDEN_IMPORTS for name in names):
                    failures.append(f"{path.name}: forbidden import")
            if isinstance(node, ast.Call):
                func = node.func
                call_name = ""
                if isinstance(func, ast.Name):
                    call_name = func.id
                elif isinstance(func, ast.Attribute):
                    call_name = func.attr
                if call_name in FORBIDDEN_CALL_NAMES:
                    failures.append(f"{path.name}: forbidden call {call_name}")
    return failures


def run_check() -> dict[str, Any]:
    failures = []
    outputs = {}
    for name, (path, allowed_statuses) in EXPECTED_OUTPUTS.items():
        payload, error = read_json(path)
        status = payload.get("status") if isinstance(payload, dict) else None
        ok = isinstance(payload, dict) and error is None and status in allowed_statuses and _safety_ok(payload)
        outputs[name] = {
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "status": status,
            "exists": error is None,
            "safety_object_ok": isinstance(payload, dict) and _safety_ok(payload),
        }
        if not ok:
            failures.append(f"{name} output invalid")

    missing_protected = sorted(route for route in EXPECTED_ROUTES if route not in PROTECTED_ENDPOINTS)
    failures.extend(f"{route} missing from PROTECTED_ENDPOINTS" for route in missing_protected)

    route_auth = _route_auth_map()
    missing_routes = sorted(EXPECTED_ROUTES - set(route_auth))
    failures.extend(f"{route} missing from FastAPI app" for route in missing_routes)
    for route, info in route_auth.items():
        if "GET" not in info["methods"]:
            failures.append(f"{route} missing GET method")
        if info["dependency_inspectable"] and info["protected"] is not True:
            failures.append(f"{route} missing require_echo_api_key dependency")

    api_responses = {}
    for route, func in API_FUNCTIONS.items():
        response = func()
        ok = _api_response_ok(response)
        api_responses[route] = {
            "status": response.get("status") if isinstance(response, dict) else None,
            "schema_ok": isinstance(response, dict) and set(response) == {"source", "status", "data"},
            "safety_object_ok": ok,
        }
        if not ok:
            failures.append(f"{route} response schema or safety object invalid")

    failures.extend(_source_safety_scan())
    report = {
        "schema": "titan.echo.batch2_check.v1",
        "status": "PASS" if not failures else "FAIL",
        "outputs": outputs,
        "route_auth": route_auth,
        "discovered_echo_paths": _discovered_echo_paths(),
        "api_responses": api_responses,
        "protected_endpoints_checked": sorted(EXPECTED_ROUTES),
        "failures": failures,
        "safety": safety(),
    }
    write_echo_json(CHECK_OUTPUT_PATH, report)
    return report


def main() -> int:
    report = run_check()
    print(f"ECHO batch2 check: {report['status']}")
    print(f"Outputs checked: {len(report['outputs'])}")
    print(f"Routes checked: {len(report['protected_endpoints_checked'])}")
    if report["failures"]:
        print("Discovered /echo/ paths:")
        for path in report["discovered_echo_paths"]:
            print(f"  {path}")
        for failure in report["failures"]:
            print(f"FAIL: {failure}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
