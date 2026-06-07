import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from data.active_trade_store import canonical_open_trade_count
from utils.market_hours import IST, is_trade_window


RUNTIME_DIR = Path("data") / "runtime"
AUTHORITATIVE_RUNTIME_TRUTH_PATH = RUNTIME_DIR / "authoritative_runtime_truth.json"
JOURNAL_TRUTH_UNIFICATION_PATH = RUNTIME_DIR / "journal_truth_unification.json"
MASTER_BRAIN_ACTIVATION_GUARD_PATH = RUNTIME_DIR / "master_brain_activation_guard.json"

MODE_DISABLED = "DISABLED"
MODE_READ_ONLY = "READ_ONLY"
MODE_ADVISORY_ONLY = "ADVISORY_ONLY"
MODE_PAPER_ONLY = "PAPER_ONLY"
MODE_REAL = "REAL"
EXPLICIT_MODES = {MODE_DISABLED, MODE_READ_ONLY, MODE_ADVISORY_ONLY, MODE_PAPER_ONLY, MODE_REAL}

REAL_APPROVAL_TOKEN = "YES_I_APPROVE_REAL_MASTER_BRAIN"
BROKER_APPROVAL_TOKEN = "YES_I_APPROVE_LIVE_BROKER_EXECUTION"
TELEGRAM_APPROVAL_TOKEN = "YES_I_APPROVE_TELEGRAM_ALERTS"
SUPABASE_APPROVAL_TOKEN = "YES_I_APPROVE_SUPABASE_TRADE_WRITES"
MARKET_PERMISSION_TOKEN = "ALLOW_REAL_MASTER_BRAIN_SESSION"


def _now_ist():
    return datetime.now(IST).isoformat()


def _read_json(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def normalize_requested_mode(value):
    requested = str(value or "").strip().upper()
    if not requested:
        return requested, MODE_READ_ONLY, "missing_mode_forced_read_only"
    if requested not in EXPLICIT_MODES:
        return requested, MODE_READ_ONLY, "invalid_or_ambiguous_mode_forced_read_only"
    return requested, requested, "explicit_mode"


def _truth_restart_blocked(authoritative_truth):
    summary = authoritative_truth.get("summary") if isinstance(authoritative_truth, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    blockers = summary.get("restart_blockers") if isinstance(summary.get("restart_blockers"), list) else []
    overall = str(summary.get("overall_status") or "UNKNOWN").upper()
    return bool(blockers or overall in {"STOPPED", "STALE", "DEGRADED", "UNKNOWN"}), overall, blockers


def _journal_clean(journal_truth):
    if not isinstance(journal_truth, dict) or not journal_truth:
        return False, ["journal_truth_unification_missing"]
    blockers = []
    try:
        canonical_count = int(journal_truth.get("canonical_open_trade_count", canonical_open_trade_count()))
    except (TypeError, ValueError):
        canonical_count = canonical_open_trade_count()
    if canonical_count != 0:
        blockers.append("canonical_active_trade_truth_not_clean")
    if journal_truth.get("legacy_open_rows_warning"):
        blockers.append("journal_legacy_open_rows_warning")
    if journal_truth.get("restart_blocker"):
        blockers.append("journal_truth_restart_blocker")
    return not blockers, blockers


def build_master_brain_activation_guard(
    requested_mode=None,
    *,
    env=None,
    authoritative_truth=None,
    journal_truth=None,
    write=False,
    output_path=MASTER_BRAIN_ACTIVATION_GUARD_PATH,
):
    env = env if isinstance(env, dict) else os.environ
    requested_raw = requested_mode if requested_mode is not None else env.get("TITAN_RUNTIME_MASTER_BRAIN_MODE")
    requested_mode, effective_mode, mode_reason = normalize_requested_mode(requested_raw)
    authoritative_truth = (
        authoritative_truth
        if isinstance(authoritative_truth, dict)
        else _read_json(AUTHORITATIVE_RUNTIME_TRUTH_PATH)
    )
    journal_truth = (
        journal_truth
        if isinstance(journal_truth, dict)
        else _read_json(JOURNAL_TRUTH_UNIFICATION_PATH)
    )

    real_mode_blockers = []
    restart_blocked, runtime_overall, runtime_blockers = _truth_restart_blocked(authoritative_truth)
    journal_clean, journal_blockers = _journal_clean(journal_truth)
    market_allowed = bool(is_trade_window() and env.get("TITAN_MARKET_SESSION_PERMISSION") == MARKET_PERMISSION_TOKEN)
    telegram_requested = str(env.get("TITAN_MASTER_BRAIN_SEND_TELEGRAM", "true")).strip().lower() not in {"0", "false", "no"}

    if effective_mode == MODE_REAL:
        if env.get("TITAN_MASTER_BRAIN_ALLOW_REAL") != REAL_APPROVAL_TOKEN:
            real_mode_blockers.append("missing_real_master_brain_approval_token")
        if env.get("TITAN_RUNTIME_OWNER") != "VPS":
            real_mode_blockers.append("runtime_owner_not_vps")
        if not market_allowed:
            real_mode_blockers.append("market_session_permission_not_granted")
        if not journal_clean:
            real_mode_blockers.extend(journal_blockers)
        if restart_blocked:
            real_mode_blockers.append(f"authoritative_runtime_truth_restart_blocked:{runtime_overall}")
            real_mode_blockers.extend([f"runtime_blocker:{item}" for item in runtime_blockers])
        if env.get("TITAN_BROKER_LIVE_EXECUTION") != BROKER_APPROVAL_TOKEN:
            real_mode_blockers.append("broker_live_execution_not_explicitly_enabled")
        if telegram_requested and env.get("TITAN_TELEGRAM_ALERTS") != TELEGRAM_APPROVAL_TOKEN:
            real_mode_blockers.append("telegram_alert_permission_not_explicitly_enabled")
        if env.get("TITAN_SUPABASE_TRADE_WRITES") != SUPABASE_APPROVAL_TOKEN:
            real_mode_blockers.append("supabase_trade_write_permission_not_explicitly_enabled")

    real_allowed = bool(effective_mode == MODE_REAL and not real_mode_blockers)
    if effective_mode == MODE_DISABLED:
        status = MODE_DISABLED
    elif effective_mode == MODE_READ_ONLY:
        status = MODE_READ_ONLY
    elif effective_mode == MODE_ADVISORY_ONLY:
        status = MODE_ADVISORY_ONLY
    elif effective_mode == MODE_PAPER_ONLY:
        status = MODE_PAPER_ONLY
    elif real_allowed:
        status = "LIVE"
    else:
        status = "REAL_BLOCKED"

    can_send_telegram = bool(real_allowed and telegram_requested and env.get("TITAN_TELEGRAM_ALERTS") == TELEGRAM_APPROVAL_TOKEN)
    can_call_broker = bool(real_allowed and env.get("TITAN_BROKER_LIVE_EXECUTION") == BROKER_APPROVAL_TOKEN)
    payload = {
        "generated_at": _now_ist(),
        "requested_mode": requested_mode or None,
        "effective_mode": effective_mode,
        "status": status,
        "real_mode_allowed": real_allowed,
        "real_mode_blockers": real_mode_blockers,
        "can_send_telegram": can_send_telegram,
        "can_mutate_journal": bool(real_allowed),
        "can_write_supabase_trades": bool(real_allowed and env.get("TITAN_SUPABASE_TRADE_WRITES") == SUPABASE_APPROVAL_TOKEN),
        "can_call_broker": can_call_broker,
        "can_execute_orders": can_call_broker,
        "reason": "real_mode_guard_passed" if real_allowed else (
            mode_reason if effective_mode != MODE_REAL else "real_mode_blocked_by_activation_guard"
        ),
        "runtime_overall_status": runtime_overall,
        "runtime_restart_blockers": runtime_blockers,
        "journal_truth_clean": journal_clean,
        "market_session_allowed": market_allowed,
        "telegram_requested": telegram_requested,
        "safety": {
            "broker_calls": False,
            "trade_placement": False,
            "telegram_sent": False,
            "journal_row_mutation": False,
            "service_restart": False,
            "diagnostic_status_write_only": bool(write),
        },
    }
    if write:
        _atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(build_master_brain_activation_guard(write=True), indent=2, sort_keys=True))
