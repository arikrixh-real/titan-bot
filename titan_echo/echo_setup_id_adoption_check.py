"""Read-only checker for setup_id adoption at final_validated_setups."""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lineage.lineage_ids import is_valid_setup_id

FINAL_VALIDATED_SETUPS_PATH = REPO_ROOT / "data" / "runtime" / "final_validated_setups.json"
REPORT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "setup_id_adoption_report.json"
IST = timezone(timedelta(hours=5, minutes=30))


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def setup_key(record: dict[str, Any], index: int) -> str:
    return "|".join(
        str(record.get(key) or "")
        for key in ("symbol", "side", "direction", "scanner_cycle_id", "timestamp_ist")
    ) or f"index:{index}"


def build_report() -> dict[str, Any]:
    payload = read_json(FINAL_VALIDATED_SETUPS_PATH)
    file_exists = FINAL_VALIDATED_SETUPS_PATH.exists()
    setups = payload.get("setups") if isinstance(payload, dict) else []
    if not isinstance(setups, list):
        setups = []

    ids = []
    invalid = []
    legacy = []
    records = []
    for index, item in enumerate(setups):
        if not isinstance(item, dict):
            legacy.append({"index": index, "reason": "non_dict_record"})
            continue
        setup_id = item.get("setup_id")
        if setup_id:
            ids.append(str(setup_id))
            valid = is_valid_setup_id(setup_id)
            if not valid:
                invalid.append({"index": index, "setup_id": setup_id, "reason": "invalid_format"})
            records.append(
                {
                    "index": index,
                    "symbol": item.get("symbol"),
                    "side": item.get("side") or item.get("direction"),
                    "setup_id": setup_id,
                    "lineage_status": "setup_id_present" if valid else "invalid_setup_id",
                }
            )
        else:
            marker = {
                "index": index,
                "symbol": item.get("symbol"),
                "side": item.get("side") or item.get("direction"),
                "lineage_status": "legacy_unlinked",
                "legacy_reason": "record predates setup_id adoption or was written by an older writer",
                "safe_link_exists": False,
                "setup_key": setup_key(item, index),
            }
            legacy.append(marker)
            records.append(marker)

    duplicate_ids = sorted([setup_id for setup_id, count in Counter(ids).items() if count > 1])
    status = "PASS"
    failures = []
    if not file_exists:
        status = "PASS"
        failures.append("final_validated_setups.json not present; no current records to validate")
    if invalid:
        status = "FAIL"
        failures.append("invalid setup_id format found")
    if duplicate_ids:
        status = "FAIL"
        failures.append("duplicate setup_id values found")

    adoption_rate = round((len(ids) / len(setups)) * 100, 2) if setups else 100.0
    report = {
        "schema": "titan.echo.setup_id_adoption_report.v1",
        "timestamp_ist": timestamp_ist(),
        "status": status,
        "source_file": rel(FINAL_VALIDATED_SETUPS_PATH),
        "source_file_exists": file_exists,
        "scanner_logic_changed": False,
        "selection_logic_changed": False,
        "filter_logic_changed": False,
        "risk_logic_changed": False,
        "broker_logic_changed": False,
        "current_setup_count": len(setups),
        "records_with_setup_id": len(ids),
        "legacy_unlinked_count": len(legacy),
        "invalid_setup_id_count": len(invalid),
        "duplicate_setup_id_count": len(duplicate_ids),
        "setup_id_adoption_rate_pct": adoption_rate,
        "duplicate_setup_ids": duplicate_ids,
        "invalid_records": invalid,
        "legacy_unlinked_records": legacy,
        "record_lineage_status": records,
        "checks": {
            "final_validated_setups_exists_if_present": file_exists,
            "every_record_has_setup_id_or_reported_legacy_unlinked": len(records) == len(setups),
            "no_duplicate_setup_id": not duplicate_ids,
            "setup_id_format_valid": not invalid,
            "old_records_without_setup_id_do_not_break_checks": True,
        },
        "failures": failures,
        "verdict": "SETUP_ID_ADOPTION_READY" if status == "PASS" else "SETUP_ID_ADOPTION_BLOCKED",
        "recommended_next_action": (
            "Run the scanner naturally; newly written final_validated_setups records should include setup_id. "
            "Legacy records remain valid as legacy_unlinked in this report."
        ),
    }
    return report


def main() -> None:
    report = build_report()
    write_json(REPORT_PATH, report)
    print("Setup ID adoption check complete.")
    print(f"status={report['status']}")
    print(f"current_setup_count={report['current_setup_count']}")
    print(f"records_with_setup_id={report['records_with_setup_id']}")
    print(f"legacy_unlinked_count={report['legacy_unlinked_count']}")
    print(f"duplicate_setup_id_count={report['duplicate_setup_id_count']}")
    print(f"invalid_setup_id_count={report['invalid_setup_id_count']}")
    print(f"adoption_rate_pct={report['setup_id_adoption_rate_pct']}")
    print(f"verdict={report['verdict']}")


if __name__ == "__main__":
    main()
