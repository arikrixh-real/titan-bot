"""Import-only checker for the disabled ECHO relay skeleton."""

from __future__ import annotations

from typing import Any

from titan_echo import echo_relay_api
from titan_echo.echo_relay_config import relay_status_payload


REQUIRED_ROUTES = {
    "/relay/health",
    "/relay/allowlist",
    "/relay/jarvis/ask",
    "/relay/titan/status",
    "/relay/chatgpt/integration/status",
    "/relay/chatgpt/evidence/contract",
    "/relay/chatgpt/evidence/catalog",
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
    status = relay_status_payload()
    failures = []
    if missing:
        failures.append("relay route missing")
    if status["status"] != "RELAY_DISABLED":
        failures.append("relay is not disabled by default")
    return {
        "schema": "titan.echo.relay_check.v1",
        "status": "PASS" if not failures else "FAIL",
        "routes": routes,
        "missing_routes": missing,
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
