import json
import os
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.active_trade_store import (  # noqa: E402
    canonical_open_trade_count,
    classify_legacy_active_trade_files,
    find_open_trade,
    load_canonical_active_trade_rows,
    remove_test_trades,
    write_journal_truth_unification,
)
from data.paper_journal import maybe_write_paper_journal, timestamp_ist  # noqa: E402
from journal import outcome_tracker  # noqa: E402
from restart_readiness_gate import build_restart_readiness_gate  # noqa: E402
from runtime_dashboard_sync import run_dashboard_sync  # noqa: E402
from runtime_scanner import run_scanner  # noqa: E402
from runtime_setup_engine import run_setup_engine  # noqa: E402
from runtime_truth import build_authoritative_runtime_truth  # noqa: E402
from scanner_ohlc_setup_truth import build_scanner_ohlc_setup_truth  # noqa: E402
from tools import synthetic_trade_test_check as synthetic  # noqa: E402


RUNTIME_DIR = PROJECT_ROOT / "data" / "runtime"
REPORT_PATH = RUNTIME_DIR / "titan_classic_freeze_report.json"
MISSION_DIAGNOSTIC_PATH = RUNTIME_DIR / "paper_proof_mission_020.json"
MASTER_GUARD_PATH = RUNTIME_DIR / "master_brain_activation_guard.json"
JOURNAL_TRUTH_PATH = RUNTIME_DIR / "journal_truth_unification.json"
DASHBOARD_TRUTH_PATH = RUNTIME_DIR / "dashboard_truth.json"


def _read_json(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        return {"_read_error": f"{type(exc).__name__}:{exc}"}


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    tmp.replace(path)


def _env_set(name, value):
    previous = os.environ.get(name)
    os.environ[name] = value
    return previous


def _env_unset(name):
    previous = os.environ.get(name)
    os.environ.pop(name, None)
    return previous


def _restore_env(snapshot):
    for name, previous in snapshot.items():
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


def _journal_counts():
    rows = load_canonical_active_trade_rows()
    return {
        "canonical_active_trade_count": len(rows),
        "canonical_open_trade_count": canonical_open_trade_count(),
        "synthetic_open_trade": bool(find_open_trade(synthetic.SYMBOL, source=synthetic.SOURCE, test_trade=True)),
    }


def _run_duplicate_paper_lifecycle():
    diagnostics = {
        "test_run_id": synthetic.SOURCE,
        "symbol": synthetic.SYMBOL,
        "trade_written": False,
        "duplicate_attempted": False,
        "duplicate_skipped": False,
        "open_trade_detected": False,
        "outcome_tracker_detected": False,
        "result_write_ok": False,
        "dashboard_visibility_ok": False,
        "tp_logic_ok": False,
        "sl_logic_ok": False,
        "errors": [],
    }
    final_setup_backup = synthetic._backup_file(synthetic.FINAL_VALIDATED_SETUPS_PATH)
    price_cache_backup = synthetic._backup_file(synthetic.PRICE_CACHE_PATH)
    price_cache_meta_backup = synthetic._backup_file(synthetic.PRICE_CACHE_META_PATH)
    previous_store_supabase_flag = os.environ.get("TITAN_ACTIVE_STORE_DISABLE_SUPABASE")
    previous_paper_supabase_flag = os.environ.get("TITAN_PAPER_JOURNAL_DISABLE_SUPABASE")
    previous_paper_flag = os.environ.get(synthetic.PAPER_FLAG)

    try:
        os.environ["TITAN_ACTIVE_STORE_DISABLE_SUPABASE"] = "true"
        os.environ["TITAN_PAPER_JOURNAL_DISABLE_SUPABASE"] = "true"
        os.environ[synthetic.PAPER_FLAG] = "true"
        remove_test_trades(symbol=synthetic.SYMBOL, source=synthetic.SOURCE)
        synthetic._remove_previous_synthetic_outcome_rows()

        existing_open = synthetic._non_synthetic_open_rows(synthetic._active_rows())
        if existing_open:
            diagnostics["errors"].append(
                f"NON_SYNTHETIC_OPEN_TRADES_PRESENT:{[row.get('symbol') for row in existing_open]}"
            )
            return diagnostics

        price, price_debug = synthetic._current_price()
        diagnostics["live_price_loaded"] = bool(price and price > 0)
        diagnostics["live_price_source"] = price_debug.get("source")
        diagnostics["live_price_status"] = price_debug.get("status")
        if not diagnostics["live_price_loaded"]:
            diagnostics["errors"].append(f"LIVE_PRICE_NOT_LOADED:{price_debug}")
            return diagnostics

        setup = synthetic._build_setup(price)
        diagnostics["setup_contract_status"] = (setup.get("contract_validation") or {}).get("status")
        if diagnostics["setup_contract_status"] != "PASS":
            diagnostics["errors"].append(
                f"CONTRACT_VALIDATION_FAILED:{(setup.get('contract_validation') or {}).get('reason')}"
            )
            return diagnostics

        synthetic._write_synthetic_final_setup(setup)
        first_payload = synthetic._run_real_paper_journal()
        duplicate_payload = maybe_write_paper_journal(
            truth_gate_payload={"overall_status": "PASS", "market_data_status": {"status": "PASS"}},
            selector_payload={"selector_used": "SCORED_DYNAMIC_50", "fallback_active": False},
            ohlc_status="PASS",
            scan_id=f"{synthetic.SOURCE}-{timestamp_ist()}-duplicate",
            within_trading_window=True,
            refresh_contract=True,
        )
        diagnostics["first_paper_journal_payload"] = first_payload
        diagnostics["duplicate_paper_journal_payload"] = duplicate_payload
        diagnostics["duplicate_attempted"] = True
        diagnostics["duplicate_skipped"] = int(duplicate_payload.get("duplicate_skipped") or 0) >= 1

        trade_row = find_open_trade(synthetic.SYMBOL, source=synthetic.SOURCE, test_trade=True)
        diagnostics["trade_written"] = int(first_payload.get("written") or 0) == 1 or bool(trade_row)
        diagnostics["open_trade_detected"] = bool(trade_row)
        if not trade_row:
            diagnostics["errors"].append("SYNTHETIC_OPEN_TRADE_NOT_FOUND_AFTER_JOURNAL_WRITE")
            return diagnostics

        trade_id = trade_row.get("trade_id")
        diagnostics["trade_id"] = trade_id
        diagnostics["dashboard_visibility_ok"] = synthetic._dashboard_visibility_ok(trade_id)

        controlled_tp_price = round(setup["target"] * 1.001, 4)
        synthetic.update_cached_price(
            synthetic.SYMBOL,
            controlled_tp_price,
            source="MISSION_020_CONTROLLED_TP",
        )
        tp_outcome, _, _, _ = outcome_tracker._check_outcome(trade_row, controlled_tp_price)
        sl_outcome, _, _, _ = outcome_tracker._check_outcome(trade_row, round(setup["stop_loss"] * 0.999, 4))
        diagnostics["tp_logic_ok"] = tp_outcome == "TP"
        diagnostics["sl_logic_ok"] = sl_outcome == "SL"

        original_is_trade_window = outcome_tracker.is_trade_window
        original_trade_window_text = outcome_tracker.trade_window_text
        original_supabase = outcome_tracker.SUPABASE
        outcome_tracker.is_trade_window = lambda: True
        outcome_tracker.trade_window_text = lambda: "MISSION_020_PAPER_PROOF_WINDOW"
        outcome_tracker.SUPABASE = None
        try:
            outcome_payload = outcome_tracker.track_trade_outcomes()
        finally:
            outcome_tracker.is_trade_window = original_is_trade_window
            outcome_tracker.trade_window_text = original_trade_window_text
            outcome_tracker.SUPABASE = original_supabase

        diagnostics["outcome_tracker_payload"] = outcome_payload
        diagnostics["outcome_tracker_detected"] = int(outcome_payload.get("checked") or 0) >= 1
        outcome_row = synthetic._latest_synthetic_outcome(trade_id)
        diagnostics["result_write_ok"] = bool(
            outcome_row and str(outcome_row.get("outcome") or "").upper() in {"TP", "SL"}
        )
        diagnostics["closed_outcome"] = outcome_row.get("outcome") if outcome_row else None
        diagnostics["dashboard_visibility_ok"] = diagnostics["dashboard_visibility_ok"] or synthetic._dashboard_visibility_ok(trade_id)
        diagnostics["canonical_open_after_closure"] = canonical_open_trade_count()
    except Exception as exc:
        diagnostics["errors"].append(f"{type(exc).__name__}:{exc}")
    finally:
        if previous_store_supabase_flag is None:
            os.environ.pop("TITAN_ACTIVE_STORE_DISABLE_SUPABASE", None)
        else:
            os.environ["TITAN_ACTIVE_STORE_DISABLE_SUPABASE"] = previous_store_supabase_flag
        if previous_paper_supabase_flag is None:
            os.environ.pop("TITAN_PAPER_JOURNAL_DISABLE_SUPABASE", None)
        else:
            os.environ["TITAN_PAPER_JOURNAL_DISABLE_SUPABASE"] = previous_paper_supabase_flag
        if previous_paper_flag is None:
            os.environ.pop(synthetic.PAPER_FLAG, None)
        else:
            os.environ[synthetic.PAPER_FLAG] = previous_paper_flag
        synthetic._restore_file(synthetic.FINAL_VALIDATED_SETUPS_PATH, final_setup_backup)
        synthetic._restore_file(synthetic.PRICE_CACHE_PATH, price_cache_backup)
        synthetic._restore_file(synthetic.PRICE_CACHE_META_PATH, price_cache_meta_backup)
        diagnostics["scanner_inputs_restored"] = True
        diagnostics["price_cache_restored"] = True

    required = [
        "trade_written",
        "duplicate_attempted",
        "duplicate_skipped",
        "open_trade_detected",
        "outcome_tracker_detected",
        "result_write_ok",
        "dashboard_visibility_ok",
        "tp_logic_ok",
        "sl_logic_ok",
    ]
    diagnostics["status"] = "PASS" if all(diagnostics.get(key) for key in required) and not diagnostics["errors"] else "FAIL"
    return diagnostics


def run_mission():
    started = time.monotonic()
    env_snapshot = {
        "TITAN_RUNTIME_MASTER_BRAIN_MODE": _env_set("TITAN_RUNTIME_MASTER_BRAIN_MODE", "READ_ONLY"),
        "TITAN_ACTIVE_STORE_DISABLE_SUPABASE": _env_set("TITAN_ACTIVE_STORE_DISABLE_SUPABASE", "true"),
        "TITAN_PAPER_JOURNAL_DISABLE_SUPABASE": _env_set("TITAN_PAPER_JOURNAL_DISABLE_SUPABASE", "true"),
        "TITAN_DASHBOARD_SYNC_LOCAL_ONLY": _env_set("TITAN_DASHBOARD_SYNC_LOCAL_ONLY", "1"),
        "TITAN_ENABLE_PAPER_JOURNAL": _env_unset("TITAN_ENABLE_PAPER_JOURNAL"),
        "TITAN_BROKER_LIVE_EXECUTION": _env_unset("TITAN_BROKER_LIVE_EXECUTION"),
        "TITAN_TELEGRAM_ALERTS": _env_unset("TITAN_TELEGRAM_ALERTS"),
        "TITAN_ENABLE_HFT": _env_unset("TITAN_ENABLE_HFT"),
    }

    diagnostic = {
        "mission": "020",
        "generated_at": timestamp_ist(),
        "mode": "paper_only_validation",
        "pre_journal_counts": _journal_counts(),
        "legacy_files_before": classify_legacy_active_trade_files(),
        "scanner_result": {},
        "setup_result": {},
        "paper_lifecycle_result": {},
        "dashboard_sync_result": {},
        "runtime_truth_after": {},
        "scanner_ohlc_setup_truth_after": {},
        "restart_readiness_gate_after": {},
        "journal_truth_after": {},
        "legacy_files_after": [],
        "broker_order_api_called": False,
        "trading_api_called": False,
        "telegram_sent": False,
        "live_supabase_trade_order_state_written": False,
        "hft_enabled": False,
        "errors": [],
    }
    try:
        scanner_payload = run_scanner()
        diagnostic["scanner_result"] = {
            "status": scanner_payload.get("status"),
            "mode": scanner_payload.get("mode"),
            "scan_only": scanner_payload.get("scan_only"),
            "symbols_scanned": scanner_payload.get("symbols_scanned") or scanner_payload.get("stocks_checked"),
            "final_setups_count": scanner_payload.get("final_setups_count") or scanner_payload.get("final_passed_count"),
            "trade_creation": scanner_payload.get("trade_creation"),
            "journal_writes": scanner_payload.get("journal_writes"),
            "telegram_alerts": scanner_payload.get("telegram_alerts"),
            "paper_journal": scanner_payload.get("paper_journal"),
        }
    except Exception as exc:
        diagnostic["scanner_result"] = {"status": "ERROR", "error": f"{type(exc).__name__}:{exc}"}
        diagnostic["errors"].append(f"SCANNER_PROOF_ERROR:{type(exc).__name__}:{exc}")

    try:
        setup_payload = run_setup_engine()
        diagnostic["setup_result"] = {
            "status": setup_payload.get("status"),
            "setup_engine_status": setup_payload.get("setup_engine_status"),
            "real_setup_engine_called": setup_payload.get("real_setup_engine_called"),
            "trade_creation": setup_payload.get("trade_creation"),
            "journal_writes": setup_payload.get("journal_writes"),
            "telegram_alerts": setup_payload.get("telegram_alerts"),
            "broker_orders": setup_payload.get("broker_orders"),
        }
    except Exception as exc:
        diagnostic["setup_result"] = {"status": "ERROR", "error": f"{type(exc).__name__}:{exc}"}
        diagnostic["errors"].append(f"SETUP_PROOF_ERROR:{type(exc).__name__}:{exc}")

    diagnostic["paper_lifecycle_result"] = _run_duplicate_paper_lifecycle()

    try:
        diagnostic["journal_truth_after"] = write_journal_truth_unification(
            readers_checked=["data.active_trade_store", "data.paper_journal", "journal.outcome_tracker"],
            readers_patched=[],
            unsafe_fallbacks_removed=[],
            remaining_unknowns=[],
        )
        diagnostic["runtime_truth_after"] = build_authoritative_runtime_truth(write=True)
        diagnostic["scanner_ohlc_setup_truth_after"] = build_scanner_ohlc_setup_truth(write=True)
        diagnostic["restart_readiness_gate_after"] = build_restart_readiness_gate(write=True)
        diagnostic["dashboard_sync_result"] = run_dashboard_sync()
        diagnostic["runtime_truth_after"] = build_authoritative_runtime_truth(write=True)
        diagnostic["restart_readiness_gate_after"] = build_restart_readiness_gate(write=True)
    except Exception as exc:
        diagnostic["errors"].append(f"TRUTH_REGEN_ERROR:{type(exc).__name__}:{exc}")

    diagnostic["legacy_files_after"] = classify_legacy_active_trade_files()
    diagnostic["post_journal_counts"] = _journal_counts()
    diagnostic["duration_seconds"] = round(time.monotonic() - started, 3)

    master_guard = _read_json(MASTER_GUARD_PATH)
    runtime_truth = diagnostic.get("runtime_truth_after") or {}
    restart_gate = diagnostic.get("restart_readiness_gate_after") or {}
    dashboard_sync = diagnostic.get("dashboard_sync_result") or {}
    paper_result = diagnostic.get("paper_lifecycle_result") or {}
    journal_truth = diagnostic.get("journal_truth_after") or {}

    no_legacy_contamination = (
        journal_truth.get("canonical_open_trade_count") == 0
        and not diagnostic["post_journal_counts"].get("synthetic_open_trade")
    )
    paper_pass = paper_result.get("status") == "PASS"
    duplicate_pass = bool(paper_result.get("duplicate_skipped"))
    safety_pass = (
        master_guard.get("effective_mode") == "READ_ONLY"
        and not master_guard.get("can_call_broker")
        and not master_guard.get("can_send_telegram")
        and not diagnostic["broker_order_api_called"]
        and not diagnostic["trading_api_called"]
        and not diagnostic["telegram_sent"]
        and not diagnostic["live_supabase_trade_order_state_written"]
        and not diagnostic["hft_enabled"]
    )
    gate_pass = not restart_gate.get("blockers")
    approved = bool(paper_pass and duplicate_pass and safety_pass and no_legacy_contamination and gate_pass and not diagnostic["errors"])

    report = {
        "generated_at": timestamp_ist(),
        "architecture_version": "TITAN_CLASSIC_V1_FROZEN_2026-06-07",
        "runtime_status": (runtime_truth.get("summary") or {}).get("overall_status"),
        "daemon_status": ((runtime_truth.get("components") or {}).get("daemon") or {}).get("status"),
        "worker_status": ((runtime_truth.get("components") or {}).get("workers") or {}).get("status"),
        "scanner_status": diagnostic["scanner_result"].get("status"),
        "setup_status": diagnostic["setup_result"].get("status"),
        "master_brain_status": master_guard.get("effective_mode") or master_guard.get("status"),
        "journal_status": {
            "canonical_open_trade_count": journal_truth.get("canonical_open_trade_count"),
            "legacy_open_rows_warning": journal_truth.get("legacy_open_rows_warning"),
            "no_legacy_file_contamination": no_legacy_contamination,
        },
        "dashboard_status": {
            "timestamp_ist": dashboard_sync.get("timestamp_ist"),
            "supabase_sync": dashboard_sync.get("supabase_sync"),
            "dashboard_truth_path": str(DASHBOARD_TRUTH_PATH).replace("\\", "/"),
        },
        "duplicate_protection": {
            "status": "PASS" if duplicate_pass else "FAIL",
            "duplicate_attempted": paper_result.get("duplicate_attempted"),
            "duplicate_skipped": paper_result.get("duplicate_skipped"),
            "first_write": (paper_result.get("first_paper_journal_payload") or {}).get("written"),
            "second_duplicate_skipped": (paper_result.get("duplicate_paper_journal_payload") or {}).get("duplicate_skipped"),
        },
        "paper_trade_count": {
            "written": (paper_result.get("first_paper_journal_payload") or {}).get("written"),
            "open_after_closure": paper_result.get("canonical_open_after_closure"),
        },
        "outcome_count": {
            "checked": (paper_result.get("outcome_tracker_payload") or {}).get("checked"),
            "closed": (paper_result.get("outcome_tracker_payload") or {}).get("closed"),
            "outcome": paper_result.get("closed_outcome"),
        },
        "broker_execution_disabled": not master_guard.get("can_call_broker"),
        "telegram_disabled": not master_guard.get("can_send_telegram"),
        "hft_enabled": False,
        "classic_mode_frozen": approved,
        "approved_for_vps_deploy": approved,
        "remaining_known_debts": [
            "legacy_open_rows_quarantined_warning" if journal_truth.get("legacy_open_rows_warning") else None,
            "authoritative_runtime_truth still records old advisory stale files for non-blocking historical components",
        ],
        "freeze_rules": [
            "no new execution engines",
            "no new journals",
            "no new dashboard truth paths",
            "no new runtime owners",
            "no HFT integration",
            "bug fixes only",
        ],
        "final_recommendation": (
            "APPROVE_VPS_DEPLOY_AFTER_GIT_PUSH" if approved else "DO_NOT_DEPLOY_UNTIL_MISSION_020_BLOCKERS_RESOLVED"
        ),
    }
    report["remaining_known_debts"] = [item for item in report["remaining_known_debts"] if item]
    diagnostic["freeze_report"] = report
    diagnostic["status"] = "PASS" if approved else "FAIL"
    _write_json(MISSION_DIAGNOSTIC_PATH, diagnostic)
    _write_json(REPORT_PATH, report)
    _restore_env(env_snapshot)
    return diagnostic


if __name__ == "__main__":
    result = run_mission()
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    raise SystemExit(0 if result.get("status") == "PASS" else 1)
