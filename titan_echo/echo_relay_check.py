"""Import-only checker for the disabled ECHO relay skeleton."""

from __future__ import annotations

from typing import Any

from titan_echo import echo_relay_api
from titan_echo.echo_relay_config import ALLOWED_ECHO_ENDPOINTS, BLOCKED_PREFIXES, relay_status_payload


REQUIRED_ROUTES = {
    "/relay/health",
    "/relay/jarvis/ask",
    "/relay/titan/status",
    "/relay/chatgpt/integration/status",
    "/relay/chatgpt/evidence/contract",
    "/relay/chatgpt/evidence/catalog",
}

REQUIRED_BLOCKED_PREFIXES = {
    "/mission",
    "/approval",
    "/execution",
    "/codex",
    "/deploy",
    "/rollback",
}

REQUIRED_ALLOWED_ECHO_ENDPOINTS = {
    "/chatgpt/integration/status",
    "/chatgpt/evidence/contract",
    "/chatgpt/evidence/catalog",
    "/jarvis/ask",
    "/titan/status",
}


def route_paths() -> list[str]:
    app = getattr(echo_relay_api, "app", None)
    if app is None:
        return []
    return sorted(
        path
        for route in getattr(app, "routes", [])
        for path in [getattr(route, "path", "")]
        if path.startswith("/relay/")
    )


def build_check() -> dict[str, Any]:
    routes = route_paths()
    missing = sorted(REQUIRED_ROUTES - set(routes))
    extra = sorted(set(routes) - REQUIRED_ROUTES)
    status = relay_status_payload()
    failures = []
    if missing:
        failures.append("relay route missing")
    if extra:
        failures.append("unexpected relay route present")
    if set(ALLOWED_ECHO_ENDPOINTS) != REQUIRED_ALLOWED_ECHO_ENDPOINTS:
        failures.append("upstream allowlist mismatch")
    if not REQUIRED_BLOCKED_PREFIXES.issubset(set(BLOCKED_PREFIXES)):
        failures.append("blocked prefix missing")
    if status["status"] != "RELAY_DISABLED":
        failures.append("relay is not disabled by default")
    return {
        "schema": "titan.echo.relay_check.v1",
        "status": "PASS" if not failures else "FAIL",
        "routes": routes,
        "missing_routes": missing,
        "extra_routes": extra,
        "allowed_echo_endpoints": sorted(ALLOWED_ECHO_ENDPOINTS),
        "blocked_prefixes": sorted(BLOCKED_PREFIXES),
        "relay_status": status,
        "failures": failures,
    }


if __name__ == "__main__":
    report = build_check()
    print("ECHO relay check complete.")
    print(f"status={report['status']}")
    print("routes=" + ", ".join(report["routes"]))
    if report["failures"]:
        print("failures=" + "; ".join(report["failures"]))
        raise SystemExit(1)
