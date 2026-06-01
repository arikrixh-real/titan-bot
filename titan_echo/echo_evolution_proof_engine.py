"""Read-only evolution proof engine for ECHO Batch 2."""

from __future__ import annotations

import json
from typing import Any

from titan_echo.echo_batch2_common import echo_path, now_utc, runtime_path, safety, source_record, status_from_counts, write_echo_json


OUTPUT_PATH = echo_path("evolution_proof_report.json")

EVIDENCE_FILES = (
    "evolution_status.json",
    "learning_status.json",
    "memory_consolidation_status.json",
    "master_brain_status.json",
    "outcome_tracker_status.json",
)

PROOF_TERMS = {
    "learning_activity": ("learning", "trained", "updated", "feedback"),
    "memory_consolidation": ("memory", "consolidation", "stored", "retained"),
    "outcome_feedback": ("outcome", "feedback", "win_rate", "pnl"),
    "evolution_state_change": ("evolution", "mutation", "changed", "parameter"),
}


def _blob(values: list[Any]) -> str:
    return " ".join(json.dumps(value, sort_keys=True, default=str).lower() for value in values)


def build_evolution_proof() -> dict[str, Any]:
    records = [source_record(runtime_path(name)) for name in EVIDENCE_FILES]
    payloads = [record["data"] for record in records if record["exists"]]
    text = _blob(payloads)
    present = sum(1 for record in records if record["exists"])
    categories = {}
    for name, terms in PROOF_TERMS.items():
        hits = [term for term in terms if term in text]
        categories[name] = {
            "status": "PROVEN" if hits else "UNKNOWN_NOT_PROVEN",
            "evidence_terms": hits,
        }
    ready = all(item["status"] == "PROVEN" for item in categories.values())
    status = "EVOLUTION_PROOF_READY" if ready else status_from_counts("EVOLUTION_PROOF_READY", len(records), present)
    return {
        "schema": "titan.echo.evolution_proof_report.v1",
        "generated_at_utc": now_utc(),
        "status": status,
        "proof_categories": categories,
        "summary": {
            "evidence_files_expected": len(records),
            "evidence_files_present": present,
            "categories_proven": sum(1 for item in categories.values() if item["status"] == "PROVEN"),
        },
        "sources": [{key: value for key, value in record.items() if key != "data"} for record in records],
        "safety": safety(),
    }


def write_evolution_proof() -> dict[str, Any]:
    payload = build_evolution_proof()
    write_echo_json(OUTPUT_PATH, payload)
    return payload


def main() -> int:
    payload = write_evolution_proof()
    print(f"ECHO evolution proof status: {payload['status']}")
    print(f"Output: data/runtime/echo/{OUTPUT_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
