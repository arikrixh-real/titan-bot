import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

from titan_echo import echo_trade_diagnostics
from titan_echo import echo_truth_refresh_layer as truth


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_csv(path: Path, fields: list[str], rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _patch_truth_paths(monkeypatch, tmp_path):
    runtime = tmp_path / "data" / "runtime"
    journals = tmp_path / "data" / "journals"
    monkeypatch.setattr(truth, "RUNTIME_DIR", runtime)
    monkeypatch.setattr(truth, "JOURNAL_DIR", journals)
    monkeypatch.setattr(truth, "AUTHORITATIVE_RUNTIME_TRUTH_PATH", runtime / "authoritative_runtime_truth.json")
    monkeypatch.setattr(truth, "COMPONENT_FRESHNESS_SUMMARY_PATH", runtime / "component_freshness_summary.json")
    monkeypatch.setattr(truth, "GIT_CLEANLINESS_PATH", runtime / "git_cleanliness.json")
    monkeypatch.setattr(truth, "RUNTIME_ERROR_SUMMARY_PATH", runtime / "runtime_error_summary.json")
    monkeypatch.setattr(truth, "DAEMON_ERRORS_LOG_PATH", runtime / "daemon_errors.jsonl")
    monkeypatch.setattr(truth, "ACTIVE_TRADES_CSV", journals / "active_trades.csv")
    monkeypatch.setattr(truth, "TRADE_OUTCOMES_CSV", journals / "trade_outcomes.csv")
    return runtime, journals


def _patch_trade_paths(monkeypatch, runtime, journals):
    monkeypatch.setattr(echo_trade_diagnostics, "RUNTIME_DIR", runtime)
    monkeypatch.setattr(echo_trade_diagnostics, "JOURNAL_DIR", journals)
    monkeypatch.setattr(echo_trade_diagnostics, "FILTER_DIAGNOSTICS_PATH", runtime / "filter_engine_diagnostics.json")
    monkeypatch.setattr(echo_trade_diagnostics, "SCANNER_STATUS_PATH", runtime / "scanner_status.json")
    monkeypatch.setattr(echo_trade_diagnostics, "TRADE_CONTRACT_DIAGNOSTICS_PATH", runtime / "trade_contract_diagnostics.json")
    monkeypatch.setattr(echo_trade_diagnostics, "TRADE_JOURNAL_DIAGNOSTICS_PATH", runtime / "trade_journal_diagnostics.json")
    monkeypatch.setattr(echo_trade_diagnostics, "OUTCOME_TRACKER_DIAGNOSTICS_PATH", runtime / "outcome_tracker_diagnostics.json")
    monkeypatch.setattr(echo_trade_diagnostics, "TRADE_JOURNAL_CSV", journals / "trade_journal.csv")
    monkeypatch.setattr(echo_trade_diagnostics, "ACTIVE_TRADES_CSV", journals / "active_trades.csv")
    monkeypatch.setattr(echo_trade_diagnostics, "TRADE_OUTCOMES_CSV", journals / "trade_outcomes.csv")


def test_stale_runtime_marked_stale(tmp_path, monkeypatch):
    runtime, _ = _patch_truth_paths(monkeypatch, tmp_path)
    now = datetime(2026, 6, 6, 12, 0, tzinfo=truth.IST)
    stale_time = (now - timedelta(hours=2)).isoformat()
    artifact = runtime / "runtime_status.json"
    _write_json(artifact, {"timestamp_ist": stale_time, "status": "OK"})

    payload = truth.build_component_freshness_summary(
        now=now,
        artifacts={"runtime_status": artifact},
        stale_after_minutes=30,
    )

    assert payload["overall_status"] == "STALE"
    assert payload["components"][0]["freshness_status"] == "STALE"


def test_active_trades_header_only_reports_zero(tmp_path, monkeypatch):
    runtime, journals = _patch_truth_paths(monkeypatch, tmp_path)
    _patch_trade_paths(monkeypatch, runtime, journals)
    fields = ["trade_id", "symbol", "side", "entry", "sl", "target", "status", "outcome"]
    _write_csv(journals / "active_trades.csv", fields, [])
    _write_csv(journals / "trade_outcomes.csv", ["trade_id", "symbol", "outcome"], [])

    payload = echo_trade_diagnostics.build_outcome_tracker_diagnostics()

    assert payload["active_trade_count"] == 0
    assert payload["open_trade_count"] == 0
    assert payload["monitored_count"] == 0


def test_diagnostics_cannot_report_trades_not_in_csv(tmp_path, monkeypatch):
    runtime, journals = _patch_truth_paths(monkeypatch, tmp_path)
    _patch_trade_paths(monkeypatch, runtime, journals)
    _write_json(runtime / "outcome_tracker_diagnostics.json", {"active_trade_ids_sample": ["FAKE_STALE_ID"]})
    _write_csv(
        journals / "active_trades.csv",
        ["trade_id", "symbol", "side", "entry", "sl", "target", "status"],
        [{"trade_id": "CSV_TRADE_1", "symbol": "ABC", "side": "BUY", "entry": "10", "sl": "9", "target": "12", "status": "OPEN"}],
    )
    _write_csv(journals / "trade_outcomes.csv", ["trade_id", "symbol", "outcome"], [])

    outcome = echo_trade_diagnostics.build_outcome_tracker_diagnostics()
    csv_truth = truth.build_trade_csv_truth(
        active_trades_path=journals / "active_trades.csv",
        outcomes_path=journals / "trade_outcomes.csv",
    )

    assert outcome["active_trade_count"] == 1
    assert outcome["active_trade_ids_sample"] == ["CSV_TRADE_1"]
    assert "FAKE_STALE_ID" not in outcome["active_trade_ids_sample"]
    assert csv_truth["active_trade_ids_sample"] == ["CSV_TRADE_1"]


def test_missing_logs_reports_unknown(tmp_path, monkeypatch):
    runtime, _ = _patch_truth_paths(monkeypatch, tmp_path)
    missing_log = runtime / "missing_daemon_errors.jsonl"

    payload = truth.build_runtime_error_summary(log_path=missing_log)

    assert payload["status"] == "UNKNOWN"
    assert payload["reason"] == "MISSING_ERROR_LOG"
