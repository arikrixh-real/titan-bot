"""Check ECHO outcome lineage map artifacts and safety."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
MAP_PATH = RUNTIME_ECHO_DIR / "outcome_lineage_map.json"
SUMMARY_PATH = RUNTIME_ECHO_DIR / "outcome_lineage_summary.json"
SCRIPTS = [
    REPO_ROOT / "titan_echo" / "echo_outcome_lineage_mapper.py",
    REPO_ROOT / "titan_echo" / "echo_outcome_lineage_check.py",
]
PROTECTED_PREFIXES = (
    "runtime_scanner.py",
    "scanner_filter_truth.py",
    "runtime_master_brain.py",
    "titan_master_brain/",
    "consciousness_core/",
    "runtime_paper_engine.py",
    "runtime_risk_watchdog.py",
    "engines/risk_engine.py",
    "engines/pro_risk_engine.py",
    "engines/broker_execution_safety_system.py",
    "journal/trade_execution_layer.py",
    "unified_brain/",
)
FORBIDDEN_CODE_TERMS = tuple(
    name + "("
    for name in (
        "send_telegram_signals",
        "place_order",
        "open_paper_position",
        "create_client",
        "run_master_brain",
        "scan_for_setups",
        "calculate_rr",
    )
)
VALID_VERDICTS = {"COMPLETE", "PARTIAL", "BROKEN"}


def load_json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            errors.append(f"{path.name} must contain a JSON object")
            return {}
        return payload
    except Exception as exc:
        errors.append(f"invalid json {path}: {exc}")
        return {}


def safe_float(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def git_names(args: list[str]) -> list[str]:
    result = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if result.returncode:
        return []
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def protected_code_changes() -> list[str]:
    names = set(git_names(["diff", "--name-only"]))
    names.update(git_names(["diff", "--cached", "--name-only"]))
    return [
        name
        for name in sorted(names)
        if any(name == prefix.rstrip("/") or name.startswith(prefix) for prefix in PROTECTED_PREFIXES)
        and name not in {"titan_echo/echo_outcome_lineage_mapper.py", "titan_echo/echo_outcome_lineage_check.py"}
    ]


def forbidden_code_hits() -> list[str]:
    hits = []
    for path in SCRIPTS:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for term in FORBIDDEN_CODE_TERMS:
            if term in text:
                hits.append(f"{path.name}:{term}")
    return hits


def main() -> int:
    errors: list[str] = []
    for path in SCRIPTS + [MAP_PATH, SUMMARY_PATH]:
        if not path.exists():
            errors.append(f"missing required file: {path}")
    lineage_map = load_json(MAP_PATH, errors) if MAP_PATH.exists() else {}
    summary = load_json(SUMMARY_PATH, errors) if SUMMARY_PATH.exists() else {}
    if summary.get("verdict") not in VALID_VERDICTS:
        errors.append("invalid lineage verdict")
    for field in ("lineage_completeness_score", "traceability_score", "learning_linkage_score", "evolution_linkage_score"):
        value = safe_float(summary.get(field))
        if value < 0 or value > 100:
            errors.append(f"{field} out of range")
    if not isinstance(summary.get("TOP_20_LINEAGE_GAPS"), list):
        errors.append("TOP_20_LINEAGE_GAPS must be a list")
    if not isinstance(lineage_map.get("identifier_summary"), dict):
        errors.append("identifier_summary missing from lineage map")
    if not isinstance(lineage_map.get("lineage_edges"), dict):
        errors.append("lineage_edges missing from lineage map")
    safety = lineage_map.get("safety_contract", {})
    for key in ("scanner_mutation", "master_brain_mutation", "unified_brain_mutation", "consciousness_core_mutation", "broker_mutation", "risk_logic_mutation", "deploy", "restart", "push"):
        if safety.get(key) is not False:
            errors.append(f"safety_contract {key} is not false")
    protected = protected_code_changes()
    if protected:
        errors.append("protected scanner/Master Brain/Unified Brain/risk/broker files modified: " + ", ".join(protected[:20]))
    forbidden = forbidden_code_hits()
    if forbidden:
        errors.append("forbidden execution path term found in outcome lineage scripts: " + ", ".join(forbidden))
    if errors:
        print("TITAN ECHO outcome lineage check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("TITAN ECHO outcome lineage check: PASSED")
    print(f"Lineage completeness: {summary.get('lineage_completeness_score')}")
    print(f"Traceability score: {summary.get('traceability_score')}")
    print(f"Orphan count: {summary.get('orphan_count')}")
    print(f"Verdict: {summary.get('verdict')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
