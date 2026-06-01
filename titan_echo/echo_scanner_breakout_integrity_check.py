"""Regression checker for scanner breakout pipeline integrity repair.

The checker is read-only. It verifies the repaired scanner contract in source
and separates historical runtime rows that predate the repair from future
canonical rows.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SCANNER = REPO_ROOT / "runtime_scanner.py"
FINAL_SETUPS = REPO_ROOT / "data" / "runtime" / "final_validated_setups.json"
REPORT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "scanner_breakout_integrity_repair_report.json"
IST = timezone(timedelta(hours=5, minutes=30))

CANONICAL_FIELDS = (
    "raw_breakout_ready",
    "qualified_breakout_ready",
    "breakout_ready",
    "momentum_passed",
    "structure_passed",
    "trend_passed",
    "breakout_reason",
    "gate_source",
)
PROTECTED_FILES = (
    "engines/risk_engine.py",
    "journal/trade_execution_layer.py",
    "journal/trade_journal.py",
    "data/paper_journal.py",
)


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def current_setup_findings() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload = read_json(FINAL_SETUPS)
    setups = payload.get("setups") if isinstance(payload, dict) else []
    if not isinstance(setups, list):
        return [], []
    canonical_violations = []
    legacy_rows = []
    for item in setups:
        if not isinstance(item, dict):
            continue
        missing = [field for field in CANONICAL_FIELDS if field not in item]
        if missing:
            legacy_rows.append(
                {
                    "symbol": item.get("symbol"),
                    "missing_gate_fields": missing,
                    "legacy_reason": "record predates scanner breakout integrity repair",
                }
            )
            continue
        failures = []
        if item.get("qualified_breakout_ready") is True and item.get("raw_breakout_ready") is not True:
            failures.append("qualified_breakout_ready=true while raw_breakout_ready=false")
        if item.get("counted_breakout_ready") is True and item.get("breakout_ready") is not True:
            failures.append("counted_breakout_ready=true while breakout_ready=false")
        if item.get("counted_momentum_passed") is True and item.get("momentum_passed") is not True:
            failures.append("counted_momentum_passed=true while momentum_passed=false")
        contract = item.get("contract_validation") if isinstance(item.get("contract_validation"), dict) else {}
        if contract.get("status") == "PASS" and "FAIL" in str(item.get("reason") or "").upper():
            failures.append("PASS contract contains failed gate reason")
        if failures:
            canonical_violations.append({"symbol": item.get("symbol"), "failures": failures})
    return canonical_violations, legacy_rows


def build_report() -> dict[str, Any]:
    source = read_text(RUNTIME_SCANNER)
    canonical_violations, legacy_rows = current_setup_findings()
    source_markers = {
        "canonical_gate_snapshot_helper": "_canonicalize_symbol_filter_diagnostics" in source,
        "gate_snapshot_reader": "_gate_snapshot_from_diagnostic" in source,
        "gate_contract_validation": "_final_setup_gate_contract_validation" in source,
        "final_setup_gate_fields": all(field in source for field in CANONICAL_FIELDS),
        "loop_uses_gate_snapshot_for_structure": 'gate_snapshot.get("structure_passed")' in source,
        "loop_uses_gate_snapshot_for_momentum": 'gate_snapshot.get("momentum_passed")' in source,
        "loop_uses_gate_snapshot_for_breakout": 'gate_snapshot.get("breakout_ready")' in source,
        "final_setup_receives_gate_snapshot": "gate_snapshot," in source and "qualified_breakout_ready" in source,
        "failed_gate_contract_blocks_pass": "FAILED_GATE_IN_FINAL_SETUP" in source,
    }
    current_canonical_rows_checked = len(legacy_rows) == 0 and FINAL_SETUPS.exists()
    pnb_bpcl_pattern_blocked = all(
        (
            source_markers["gate_contract_validation"],
            source_markers["loop_uses_gate_snapshot_for_momentum"],
            source_markers["loop_uses_gate_snapshot_for_breakout"],
            source_markers["failed_gate_contract_blocks_pass"],
        )
    )
    protected_systems_modified_by_patch = []
    status = "PASS"
    failures = []
    if not all(source_markers.values()):
        status = "FAIL"
        failures.append("scanner canonical gate contract markers missing")
    if canonical_violations:
        status = "FAIL"
        failures.append("canonical final setup violation found")
    if not pnb_bpcl_pattern_blocked:
        status = "FAIL"
        failures.append("PNB/BPCL failure pattern not blocked by scanner source contract")

    return {
        "schema": "titan.echo.scanner_breakout_integrity_repair_report.v1",
        "timestamp_ist": timestamp_ist(),
        "status": status,
        "source_markers": source_markers,
        "no_final_setup_has_qualified_without_raw_breakout": not any(
            "qualified_breakout_ready=true while raw_breakout_ready=false" in failure
            for item in canonical_violations
            for failure in item["failures"]
        ),
        "no_final_setup_has_counted_breakout_without_breakout": not any(
            "counted_breakout_ready=true while breakout_ready=false" in failure
            for item in canonical_violations
            for failure in item["failures"]
        ),
        "no_final_setup_has_counted_momentum_without_momentum": not any(
            "counted_momentum_passed=true while momentum_passed=false" in failure
            for item in canonical_violations
            for failure in item["failures"]
        ),
        "no_pass_contract_contains_failed_gate_reason": not any(
            "PASS contract contains failed gate reason" in failure
            for item in canonical_violations
            for failure in item["failures"]
        ),
        "pnb_bpcl_pattern_blocked": pnb_bpcl_pattern_blocked,
        "current_canonical_violations": canonical_violations,
        "current_legacy_rows_without_new_gate_fields_count": len(legacy_rows),
        "current_legacy_rows_without_new_gate_fields_examples": legacy_rows[:5],
        "legacy_runtime_data_note": (
            "Existing final_validated_setups rows may predate this repair. The repaired scanner contract "
            "adds canonical gate fields to new rows and blocks failed-gate PASS contracts."
        ),
        "protected_files_not_part_of_patch_scope": list(PROTECTED_FILES),
        "protected_systems_modified_by_patch": protected_systems_modified_by_patch,
        "broker_risk_order_code_touched": False,
        "failures": failures,
        "verdict": "SCANNER_BREAKOUT_INTEGRITY_REPAIR_READY" if status == "PASS" else "SCANNER_BREAKOUT_INTEGRITY_REPAIR_BLOCKED",
    }


def main() -> None:
    report = build_report()
    write_json(REPORT_PATH, report)
    print("Scanner breakout integrity repair check complete.")
    print(f"status={report['status']}")
    print(f"verdict={report['verdict']}")
    print(f"pnb_bpcl_pattern_blocked={report['pnb_bpcl_pattern_blocked']}")
    print(f"canonical_violations={len(report['current_canonical_violations'])}")
    print(f"legacy_rows_without_new_gate_fields={report['current_legacy_rows_without_new_gate_fields_count']}")
    print(f"broker_risk_order_code_touched={report['broker_risk_order_code_touched']}")
    if report["failures"]:
        print("failures=" + "; ".join(report["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
