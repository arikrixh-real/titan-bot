import csv
import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from supabase import create_client
except Exception:
    create_client = None

try:
    from journal.trade_id import build_canonical_trade_id, build_setup_signature
except Exception:
    build_canonical_trade_id = None
    build_setup_signature = None

try:
    from tools.trade_pipeline_check import build_trade_contract_diagnostics
except Exception:
    build_trade_contract_diagnostics = None


IST = ZoneInfo("Asia/Kolkata")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / "data" / "runtime"
PAPER_JOURNAL_STATUS_PATH = RUNTIME_DIR / "paper_journal_status.json"
TRADE_CONTRACT_DIAGNOSTICS_PATH = RUNTIME_DIR / "trade_contract_diagnostics.json"
ACTIVE_TRADES_CSV = PROJECT_ROOT / "data" / "journals" / "active_trades.csv"

PAPER_SOURCE = "RUNTIME_SCANNER_PAPER"
PAPER_FLAG = "TITAN_ENABLE_PAPER_JOURNAL"
SAFE_SELECTOR = "SCORED_DYNAMIC_50"

LOCAL_REQUIRED_FIELDS = [
    "trade_id",
    "setup_signature",
    "trade_date",
    "scan_id",
    "symbol",
    "side",
    "entry",
    "sl",
    "stop_loss",
    "target",
    "tp",
    "rr",
    "score",
    "final_score",
    "rank_score",
    "paper_trade_id",
    "is_paper_trade",
    "source",
    "truth_gate_status",
    "selector_used",
    "ohlc_status",
    "alert_sent",
    "telegram_alerted",
    "status",
    "created_at_ist",
    "opened_at",
    "last_checked_at",
    "reason",
]


def paper_journal_enabled():
    return str(os.getenv(PAPER_FLAG, "")).strip().lower() == "true"


def timestamp_ist():
    return datetime.now(IST).isoformat()


def _today_key():
    return datetime.now(IST).strftime("%Y-%m-%d")


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


def _read_csv_rows(path):
    path = Path(path)
    if not path.exists():
        return [], []
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            return list(reader.fieldnames or []), list(reader)
    except Exception:
        return [], []


def _write_csv_rows(path, fieldnames, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = []
    seen = set()
    for field in list(fieldnames or []) + LOCAL_REQUIRED_FIELDS:
        if field and field not in seen:
            ordered.append(field)
            seen.add(field)
    for row in rows:
        for field in row.keys():
            if field not in seen:
                ordered.append(field)
                seen.add(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ordered, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _safe_float(value):
    try:
        if value is None or value == "":
            return None
        result = float(value)
        if not math.isfinite(result):
            return None
        return result
    except Exception:
        return None


def _side(value):
    text = str(value or "").strip().upper()
    if text in {"BUY", "LONG"}:
        return "BUY"
    if text in {"SELL", "SHORT"}:
        return "SELL"
    return text


def _local_side(value):
    text = _side(value)
    if text == "BUY":
        return "LONG"
    if text == "SELL":
        return "SHORT"
    return text


def _open_trade_exists_local(symbol, side):
    _, rows = _read_csv_rows(ACTIVE_TRADES_CSV)
    wanted_symbol = str(symbol or "").strip().upper()
    wanted_side = _side(side)
    for row in rows:
        status = str(row.get("status") or "").strip().upper()
        if status not in {"OPEN", "ACTIVE", "LIVE"}:
            continue
        if str(row.get("symbol") or "").strip().upper() != wanted_symbol:
            continue
        if _side(row.get("side")) == wanted_side:
            return True
    return False


def _get_supabase():
    if create_client is None:
        return None
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None


def _extract_missing_column(error_text):
    match = re.search(r"Could not find the '([^']+)' column", str(error_text))
    return match.group(1) if match else None


def _safe_supabase_insert(client, table_name, payload):
    clean = dict(payload)
    removed = []
    for _ in range(20):
        try:
            client.table(table_name).insert(clean).execute()
            return True, removed, None
        except Exception as exc:
            missing_col = _extract_missing_column(exc)
            if missing_col and missing_col in clean:
                removed.append(missing_col)
                clean.pop(missing_col, None)
                continue
            return False, removed, str(exc)
    return False, removed, "SUPABASE_SCHEMA_RETRY_LIMIT"


def _supabase_open_trade_exists(client, symbol, side):
    wanted_symbol = str(symbol or "").strip().upper()
    wanted_sides = {_side(side), _local_side(side)}
    for query_side in wanted_sides:
        try:
            result = (
                client.table("trades")
                .select("trade_id")
                .eq("symbol", wanted_symbol)
                .eq("side", query_side)
                .eq("status", "OPEN")
                .limit(1)
                .execute()
            )
            if result.data:
                return True, None
        except Exception as exc:
            return False, str(exc)
    return False, None


def _fallback_trade_id(scan_id, symbol, side, entry, stop_loss, target):
    seed = "|".join(
        [
            str(scan_id or ""),
            str(symbol or "").upper(),
            str(side or "").upper(),
            f"{entry or 0:.4f}",
            f"{stop_loss or 0:.4f}",
            f"{target or 0:.4f}",
            PAPER_SOURCE,
        ]
    )
    return "PAPER-" + str(abs(hash(seed)))


def _build_trade_ids(scan_id, setup):
    symbol = str(setup.get("symbol") or "").strip().upper()
    side = _side(setup.get("side"))
    entry = _safe_float(setup.get("entry"))
    stop_loss = _safe_float(setup.get("stop_loss"))
    target = _safe_float(setup.get("target"))
    local_side = _local_side(side)
    if build_canonical_trade_id:
        trade_id = build_canonical_trade_id(scan_id, symbol, local_side, entry, stop_loss, target, source=PAPER_SOURCE)
    else:
        trade_id = _fallback_trade_id(scan_id, symbol, side, entry, stop_loss, target)
    if build_setup_signature:
        setup_signature = build_setup_signature(symbol, local_side, entry, stop_loss, target)
    else:
        setup_signature = f"{symbol}|{local_side}|{entry}|{stop_loss}|{target}"
    return trade_id, setup_signature


def _trade_row(setup, *, scan_id, truth_gate_status, selector_used, ohlc_status):
    symbol = str(setup.get("symbol") or "").strip().upper()
    side = _side(setup.get("side"))
    local_side = _local_side(side)
    entry = _safe_float(setup.get("entry"))
    stop_loss = _safe_float(setup.get("stop_loss"))
    target = _safe_float(setup.get("target"))
    rr = _safe_float(setup.get("rr"))
    final_score = _safe_float(setup.get("final_score"))
    now = timestamp_ist()
    trade_id, setup_signature = _build_trade_ids(scan_id, setup)
    return {
        "trade_id": trade_id,
        "setup_signature": setup_signature,
        "trade_date": _today_key(),
        "scan_id": str(scan_id or ""),
        "symbol": symbol,
        "side": local_side,
        "entry": entry,
        "sl": stop_loss,
        "stop_loss": stop_loss,
        "target": target,
        "tp": target,
        "rr": rr,
        "score": final_score,
        "final_score": final_score,
        "rank_score": final_score,
        "paper_trade_id": trade_id,
        "is_paper_trade": True,
        "source": PAPER_SOURCE,
        "truth_gate_status": truth_gate_status,
        "selector_used": selector_used,
        "ohlc_status": ohlc_status,
        "alert_sent": False,
        "telegram_alerted": "NO",
        "status": "OPEN",
        "created_at_ist": now,
        "opened_at": now,
        "last_checked_at": now,
        "reason": str(setup.get("reason") or "")[:500],
    }


def _supabase_payload(row):
    payload = dict(row)
    payload.update(
        {
            "side": _side(row.get("side")),
            "stop_loss": row.get("stop_loss") or row.get("sl"),
            "status": "OPEN",
            "created_at": row.get("created_at_ist"),
            "updated_at": timestamp_ist(),
            "alert_sent": False,
            "telegram_alerted": "NO",
        }
    )
    return payload


def _append_local_trade(row):
    fieldnames, rows = _read_csv_rows(ACTIVE_TRADES_CSV)
    rows.append(row)
    _write_csv_rows(ACTIVE_TRADES_CSV, fieldnames, rows)


def _valid_setups(contract_payload):
    return [
        item
        for item in contract_payload.get("setups") or []
        if (item.get("validation") or {}).get("status") == "PASS"
    ]


def latest_contract_payload(refresh=False):
    if refresh and build_trade_contract_diagnostics is not None:
        try:
            return build_trade_contract_diagnostics()
        except Exception:
            pass
    return _read_json(TRADE_CONTRACT_DIAGNOSTICS_PATH)


def _base_status(contract_payload=None):
    contract_payload = contract_payload or latest_contract_payload(refresh=False)
    valid = _valid_setups(contract_payload)
    _, active_rows = _read_csv_rows(ACTIVE_TRADES_CSV)
    open_count = sum(1 for row in active_rows if str(row.get("status") or "").upper() in {"OPEN", "ACTIVE", "LIVE"})
    return {
        "timestamp_ist": timestamp_ist(),
        "enabled": paper_journal_enabled(),
        "attempted": 0,
        "written": 0,
        "duplicate_skipped": 0,
        "failed": 0,
        "destination": None,
        "errors": [],
        "latest_setup_count": int(contract_payload.get("final_setup_count") or len(contract_payload.get("setups") or [])),
        "valid_setup_count": len(valid),
        "open_trades_count": open_count,
        "duplicate_protection_status": "PASS",
        "last_write_status": "NOT_RUN",
        "broker_execution_disabled": True,
        "telegram_sent": False,
        "only_journal_paper_write_enabled": paper_journal_enabled(),
    }


def write_disabled_status(reason="FLAG_DISABLED"):
    payload = _base_status()
    payload.update(
        {
            "last_write_status": "READ_ONLY_DISABLED",
            "blocked_reason": reason,
            "recommended_next_action": f"Set {PAPER_FLAG}=true only when paper journaling is intended.",
        }
    )
    _write_json(PAPER_JOURNAL_STATUS_PATH, payload)
    return payload


def maybe_write_paper_journal(
    *,
    truth_gate_payload=None,
    selector_payload=None,
    ohlc_status=None,
    scan_id=None,
    within_trading_window=False,
    refresh_contract=True,
):
    contract_payload = latest_contract_payload(refresh=refresh_contract)
    payload = _base_status(contract_payload)

    if not paper_journal_enabled():
        payload.update(
            {
                "last_write_status": "READ_ONLY_DISABLED",
                "blocked_reason": "TITAN_ENABLE_PAPER_JOURNAL_FALSE",
                "recommended_next_action": f"Set {PAPER_FLAG}=true to enable paper-only journaling.",
            }
        )
        _write_json(PAPER_JOURNAL_STATUS_PATH, payload)
        return payload

    truth_gate_status = str((truth_gate_payload or {}).get("overall_status") or "").upper()
    market_gate_status = str(((truth_gate_payload or {}).get("market_data_status") or {}).get("status") or "").upper()
    selector_used = str((selector_payload or {}).get("selector_used") or "").upper()
    fallback_active = bool((selector_payload or {}).get("fallback_active"))
    ohlc_status = str(ohlc_status or "").upper()

    blockers = []
    if market_gate_status != "PASS":
        blockers.append(f"TRUTH_GATE_MARKET_DATA_NOT_PASS:{market_gate_status or 'UNKNOWN'}")
    if selector_used != SAFE_SELECTOR or fallback_active:
        blockers.append(f"SELECTOR_NOT_PASS:{selector_used or 'UNKNOWN'}")
    if ohlc_status != "PASS":
        blockers.append(f"OHLC_NOT_PASS:{ohlc_status or 'UNKNOWN'}")
    if not within_trading_window:
        blockers.append("OUTSIDE_TRADING_WINDOW")

    valid_setups = _valid_setups(contract_payload)
    if not valid_setups:
        blockers.append("NO_VALID_SETUP_CONTRACTS")

    if blockers:
        payload.update(
            {
                "last_write_status": "BLOCKED",
                "blocked_reason": ";".join(blockers),
                "truth_gate_status": truth_gate_status or "UNKNOWN",
                "truth_gate_market_data_status": market_gate_status or "UNKNOWN",
                "selector_used": selector_used or "UNKNOWN",
                "ohlc_status": ohlc_status or "UNKNOWN",
                "recommended_next_action": "Fix blocking gates before enabling paper journal writes.",
            }
        )
        _write_json(PAPER_JOURNAL_STATUS_PATH, payload)
        return payload

    client = _get_supabase()
    destinations = set()
    errors = []

    for setup in valid_setups:
        symbol = str(setup.get("symbol") or "").strip().upper()
        side = _side(setup.get("side"))
        payload["attempted"] += 1

        if _open_trade_exists_local(symbol, side):
            payload["duplicate_skipped"] += 1
            continue

        supabase_duplicate = False
        if client is not None:
            supabase_duplicate, duplicate_error = _supabase_open_trade_exists(client, symbol, side)
            if duplicate_error:
                errors.append(f"{symbol}:{side}:SUPABASE_DUPLICATE_CHECK_FAILED:{duplicate_error}")
            if supabase_duplicate:
                payload["duplicate_skipped"] += 1
                continue

        row = _trade_row(
            setup,
            scan_id=scan_id or contract_payload.get("scanner_cycle_id"),
            truth_gate_status=truth_gate_status,
            selector_used=selector_used,
            ohlc_status=ohlc_status,
        )

        written = False
        if client is not None:
            ok, removed_cols, error = _safe_supabase_insert(client, "trades", _supabase_payload(row))
            if ok:
                written = True
                destinations.add("SUPABASE_TRADES")
            else:
                errors.append(f"{symbol}:{side}:SUPABASE_WRITE_FAILED:{error}")
                if removed_cols:
                    errors.append(f"{symbol}:{side}:SUPABASE_COLUMNS_REMOVED:{','.join(removed_cols)}")

        if not written:
            try:
                _append_local_trade(row)
                written = True
                destinations.add("LOCAL_ACTIVE_TRADES_CSV")
            except Exception as exc:
                errors.append(f"{symbol}:{side}:LOCAL_FALLBACK_WRITE_FAILED:{exc}")

        if written:
            payload["written"] += 1
        else:
            payload["failed"] += 1

    payload.update(
        {
            "destination": "MIXED" if len(destinations) > 1 else (next(iter(destinations)) if destinations else None),
            "errors": errors[:50],
            "last_write_status": "PASS" if payload["failed"] == 0 else "PARTIAL_FAIL",
            "truth_gate_status": truth_gate_status,
            "truth_gate_market_data_status": market_gate_status,
            "selector_used": selector_used,
            "ohlc_status": ohlc_status,
            "recommended_next_action": None if payload["failed"] == 0 else "Review paper journal errors.",
        }
    )
    _write_json(PAPER_JOURNAL_STATUS_PATH, payload)
    return payload


def latest_status():
    payload = _read_json(PAPER_JOURNAL_STATUS_PATH)
    if payload:
        return payload
    return write_disabled_status(reason="STATUS_FILE_MISSING_CREATED_READ_ONLY_STATUS")
