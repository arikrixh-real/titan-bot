import pandas as pd
from datetime import datetime

from data.ohlc_health import validate_ohlc_df
from scanner_ohlc_setup_truth import classify_scanner_status, classify_setup_engine_status
from utils.market_hours import IST


def _df(latest):
    rows = []
    base = pd.Timestamp(latest) - pd.Timedelta(minutes=15 * 119)
    for index in range(120):
        rows.append(
            {
                "Datetime": (base + pd.Timedelta(minutes=15 * index)).isoformat(),
                "Open": 100 + index,
                "High": 101 + index,
                "Low": 99 + index,
                "Close": 100.5 + index,
                "Volume": 1000,
            }
        )
    return pd.DataFrame(rows)


def _write_json(path, payload):
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_friday_candle_valid_sunday():
    now = datetime(2026, 6, 7, 12, 0, tzinfo=IST)
    result = validate_ohlc_df(_df("2026-06-05T15:15:00+05:30"), "CANBK", now=now)

    assert result["status"] == "PASS"
    assert result["market_cache_status"] == "VALID_MARKET_CACHE"
    assert result["market_cache_reason"] == "VALID_WEEKEND_CACHE"


def test_weekend_cache_accepted():
    now = datetime(2026, 6, 7, 23, 0, tzinfo=IST)
    result = validate_ohlc_df(_df("2026-06-05T15:15:00+05:30"), "PNB", now=now)

    assert result["status"] == "PASS"
    assert "OHLC_STALE" not in str(result.get("reason"))


def test_holiday_cache_accepted():
    now = datetime(2026, 6, 8, 12, 0, tzinfo=IST)
    result = validate_ohlc_df(
        _df("2026-06-05T15:15:00+05:30"),
        "NIFTYBEES",
        now=now,
        holidays=["2026-06-08"],
    )

    assert result["status"] == "PASS"
    assert result["market_cache_reason"] == "VALID_CLOSED_MARKET_CACHE"


def test_stale_market_cache_rejected():
    now = datetime(2026, 6, 9, 12, 0, tzinfo=IST)
    result = validate_ohlc_df(_df("2026-06-05T15:15:00+05:30"), "CANBK", now=now)

    assert result["status"] == "FAIL"
    assert result["market_cache_status"] == "STALE"
    assert "LAST_VALID_SESSION:2026-06-09" in result["reason"]


def test_setup_diagnostic_skipped_not_unknown(tmp_path):
    setup = tmp_path / "setup_engine_status.json"
    final = tmp_path / "final_validated_setups.json"
    now = datetime(2026, 6, 7, 12, 0, tzinfo=IST)
    _write_json(setup, {"timestamp_ist": now.isoformat(), "status": "DIAGNOSTIC_SKIPPED"})
    _write_json(final, {"timestamp_ist": now.isoformat(), "setups": []})

    result = classify_setup_engine_status(setup, final, now=now)

    assert result["status"] == "DIAGNOSTIC_SKIPPED"
    assert result["restart_blocker"] is False


def test_scanner_idle_not_failed(tmp_path):
    scanner = tmp_path / "scanner_status.json"
    final = tmp_path / "final_validated_setups.json"
    now = datetime(2026, 6, 7, 12, 0, tzinfo=IST)
    _write_json(scanner, {"timestamp_ist": now.isoformat(), "status": "FULL_RUNTIME_PIPELINE_COMPLETE", "stocks_checked": 0})
    _write_json(final, {"timestamp_ist": now.isoformat(), "setups": []})

    result = classify_scanner_status(scanner, final, now=now)

    assert result["status"] == "SCAN_IDLE"
    assert result["restart_blocker"] is False


def test_stale_scanner_idle_outside_market_not_failed(tmp_path):
    scanner = tmp_path / "scanner_status.json"
    final = tmp_path / "final_validated_setups.json"
    now = datetime(2026, 6, 7, 12, 0, tzinfo=IST)
    _write_json(scanner, {"timestamp_ist": "2026-06-07T11:00:00+05:30", "status": "FULL_RUNTIME_PIPELINE_COMPLETE", "stocks_checked": 0})
    _write_json(final, {"timestamp_ist": now.isoformat(), "setups": []})

    result = classify_scanner_status(scanner, final, now=now)

    assert result["status"] == "SCAN_IDLE"
    assert result["restart_blocker"] is False


def test_stale_setup_diagnostic_skipped_not_unknown(tmp_path):
    setup = tmp_path / "setup_engine_status.json"
    final = tmp_path / "final_validated_setups.json"
    now = datetime(2026, 6, 7, 12, 0, tzinfo=IST)
    _write_json(setup, {"timestamp_ist": "2026-06-07T11:00:00+05:30", "status": "DIAGNOSTIC_SKIPPED"})
    _write_json(final, {"timestamp_ist": now.isoformat(), "setups": []})

    result = classify_setup_engine_status(setup, final, now=now)

    assert result["status"] == "DIAGNOSTIC_SKIPPED"
    assert result["restart_blocker"] is False
