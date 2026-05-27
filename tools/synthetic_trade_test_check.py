import csv
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.truth_gate import validate_trade_setup  # noqa: E402
from data.live_price import get_live_price_debug  # noqa: E402
from data.active_trade_store import (  # noqa: E402
    find_open_trade,
    load_open_trades,
    remove_test_trades,
)
from data.paper_journal import (  # noqa: E402
    FINAL_VALIDATED_SETUPS_PATH,
    PAPER_FLAG,
    maybe_write_paper_journal,
    timestamp_ist,
)
from data.price_cache import update_cached_price  # noqa: E402
from journal import outcome_tracker  # noqa: E402
from journal.outcome_tracker import OUTCOMES_CSV  # noqa: E402
from journal.outcome_tracker import LOCAL_TRADE_RESULTS_CSV  # noqa: E402


DIAGNOSTICS_PATH = PROJECT_ROOT / "data" / "runtime" / "synthetic_trade_test.json"
PRICE_CACHE_PATH = PROJECT_ROOT / "data" / "live_price_cache.json"
PRICE_CACHE_META_PATH = PROJECT_ROOT / "data" / "live_price_cache_meta.json"
SOURCE = "SYNTHETIC_PIPELINE_TEST"
SYMBOL = "RELIANCE"
SIDE = "LONG"


def _read_json(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _read_csv(path):
    try:
        path = Path(path)
        if not path.exists():
            return []
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except Exception:
        return []


def _write_csv(path, rows, fieldnames=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = []
    seen = set()
    for row in rows:
        for field in row.keys():
            if field not in seen:
                ordered.append(field)
                seen.add(field)
    if fieldnames:
        for field in reversed(list(fieldnames)):
            if field not in seen:
                ordered.insert(0, field)
                seen.add(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ordered)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in ordered})


def _csv_fieldnames(path):
    try:
        path = Path(path)
        if not path.exists():
            return []
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle).fieldnames or [])
    except Exception:
        return []


def _active_rows():
    return load_open_trades()


def _outcome_rows():
    return _read_csv(OUTCOMES_CSV)


def _trade_result_rows():
    return _read_csv(LOCAL_TRADE_RESULTS_CSV)


def _safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _bool_text(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _synthetic_open_rows(rows):
    return [
        row
        for row in rows
        if str(row.get("symbol") or "").upper() == SYMBOL
        and str(row.get("status") or "").upper() == "OPEN"
        and (_bool_text(row.get("test_trade")) or str(row.get("source") or "").upper() == SOURCE)
    ]


def _non_synthetic_open_rows(rows):
    return [
        row
        for row in rows
        if str(row.get("status") or "").upper() in {"OPEN", "ACTIVE", "LIVE"}
        and not (_bool_text(row.get("test_trade")) or str(row.get("source") or "").upper() == SOURCE)
    ]


def _remove_previous_synthetic_active_rows():
    result = remove_test_trades(symbol=SYMBOL, source=SOURCE)
    return int(result.get("removed") or 0)


def _latest_synthetic_outcome(trade_id):
    for row in reversed(_outcome_rows() + _trade_result_rows()):
        if str(row.get("trade_id") or "") == str(trade_id or ""):
            return row
    return None


def _remove_previous_synthetic_outcome_rows():
    removed = 0
    rows = _outcome_rows()
    kept = [
        row
        for row in rows
        if not (
            str(row.get("trade_id") or "").startswith(SOURCE)
            or _bool_text(row.get("test_trade"))
            or str(row.get("source") or "").upper() == SOURCE
        )
    ]
    if len(kept) != len(rows):
        _write_csv(OUTCOMES_CSV, kept, fieldnames=_csv_fieldnames(OUTCOMES_CSV))
        removed += len(rows) - len(kept)

    result_rows = _trade_result_rows()
    kept_results = [
        row
        for row in result_rows
        if not (
            str(row.get("trade_id") or "").startswith(SOURCE)
            or _bool_text(row.get("test_trade"))
            or str(row.get("source") or "").upper() == SOURCE
        )
    ]
    if len(kept_results) != len(result_rows):
        _write_csv(LOCAL_TRADE_RESULTS_CSV, kept_results, fieldnames=_csv_fieldnames(LOCAL_TRADE_RESULTS_CSV))
        removed += len(result_rows) - len(kept_results)
    return removed


def _backup_file(path):
    path = Path(path)
    return path.read_text(encoding="utf-8") if path.exists() else None


def _restore_file(path, content):
    path = Path(path)
    if content is None:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _current_price():
    price_debug = get_live_price_debug(SYMBOL, use_cache=True, debug=False)
    price = _safe_float(price_debug.get("ltp") or price_debug.get("price"))
    return price, price_debug


def _build_setup(entry):
    stop_loss = round(entry * 0.995, 4)
    target = round(entry * 1.01, 4)
    setup = {
        "symbol": SYMBOL,
        "side": "BUY",
        "entry": round(entry, 4),
        "stop_loss": stop_loss,
        "target": target,
        "rr": 2.0,
        "final_score": 100.0,
        "reason": "Isolated synthetic paper lifecycle validation",
        "source": SOURCE,
        "test_trade": True,
        "timestamp_ist": timestamp_ist(),
    }
    setup["contract_validation"] = validate_trade_setup(setup)
    return setup


def _write_synthetic_final_setup(setup):
    payload = {
        "timestamp_ist": timestamp_ist(),
        "scanner_cycle_id": f"{SOURCE}-{timestamp_ist()}",
        "validated_setup_count": 1,
        "setups": [setup],
        "reason": None,
        "source": SOURCE,
        "schema_version": 1,
    }
    _write_json(FINAL_VALIDATED_SETUPS_PATH, payload)
    return payload


def _run_real_paper_journal():
    previous_flag = os.environ.get(PAPER_FLAG)
    os.environ[PAPER_FLAG] = "true"
    try:
        return maybe_write_paper_journal(
            truth_gate_payload={
                "overall_status": "PASS",
                "market_data_status": {"status": "PASS"},
            },
            selector_payload={
                "selector_used": "SCORED_DYNAMIC_50",
                "fallback_active": False,
            },
            ohlc_status="PASS",
            scan_id=f"{SOURCE}-{timestamp_ist()}",
            within_trading_window=True,
            refresh_contract=True,
        )
    finally:
        if previous_flag is None:
            os.environ.pop(PAPER_FLAG, None)
        else:
            os.environ[PAPER_FLAG] = previous_flag


def _dashboard_visibility_ok(trade_id):
    rows = _active_rows() + _outcome_rows() + _trade_result_rows()
    return any(
        str(row.get("trade_id") or "") == str(trade_id or "")
        and (_bool_text(row.get("test_trade")) or str(row.get("source") or "").upper() == SOURCE)
        for row in rows
    )


def main():
    diagnostics = {
        "trade_written": False,
        "open_trade_detected": False,
        "outcome_tracker_detected": False,
        "live_price_loaded": False,
        "tp_logic_ok": False,
        "sl_logic_ok": False,
        "result_write_ok": False,
        "dashboard_visibility_ok": False,
        "broker_execution_disabled": True,
        "telegram_sent": False,
        "real_capital_used": False,
        "errors": [],
        "timestamp_ist": timestamp_ist(),
    }

    final_setup_backup = _backup_file(FINAL_VALIDATED_SETUPS_PATH)
    price_cache_backup = _backup_file(PRICE_CACHE_PATH)
    price_cache_meta_backup = _backup_file(PRICE_CACHE_META_PATH)
    previous_store_supabase_flag = os.environ.get("TITAN_ACTIVE_STORE_DISABLE_SUPABASE")

    try:
        os.environ["TITAN_ACTIVE_STORE_DISABLE_SUPABASE"] = "true"
        diagnostics["previous_synthetic_active_rows_removed"] = _remove_previous_synthetic_active_rows()
        stale_synthetic = find_open_trade(SYMBOL, source=SOURCE, test_trade=True)
        if stale_synthetic:
            diagnostics["errors"].append("SYNTHETIC_OPEN_TRADE_STILL_PRESENT_AFTER_CLEANUP")
            _write_json(DIAGNOSTICS_PATH, diagnostics)
            print(json.dumps(diagnostics, indent=2, sort_keys=True))
            return 1
        diagnostics["previous_synthetic_outcome_rows_removed"] = _remove_previous_synthetic_outcome_rows()
        existing_open = _non_synthetic_open_rows(_active_rows())
        if existing_open:
            diagnostics["errors"].append(
                f"NON_SYNTHETIC_OPEN_TRADES_PRESENT:{[row.get('symbol') for row in existing_open]}"
            )
            _write_json(DIAGNOSTICS_PATH, diagnostics)
            print(json.dumps(diagnostics, indent=2, sort_keys=True))
            return 1

        price, price_debug = _current_price()
        diagnostics["live_price_loaded"] = bool(price and price > 0)
        diagnostics["live_price_source"] = price_debug.get("source")
        diagnostics["live_price_status"] = price_debug.get("status")
        if not diagnostics["live_price_loaded"]:
            diagnostics["errors"].append(f"LIVE_PRICE_NOT_LOADED:{price_debug}")
            _write_json(DIAGNOSTICS_PATH, diagnostics)
            print(json.dumps(diagnostics, indent=2, sort_keys=True))
            return 1

        setup = _build_setup(price)
        diagnostics["entry"] = setup["entry"]
        diagnostics["stop_loss"] = setup["stop_loss"]
        diagnostics["target"] = setup["target"]
        diagnostics["rr"] = setup["rr"]
        if (setup.get("contract_validation") or {}).get("status") != "PASS":
            diagnostics["errors"].append(
                f"CONTRACT_VALIDATION_FAILED:{(setup.get('contract_validation') or {}).get('reason')}"
            )
            _write_json(DIAGNOSTICS_PATH, diagnostics)
            print(json.dumps(diagnostics, indent=2, sort_keys=True))
            return 1

        _write_synthetic_final_setup(setup)
        journal_payload = _run_real_paper_journal()
        diagnostics["paper_journal_status"] = journal_payload.get("last_write_status")
        diagnostics["paper_journal_written"] = journal_payload.get("written")
        diagnostics["paper_journal_duplicate_skipped"] = journal_payload.get("duplicate_skipped")

        synthetic_trade = find_open_trade(SYMBOL, source=SOURCE, test_trade=True)
        synthetic_rows = [synthetic_trade] if synthetic_trade else []
        diagnostics["trade_written"] = int(journal_payload.get("written") or 0) == 1 or bool(synthetic_rows)
        diagnostics["open_trade_detected"] = bool(synthetic_rows)
        if not synthetic_rows:
            diagnostics["errors"].append("SYNTHETIC_OPEN_TRADE_NOT_FOUND_AFTER_JOURNAL_WRITE")
            _write_json(DIAGNOSTICS_PATH, diagnostics)
            print(json.dumps(diagnostics, indent=2, sort_keys=True))
            return 1

        trade_row = synthetic_rows[-1]
        trade_id = trade_row.get("trade_id")
        diagnostics["trade_id"] = trade_id
        diagnostics["dashboard_visibility_ok"] = _dashboard_visibility_ok(trade_id)

        controlled_tp_price = round(setup["target"] * 1.001, 4)
        update_cached_price(SYMBOL, controlled_tp_price, source="SYNTHETIC_PIPELINE_TEST_CONTROLLED_TP")

        tp_outcome, _, _, _ = outcome_tracker._check_outcome(trade_row, controlled_tp_price)
        sl_outcome, _, _, _ = outcome_tracker._check_outcome(trade_row, round(setup["stop_loss"] * 0.999, 4))
        diagnostics["tp_logic_ok"] = tp_outcome == "TP"
        diagnostics["sl_logic_ok"] = sl_outcome == "SL"

        original_is_trade_window = outcome_tracker.is_trade_window
        original_trade_window_text = outcome_tracker.trade_window_text
        original_supabase = outcome_tracker.SUPABASE
        outcome_tracker.is_trade_window = lambda: True
        outcome_tracker.trade_window_text = lambda: "SYNTHETIC_PIPELINE_TEST_WINDOW"
        outcome_tracker.SUPABASE = None
        try:
            outcome_payload = outcome_tracker.track_trade_outcomes()
        finally:
            outcome_tracker.is_trade_window = original_is_trade_window
            outcome_tracker.trade_window_text = original_trade_window_text
            outcome_tracker.SUPABASE = original_supabase

        diagnostics["outcome_tracker_payload"] = outcome_payload
        diagnostics["outcome_tracker_detected"] = int(outcome_payload.get("checked") or 0) >= 1
        outcome_row = _latest_synthetic_outcome(trade_id)
        diagnostics["result_write_ok"] = bool(outcome_row and str(outcome_row.get("outcome") or "").upper() in {"TP", "SL"})
        diagnostics["closed_outcome"] = outcome_row.get("outcome") if outcome_row else None
        diagnostics["dashboard_visibility_ok"] = diagnostics["dashboard_visibility_ok"] or _dashboard_visibility_ok(trade_id)

    except Exception as exc:
        diagnostics["errors"].append(f"{type(exc).__name__}:{exc}")
    finally:
        if previous_store_supabase_flag is None:
            os.environ.pop("TITAN_ACTIVE_STORE_DISABLE_SUPABASE", None)
        else:
            os.environ["TITAN_ACTIVE_STORE_DISABLE_SUPABASE"] = previous_store_supabase_flag
        _restore_file(FINAL_VALIDATED_SETUPS_PATH, final_setup_backup)
        _restore_file(PRICE_CACHE_PATH, price_cache_backup)
        _restore_file(PRICE_CACHE_META_PATH, price_cache_meta_backup)
        diagnostics["price_cache_restored"] = True
        _write_json(DIAGNOSTICS_PATH, diagnostics)

    print(json.dumps(diagnostics, indent=2, sort_keys=True))
    return 0 if all(
        diagnostics.get(key)
        for key in [
            "trade_written",
            "open_trade_detected",
            "outcome_tracker_detected",
            "live_price_loaded",
            "tp_logic_ok",
            "sl_logic_ok",
            "result_write_ok",
            "dashboard_visibility_ok",
        ]
    ) and not diagnostics["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
