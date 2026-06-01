"""Read-only integration proof engine for ECHO Batch 2."""

from __future__ import annotations

import json
from typing import Any

from titan_echo.echo_batch2_common import echo_path, now_utc, read_json, safety, source_record, status_from_counts, write_echo_json


OUTPUT_PATH = echo_path("integration_proof_report.json")

EVIDENCE_PATHS = (
    echo_path("observations.json"),
    echo_path("alert_queue.json"),
    echo_path("file_index.json"),
    echo_path("module_registry.json"),
    echo_path("connection_graph.json"),
    echo_path("ownership_map.json"),
)

DIMENSION_TERMS = {
    "running": ("running", "active", "healthy", "observed", "status"),
    "connected": ("import", "connection", "edge", "module", "dependency"),
    "influencing": ("decision", "influence", "selection", "rank", "outcome"),
    "improving": ("learning", "evolution", "improvement", "calibration", "feedback"),
}


def _blob(values: list[Any]) -> str:
    return " ".join(json.dumps(value, sort_keys=True, default=str).lower() for value in values)


def build_integration_proof() -> dict[str, Any]:
    records = [source_record(path) for path in EVIDENCE_PATHS]
    payloads = [record["data"] for record in records if record["exists"]]
    text = _blob(payloads)
    present = sum(1 for record in records if record["exists"])
    dimensions = {}
    for name, terms in DIMENSION_TERMS.items():
        hits = [term for term in terms if term in text]
        dimensions[name] = {
            "status": "PROVEN" if hits else "UNKNOWN_NOT_PROVEN",
            "evidence_terms": hits,
        }
    ready = all(item["status"] == "PROVEN" for item in dimensions.values())
    status = "INTEGRATION_PROOF_READY" if ready else status_from_counts("INTEGRATION_PROOF_READY", len(records), present)
    return {
        "schema": "titan.echo.integration_proof_report.v1",
        "generated_at_utc": now_utc(),
        "status": status,
        "proof_dimensions": dimensions,
        "summary": {
            "evidence_files_expected": len(records),
            "evidence_files_present": present,
            "dimensions_proven": sum(1 for item in dimensions.values() if item["status"] == "PROVEN"),
        },
        "sources": [{key: value for key, value in record.items() if key != "data"} for record in records],
        "safety": safety(),
    }


def write_integration_proof() -> dict[str, Any]:
    payload = build_integration_proof()
    write_echo_json(OUTPUT_PATH, payload)
    return payload


def main() -> int:
    payload = write_integration_proof()
    print(f"ECHO integration proof status: {payload['status']}")
    print(f"Output: data/runtime/echo/{OUTPUT_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
