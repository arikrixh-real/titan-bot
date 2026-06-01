"""Read-only ECHO observer for selected TITAN runtime evidence."""

from __future__ import annotations

from typing import Any

from titan_echo.echo_batch2_common import echo_path, now_utc, runtime_path, safety, source_record, status_from_counts, write_echo_json


OUTPUT_PATH = echo_path("observations.json")

EVIDENCE_FILES = (
    "worker_health.json",
    "scanner_status.json",
    "master_brain_status.json",
    "outcome_tracker_status.json",
    "dashboard_sync_status.json",
    "ohlc_refresh_status.json",
    "titan_runtime_status.json",
    "runtime_selector_status.json",
    "filter_engine_diagnostics.json",
    "trade_contract_diagnostics.json",
    "trade_journal_diagnostics.json",
    "outcome_tracker_diagnostics.json",
)

ISSUE_TERMS = ("fail", "error", "critical", "down", "stale", "degraded", "missing")


def _extract_signals(data: Any) -> list[str]:
    signals: list[str] = []

    def walk(value: Any, prefix: str = "") -> None:
        if len(signals) >= 20:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                child_key = f"{prefix}.{key}" if prefix else str(key)
                if str(key).lower() in {"status", "state", "health", "result", "error", "message"} and not isinstance(child, (dict, list)):
                    signals.append(f"{child_key}={child}")
                walk(child, child_key)
        elif isinstance(value, list):
            for index, child in enumerate(value[:10]):
                walk(child, f"{prefix}[{index}]")

    walk(data)
    return signals


def build_observations() -> dict[str, Any]:
    sources = [source_record(runtime_path(name)) for name in EVIDENCE_FILES]
    present = sum(1 for item in sources if item["exists"])
    errors = sum(1 for item in sources if item["error"] not in {None, "missing"})
    observations = []
    for item in sources:
        if not item["exists"]:
            observations.append({"source": item["path"], "severity": "UNKNOWN", "finding": "Evidence file missing.", "signals": []})
            continue
        signals = _extract_signals(item["data"])
        signal_text = " ".join(signals).lower()
        severity = "ISSUE_DETECTED" if any(term in signal_text for term in ISSUE_TERMS) else "OBSERVED"
        observations.append({"source": item["path"], "severity": severity, "finding": "Evidence file read.", "signals": signals})
    return {
        "schema": "titan.echo.observations.v1",
        "generated_at_utc": now_utc(),
        "status": status_from_counts("OBSERVATION_READY", len(EVIDENCE_FILES), present, errors),
        "summary": {
            "files_expected": len(EVIDENCE_FILES),
            "files_present": present,
            "files_missing": len(EVIDENCE_FILES) - present,
            "files_with_read_errors": errors,
            "issues_detected": sum(1 for item in observations if item["severity"] == "ISSUE_DETECTED"),
        },
        "sources": [{key: value for key, value in item.items() if key != "data"} for item in sources],
        "observations": observations,
        "safety": safety(),
    }


def write_observations() -> dict[str, Any]:
    payload = build_observations()
    write_echo_json(OUTPUT_PATH, payload)
    return payload


def main() -> int:
    payload = write_observations()
    print(f"ECHO observer status: {payload['status']}")
    print(f"Output: data/runtime/echo/{OUTPUT_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
