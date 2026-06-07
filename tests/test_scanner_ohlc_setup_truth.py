import json
from datetime import datetime, timedelta
from pathlib import Path

from utils.market_hours import IST

import runtime_truth
from dashboard_truth import build_dashboard_truth_consolidation
from scanner_ohlc_setup_truth import (
    build_scanner_ohlc_setup_truth,
    classify_ohlc_status,
    classify_scanner_status,
    classify_setup_engine_status,
)


NOW = datetime(2026, 6, 7, 12, 0, tzinfo=IST)


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_stale_ohlc_health_becomes_stale(tmp_path):
    path = tmp_path / "ohlc_health.json"
    _write_json(
        path,
        {
            "timestamp_ist": (NOW - timedelta(days=3)).isoformat(),
            "status": "PASS",
            "requested_count": 2,
            "valid_count": 2,
        },
    )

    status = classify_ohlc_status(path, now=NOW)

    assert status["status"] == "STALE"
    assert status["reason"] == "ohlc_health_timestamp_stale_or_missing"


def test_stale_scanner_status_becomes_stale(tmp_path):
    scanner = tmp_path / "scanner_status.json"
    final = tmp_path / "final_validated_setups.json"
    _write_json(
        scanner,
        {
            "timestamp_ist": (NOW - timedelta(hours=2)).isoformat(),
            "status": "FULL_RUNTIME_PIPELINE_COMPLETE",
            "stocks_checked": 50,
        },
    )
    _write_json(final, {"timestamp_ist": NOW.isoformat(), "setups": []})

    status = classify_scanner_status(scanner, final, now=NOW)

    assert status["status"] == "STALE"


def test_setup_marker_only_is_not_real_active(tmp_path):
    setup = tmp_path / "setup_engine_status.json"
    final = tmp_path / "final_validated_setups.json"
    _write_json(
        setup,
        {
            "timestamp_ist": NOW.isoformat(),
            "status": "MARKER_ONLY",
            "marker_only": True,
            "real_setup_engine_called": False,
        },
    )
    _write_json(final, {"timestamp_ist": NOW.isoformat(), "setups": []})

    status = classify_setup_engine_status(setup, final, now=NOW)

    assert status["status"] == "MARKER_ONLY"
    assert status["reason"] == "marker_only_status_not_runtime_liveness"


def test_missing_final_setups_is_not_active(tmp_path):
    setup = tmp_path / "setup_engine_status.json"
    final = tmp_path / "missing_final_validated_setups.json"
    _write_json(
        setup,
        {
            "timestamp_ist": NOW.isoformat(),
            "status": "OK",
            "real_setup_engine_called": True,
            "actual_setup_generation": True,
        },
    )

    status = classify_setup_engine_status(setup, final, now=NOW)

    assert status["status"] == "DISCONNECTED"
    assert status["final_setups_count"] is None


def test_fresh_diagnostic_can_clear_scanner_ohlc_setup_blockers(tmp_path):
    scanner = tmp_path / "scanner_status.json"
    ohlc = tmp_path / "ohlc_health.json"
    setup = tmp_path / "setup_engine_status.json"
    final = tmp_path / "final_validated_setups.json"
    output = tmp_path / "scanner_ohlc_setup_truth.json"
    _write_json(
        scanner,
        {
            "timestamp_ist": NOW.isoformat(),
            "status": "FULL_RUNTIME_PIPELINE_COMPLETE",
            "stocks_checked": 50,
            "passed_setups": 1,
            "real_scanner_called": True,
        },
    )
    _write_json(
        ohlc,
        {
            "timestamp_ist": NOW.isoformat(),
            "status": "PASS",
            "requested_count": 50,
            "valid_count": 50,
        },
    )
    _write_json(
        setup,
        {
            "timestamp_ist": NOW.isoformat(),
            "status": "OK",
            "real_setup_engine_called": True,
            "actual_setup_generation": True,
        },
    )
    _write_json(final, {"timestamp_ist": NOW.isoformat(), "setups": [{"symbol": "CANBK"}]})

    truth = build_scanner_ohlc_setup_truth(
        scanner_path=scanner,
        ohlc_path=ohlc,
        setup_path=setup,
        final_setups_path=final,
        output_path=output,
        now=NOW,
        write=True,
    )

    assert truth["scanner_status"]["status"] == "SCAN_LIVE"
    assert truth["ohlc_status"]["status"] == "LIVE"
    assert truth["setup_engine_status"]["status"] == "REAL_SETUP_ENGINE_CONNECTED"
    assert truth["restart_blocker"] is False


def test_dashboard_runtime_truth_uses_scanner_ohlc_setup_statuses(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime"
    scanner = runtime / "scanner_status.json"
    ohlc = runtime / "ohlc_health.json"
    setup = runtime / "setup_engine_status.json"
    final = runtime / "final_validated_setups.json"
    auth = runtime / "authoritative_runtime_truth.json"
    _write_json(scanner, {"timestamp_ist": (NOW - timedelta(hours=2)).isoformat(), "status": "OK"})
    _write_json(ohlc, {"timestamp_ist": (NOW - timedelta(days=2)).isoformat(), "status": "PASS"})
    _write_json(setup, {"timestamp_ist": NOW.isoformat(), "status": "MARKER_ONLY", "marker_only": True})
    _write_json(final, {"timestamp_ist": NOW.isoformat(), "setups": []})
    monkeypatch.setattr(runtime_truth, "RUNTIME_DIR", runtime)
    monkeypatch.setattr(runtime_truth, "AUTHORITATIVE_RUNTIME_TRUTH_PATH", auth)
    monkeypatch.setattr(runtime_truth, "SCANNER_STATUS_PATH", scanner)
    monkeypatch.setattr(runtime_truth, "OHLC_HEALTH_PATH", ohlc)
    monkeypatch.setattr(runtime_truth, "SETUP_ENGINE_STATUS_PATH", setup)
    monkeypatch.setattr(runtime_truth, "FINAL_VALIDATED_SETUPS_PATH", final)

    truth = runtime_truth.build_authoritative_runtime_truth(path=auth, now=NOW, write=True)
    dashboard = build_dashboard_truth_consolidation(
        truth,
        {"canonical_open_trade_count": 0, "legacy_open_rows_warning": False},
    )

    assert truth["components"]["scanner"]["status"] == "STALE"
    assert truth["components"]["ohlc_health"]["status"] == "STALE"
    assert truth["components"]["setup_engine"]["status"] == "MARKER_ONLY"
    assert dashboard["restart_allowed"] is False
    assert "scanner stale" in dashboard["restart_blockers"]
