"""Check ECHO approval-gated bridge readiness plan."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
READINESS_PATH = ECHO_DIR / "echo_bridge_readiness.json"
SUMMARY_PATH = ECHO_DIR / "echo_bridge_readiness_summary.json"
DOC_PATH = REPO_ROOT / "docs" / "echo_chatgpt_codex_bridge_plan.md"

EXPECTED_READ = {
    ("GET", "/health"),
    ("GET", "/status"),
    ("GET", "/answer"),
    ("GET", "/query"),
    ("GET", "/approval/pending"),
    ("GET", "/mission/current"),
    ("GET", "/verification/latest"),
}
EXPECTED_GATED = {
    ("POST", "/mission/prepare"),
    ("POST", "/approval/approve"),
    ("POST", "/approval/reject"),
    ("POST", "/codex/run-approved"),
    ("POST", "/git/push-approved"),
    ("POST", "/vps/pull-approved"),
    ("POST", "/verify/run-approved"),
    ("POST", "/deploy/approved"),
    ("POST", "/rollback/approved"),
}


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def pairs(items: Any) -> set[tuple[str, str]]:
    if not isinstance(items, list):
        return set()
    result = set()
    for item in items:
        if isinstance(item, dict):
            result.add((str(item.get("method")), str(item.get("path"))))
    return result


def main() -> int:
    failures: list[str] = []
    readiness = read_json(READINESS_PATH)
    summary = read_json(SUMMARY_PATH)
    doc_exists = DOC_PATH.exists() and DOC_PATH.stat().st_size > 0
    if not isinstance(readiness, dict):
        failures.append("readiness JSON missing or invalid")
        readiness = {}
    if not isinstance(summary, dict):
        failures.append("summary JSON missing or invalid")
        summary = {}

    read_pairs = pairs(readiness.get("read_endpoints"))
    gated_pairs = pairs(readiness.get("approval_gated_endpoints"))
    if read_pairs != EXPECTED_READ:
        failures.append("read endpoint plan mismatch")
    if gated_pairs != EXPECTED_GATED:
        failures.append("approval-gated endpoint plan mismatch")
    if readiness.get("unsafe_endpoint_count") != 0:
        failures.append("unsafe endpoint count must be zero")
    if summary.get("approval_required_for_writes") is not True:
        failures.append("writes must require approval")
    if not doc_exists:
        failures.append("bridge plan doc missing")

    safety = readiness.get("safety", {}) if isinstance(readiness.get("safety"), dict) else {}
    required_false = [
        "public_unauthenticated_api",
        "raw_shell_endpoint",
        "chatgpt_direct_codex",
        "chatgpt_direct_git_push",
        "chatgpt_direct_vps_pull",
        "chatgpt_direct_deploy_restart_rollback",
        "broker_endpoint",
        "risk_endpoint",
        "execution_endpoint",
        "live_trade_control",
        "secret_committed",
        "running_service_modified",
        "deploy",
        "push",
        "restart",
    ]
    for key in required_false:
        if safety.get(key) is not False:
            failures.append(f"safety.{key} must be false")
    if safety.get("readiness_only") is not True:
        failures.append("safety.readiness_only must be true")

    print("ECHO bridge readiness check")
    print(f"read_endpoint_count={summary.get('read_endpoint_count')}")
    print(f"approval_gated_endpoint_count={summary.get('approval_gated_endpoint_count')}")
    print(f"unsafe_endpoint_count={summary.get('unsafe_endpoint_count')}")
    print(f"approval_required_for_writes={summary.get('approval_required_for_writes')}")
    print(f"safety_result={'PASS' if not failures else 'FAIL'}")
    if failures:
        for failure in failures:
            print(f"failure={failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
