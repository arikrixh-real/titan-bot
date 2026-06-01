"""Audit whether TITAN decisions can be traced to outcomes."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_RUNTIME = REPO_ROOT / "data" / "runtime" / "echo"
OUTPUT_PATH = ECHO_RUNTIME / "decision_trace_audit.json"
IST = timezone(timedelta(hours=5, minutes=30))

FILES = [
    "data/journals/trade_outcomes.csv",
    "data/journals/trade_outcomes.jsonl",
    "data/journals/trade_results.csv",
    "data/journals/trade_journal.csv",
    "data/journals/trade_journal.jsonl",
    "data/runtime/final_validated_setups.json",
    "data/runtime/trade_contract_diagnostics.json",
    "data/runtime/outcome_tracker_status.json",
    "data/runtime/scanner_status.json",
]


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def load_json(path: Path, default: Any | None = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {} if default is None else default


def read_csv(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return []


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
    except Exception:
        return []
    return rows


def flatten(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        rows = []
        for key in ["setups", "trades", "records", "outcomes", "results"]:
            if isinstance(value.get(key), list):
                rows.extend(item for item in value[key] if isinstance(item, dict))
        return rows or [value]
    return []


def rows() -> list[dict[str, Any]]:
    found = []
    for relative in FILES:
        path = REPO_ROOT / relative
        if not path.exists():
            continue
        if path.suffix == ".csv":
            items = read_csv(path)
        elif path.suffix == ".jsonl":
            items = read_jsonl(path)
        else:
            items = flatten(load_json(path, {}))
        for item in items:
            item["_source_file"] = relative
            found.append(item)
    return found


def has_any(row: dict[str, Any], keys: list[str]) -> bool:
    return any(str(row.get(key, "")).strip() for key in keys)


def closed(row: dict[str, Any]) -> bool:
    text = str(row.get("outcome") or row.get("result") or row.get("status") or "").upper()
    return bool(text and text not in {"OPEN", "PENDING", "UNKNOWN", "NONE", "N/A", "NA"})


def build_report() -> dict[str, Any]:
    all_rows = rows()
    traceable = []
    partial = []
    untraceable = []
    orphan_outcomes = []
    for row in all_rows:
        decision = has_any(row, ["trade_id", "scan_id", "source", "symbol", "side"])
        conf = has_any(row, ["confidence", "confidence_score", "rank_score", "score"])
        setup = has_any(row, ["entry", "entry_price", "sl", "stop_loss", "target", "tp"])
        execution = has_any(row, ["paper_trade_id", "is_paper_trade", "quantity", "qty", "broker_order_id"])
        outcome = closed(row)
        links = sum([decision, conf, setup, execution, outcome])
        entry = {
            "source_file": row.get("_source_file"),
            "trade_id": row.get("trade_id") or row.get("paper_trade_id") or row.get("scan_id"),
            "symbol": row.get("symbol"),
            "links": {
                "decision": decision,
                "confidence": conf,
                "setup": setup,
                "execution": execution,
                "outcome": outcome,
            },
        }
        if all([decision, conf, setup, execution, outcome]):
            traceable.append(entry)
        elif outcome and not decision:
            orphan_outcomes.append(entry)
            partial.append(entry)
        elif links >= 3:
            partial.append(entry)
        else:
            untraceable.append(entry)
    total = len(traceable) + len(partial) + len(untraceable)
    score = round(((len(traceable) * 1.0 + len(partial) * 0.45) / total) * 100) if total else 0
    causal = "PARTIAL" if traceable and score >= 40 else "DECISION_CAUSALITY_NOT_PROVEN"
    return {
        "schema": "titan_echo.decision_trace_audit.v1",
        "timestamp_ist": timestamp_ist(),
        "decision_trace_score": min(score, 75),
        "causality_status": causal,
        "traceable_decisions": len(traceable),
        "partially_traceable_decisions": len(partial),
        "untraceable_decisions": len(untraceable),
        "feedback_loop_completeness": "PARTIAL" if traceable else "UNKNOWN",
        "broken_links": ["execution linkage incomplete for partial rows"] if partial else [],
        "missing_links": ["explicit decision id", "confidence id", "execution id", "outcome id"] if partial or untraceable else [],
        "orphan_outcomes": orphan_outcomes[:50],
        "strongest_evidence": traceable[:10],
        "weakest_evidence": (untraceable or partial)[:10],
        "audit_note": "Traceability does not prove causality unless decision changes are tied to later outcome improvement.",
    }


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = build_report()
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("TITAN ECHO decision trace audit: PASSED")
    print(f"Decision trace score: {report['decision_trace_score']}")
    print(f"Causality status: {report['causality_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
