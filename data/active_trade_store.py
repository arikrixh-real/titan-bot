import csv
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from supabase import create_client
except Exception:
    create_client = None

try:
    from journal.trade_journal import ACTIVE_FIELDS
except Exception:
    ACTIVE_FIELDS = []


IST = ZoneInfo("Asia/Kolkata")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / "data" / "runtime"
ACTIVE_TRADES_CSV = PROJECT_ROOT / "data" / "journals" / "active_trades.csv"
DEBUG_PATH = RUNTIME_DIR / "active_trade_store_debug.json"
JOURNAL_TRUTH_UNIFICATION_PATH = RUNTIME_DIR / "journal_truth_unification.json"
OPEN_STATUSES = {"OPEN", "ACTIVE", "LIVE"}
LEGACY_ACTIVE_TRADE_FILES = [
    PROJECT_ROOT / "data" / "journals" / "active_trades_old.csv",
    PROJECT_ROOT / "data" / "journals" / "active_trades.backup.csv",
    PROJECT_ROOT / "data" / "journals" / "open_trades.csv",
    PROJECT_ROOT / "data" / "trade_journal.csv",
    PROJECT_ROOT / "active_trades.csv",
    PROJECT_ROOT / "journal" / "active_trades.csv",
]

"""
Authoritative active_trades storage owner.

All active trade lifecycle mutations must go through this module. Other
components may decide when to open/close/read trades, but direct writes to
data/journals/active_trades.csv or Supabase trades are centralized here.
"""


def _timestamp_ist():
    return datetime.now(IST).isoformat()


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _symbol(value):
    return str(value or "").strip().upper().replace(".NS", "")


def _side(value):
    text = str(value or "").strip().upper()
    if text in {"BUY", "LONG"}:
        return "LONG"
    if text in {"SELL", "SHORT"}:
        return "SHORT"
    return text


def _status(row):
    return str((row or {}).get("status") or "").strip().upper()


def _is_open(row):
    return _status(row) in OPEN_STATUSES


def _read_csv_rows(path=None):
    path = Path(path or ACTIVE_TRADES_CSV)
    if not path.exists():
        return [], []
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            return list(reader.fieldnames or []), list(reader)
    except Exception:
        return [], []


def _ordered_fields(fieldnames, rows):
    ordered = []
    seen = set()
    for field in list(ACTIVE_FIELDS or []) + list(fieldnames or []):
        if field and field not in seen:
            ordered.append(field)
            seen.add(field)
    for row in rows:
        for field in row.keys():
            if field and field not in seen:
                ordered.append(field)
                seen.add(field)
    return ordered


def _write_csv_rows(rows, fieldnames=None):
    ACTIVE_TRADES_CSV.parent.mkdir(parents=True, exist_ok=True)
    ordered = _ordered_fields(fieldnames, rows)
    with ACTIVE_TRADES_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ordered, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in ordered})
    return ordered


def ensure_active_trade_store():
    fieldnames, rows = _read_csv_rows()
    if fieldnames and ACTIVE_TRADES_CSV.exists() and ACTIVE_TRADES_CSV.stat().st_size > 0:
        return {"ensured": True, "created": False, "fieldnames": fieldnames}
    schema_fields = _write_csv_rows(rows, fieldnames)
    return {"ensured": True, "created": True, "fieldnames": schema_fields}


def _get_supabase_client():
    if str(os.getenv("TITAN_ACTIVE_STORE_DISABLE_SUPABASE", "")).strip().lower() in {"1", "true", "yes", "y"}:
        return None, None
    if create_client is None:
        return None, "SUPABASE_LIBRARY_UNAVAILABLE"
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None, "SUPABASE_CREDENTIALS_MISSING"
    try:
        return create_client(url, key), None
    except Exception as exc:
        return None, f"SUPABASE_CLIENT_ERROR:{exc}"


def _supabase_payload(row):
    payload = dict(row or {})
    payload["symbol"] = _symbol(payload.get("symbol"))
    payload["side"] = _side(payload.get("side"))
    payload["status"] = str(payload.get("status") or "OPEN").upper()
    payload.setdefault("updated_at", _timestamp_ist())
    if payload.get("created_at_ist") and not payload.get("created_at"):
        payload["created_at"] = payload.get("created_at_ist")
    return payload


def _supabase_update_payload(row):
    payload = dict(row or {})
    if "symbol" in payload:
        payload["symbol"] = _symbol(payload.get("symbol"))
    if "side" in payload:
        payload["side"] = _side(payload.get("side"))
    if "status" in payload:
        payload["status"] = str(payload.get("status") or "").upper()
    payload.setdefault("updated_at", _timestamp_ist())
    return payload


def _read_supabase_open_trades(client):
    try:
        result = (
            client.table("trades")
            .select("*")
            .in_("status", list(OPEN_STATUSES))
            .limit(1000)
            .execute()
        )
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        for row in rows:
            row["_active_trade_source"] = "SUPABASE_TRADES"
        return rows, None
    except Exception as exc:
        return [], f"SUPABASE_READ_FAILED:{exc}"


def _write_debug(
    *,
    write_destination=None,
    read_sources_checked=None,
    open_trades=None,
    synthetic_trade_found=None,
    schema_fields=None,
    errors=None,
):
    read_sources_checked = read_sources_checked or []
    errors = errors or []
    _, local_rows = _read_csv_rows()
    open_trades = open_trades if open_trades is not None else [row for row in local_rows if _is_open(row)]
    schema_fields = schema_fields or _ordered_fields([], local_rows)
    payload = {
        "timestamp_ist": _timestamp_ist(),
        "write_destination": write_destination,
        "read_sources_checked": read_sources_checked,
        "open_trade_count": len(open_trades or []),
        "synthetic_trade_found": bool(synthetic_trade_found)
        if synthetic_trade_found is not None
        else any(
            _is_open(row)
            and (
                _truthy(row.get("test_trade"))
                or str(row.get("source") or "").upper() == "SYNTHETIC_PIPELINE_TEST"
            )
            for row in open_trades or []
        ),
        "schema_fields": list(schema_fields or []),
        "errors": errors,
    }
    DEBUG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEBUG_PATH.with_suffix(DEBUG_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(DEBUG_PATH)
    return payload


def load_open_trades():
    errors = []
    read_sources = []
    fieldnames, local_rows = _read_csv_rows()
    open_rows = []

    read_sources.append(str(ACTIVE_TRADES_CSV))
    for row in local_rows:
        if _is_open(row):
            item = dict(row)
            item["_active_trade_source"] = "LOCAL_ACTIVE_TRADES_CSV"
            open_rows.append(item)

    client, client_error = _get_supabase_client()
    if client is None:
        if client_error:
            errors.append(client_error)
    else:
        read_sources.append("SUPABASE_TRADES")
        supabase_rows, supabase_error = _read_supabase_open_trades(client)
        if supabase_error:
            errors.append(supabase_error)
        open_rows.extend(supabase_rows)

    _write_debug(
        write_destination=None,
        read_sources_checked=read_sources,
        open_trades=open_rows,
        schema_fields=fieldnames,
        errors=errors,
    )
    return open_rows


def load_canonical_open_trades():
    fieldnames, local_rows = _read_csv_rows(ACTIVE_TRADES_CSV)
    open_rows = []
    for row in local_rows:
        if _is_open(row):
            item = dict(row)
            item["_active_trade_source"] = "CANONICAL_ACTIVE_TRADES_CSV"
            open_rows.append(item)
    _write_debug(
        write_destination=None,
        read_sources_checked=[str(ACTIVE_TRADES_CSV)],
        open_trades=open_rows,
        schema_fields=fieldnames,
        errors=[],
    )
    return open_rows


def load_canonical_active_trade_rows():
    _, rows = _read_csv_rows(ACTIVE_TRADES_CSV)
    return [dict(row) for row in rows]


def canonical_open_trade_count():
    return len(load_canonical_open_trades())


def _legacy_file_record(path):
    path = Path(path)
    _, rows = _read_csv_rows(path)
    open_rows = [row for row in rows if _is_open(row)]
    relative_path = str(path.relative_to(PROJECT_ROOT)).replace("\\", "/") if path.is_absolute() else str(path).replace("\\", "/")
    if relative_path == "data/trade_journal.csv":
        classification = "LEGACY_JOURNAL_HISTORY"
    elif path.exists():
        classification = "LEGACY_NON_CANONICAL"
    else:
        classification = "ARCHIVE_ONLY"
    return {
        "path": relative_path,
        "exists": path.exists(),
        "classification": classification,
        "row_count": len(rows),
        "open_row_count": len(open_rows),
        "open_trade_interpretation_allowed": False,
    }


def classify_legacy_active_trade_files(paths=None):
    records = []
    for path in paths or LEGACY_ACTIVE_TRADE_FILES:
        records.append(_legacy_file_record(path))
    return records


def write_journal_truth_unification(
    *,
    readers_checked=None,
    readers_patched=None,
    unsafe_fallbacks_removed=None,
    remaining_unknowns=None,
    output_path=None,
):
    canonical_rows = load_canonical_active_trade_rows()
    canonical_open_rows = [row for row in canonical_rows if _is_open(row)]
    legacy_records = classify_legacy_active_trade_files()
    legacy_found = [record for record in legacy_records if record["exists"]]
    legacy_open_rows = {
        record["path"]: record["open_row_count"]
        for record in legacy_found
        if record["open_row_count"] > 0
    }
    payload = {
        "generated_at": _timestamp_ist(),
        "canonical_active_trade_file": str(ACTIVE_TRADES_CSV.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "canonical_active_trade_count": len(canonical_open_rows),
        "canonical_active_trade_row_count": len(canonical_rows),
        "canonical_open_trade_count": len(canonical_open_rows),
        "legacy_journal_row_count": sum(record["row_count"] for record in legacy_found),
        "legacy_open_trade_interpretation_allowed": False,
        "journal_truth_status": "CANONICAL_ACTIVE_TRADES_OPEN" if canonical_open_rows else "CANONICAL_ACTIVE_TRADES_ZERO_OPEN",
        "legacy_files_found": legacy_found,
        "legacy_quarantined_file_count": len(legacy_found),
        "legacy_open_rows_by_file": legacy_open_rows,
        "legacy_open_rows_warning": bool(legacy_open_rows),
        "readers_checked": list(readers_checked or []),
        "readers_patched": list(readers_patched or []),
        "unsafe_fallbacks_removed": list(unsafe_fallbacks_removed or []),
        "remaining_unknowns": list(remaining_unknowns or []),
        "restart_blocker": bool(remaining_unknowns),
    }
    path = Path(output_path or JOURNAL_TRUTH_UNIFICATION_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return payload


def find_open_trade(symbol, source=None, test_trade=None):
    wanted_symbol = _symbol(symbol)
    wanted_source = str(source or "").strip().upper()
    open_rows = load_canonical_open_trades()
    matches = []
    for row in open_rows:
        if wanted_symbol and _symbol(row.get("symbol")) != wanted_symbol:
            continue
        if wanted_source and str(row.get("source") or "").strip().upper() != wanted_source:
            continue
        if test_trade is not None and _truthy(row.get("test_trade")) != bool(test_trade):
            continue
        matches.append(row)
    _write_debug(
        write_destination=None,
        read_sources_checked=[str(ACTIVE_TRADES_CSV)],
        open_trades=open_rows,
        synthetic_trade_found=bool(matches),
        errors=[],
    )
    return matches[0] if matches else None


def append_open_trade(row, *, client=None, prefer_supabase=True):
    row = dict(row or {})
    row["status"] = str(row.get("status") or "OPEN").upper()
    errors = []
    destinations = []

    if prefer_supabase:
        if client is None:
            client, client_error = _get_supabase_client()
            if client_error:
                errors.append(client_error)
        if client is not None:
            try:
                client.table("trades").insert(_supabase_payload(row)).execute()
                destinations.append("SUPABASE_TRADES")
            except Exception as exc:
                errors.append(f"SUPABASE_WRITE_FAILED:{exc}")

    if not destinations:
        fieldnames, rows = _read_csv_rows()
        rows.append(row)
        schema_fields = _write_csv_rows(rows, fieldnames)
        destinations.append("LOCAL_ACTIVE_TRADES_CSV")
    else:
        schema_fields, _ = _read_csv_rows()

    open_rows = load_canonical_open_trades()
    _write_debug(
        write_destination="+".join(destinations),
        read_sources_checked=[str(ACTIVE_TRADES_CSV)],
        open_trades=open_rows,
        synthetic_trade_found=bool(
            find_open_trade(
                row.get("symbol"),
                source=row.get("source") if row.get("source") else None,
                test_trade=True if _truthy(row.get("test_trade")) else None,
            )
        ),
        schema_fields=schema_fields,
        errors=errors,
    )
    return {
        "written": True,
        "destination": "+".join(destinations),
        "errors": errors,
        "row": row,
    }


def update_active_trade(trade, updates=None):
    updates = dict(updates or {})
    trade = trade if isinstance(trade, dict) else {"trade_id": str(trade or "")}
    trade_id = str(trade.get("trade_id") or "").strip()
    match_fields = ["symbol", "side", "opened_at", "entry", "sl", "target"]
    fieldnames, rows = _read_csv_rows()
    updated = False
    updated_rows = []

    for row in rows:
        row_trade_id = str(row.get("trade_id") or "").strip()
        trade_id_match = bool(trade_id and row_trade_id == trade_id)
        fallback_pairs = [
            field
            for field in match_fields
            if trade.get(field) not in (None, "")
        ]
        fallback_match = bool(fallback_pairs) and not trade_id and all(
            str(row.get(field) or "").strip() == str(trade.get(field) or "").strip()
            for field in fallback_pairs
        )
        if trade_id_match or fallback_match:
            row.update(updates)
            updated = True
        updated_rows.append(row)

    schema_fields = _write_csv_rows(updated_rows, fieldnames)
    errors = []
    client, client_error = _get_supabase_client()
    if client is None:
        if client_error:
            errors.append(client_error)
    elif trade_id:
        try:
            client.table("trades").update(_supabase_update_payload(updates)).eq("trade_id", trade_id).execute()
        except Exception as exc:
            errors.append(f"SUPABASE_UPDATE_FAILED:{exc}")

    open_rows = [row for row in updated_rows if _is_open(row)]
    _write_debug(
        write_destination="LOCAL_ACTIVE_TRADES_CSV",
        read_sources_checked=[str(ACTIVE_TRADES_CSV), "SUPABASE_TRADES"],
        open_trades=open_rows,
        schema_fields=schema_fields,
        errors=errors,
    )
    return {"updated": updated, "trade_id": trade_id, "errors": errors}


def close_open_trade(trade, updates=None):
    result = update_active_trade(trade, updates)
    return {"closed": result.get("updated"), "trade_id": result.get("trade_id"), "errors": result.get("errors", [])}



def remove_matching_trades(predicate):
    fieldnames, rows = _read_csv_rows()
    kept = []
    removed = 0
    for row in rows:
        if predicate(row):
            removed += 1
            continue
        kept.append(row)
    schema_fields = _write_csv_rows(kept, fieldnames)
    _write_debug(
        write_destination="LOCAL_ACTIVE_TRADES_CSV",
        read_sources_checked=[str(ACTIVE_TRADES_CSV)],
        open_trades=[row for row in kept if _is_open(row)],
        schema_fields=schema_fields,
        errors=[],
    )
    return removed


def remove_test_trades(symbol=None, source="SYNTHETIC_PIPELINE_TEST"):
    """
    Remove only OPEN synthetic test rows from the canonical active trade store.

    Supabase cleanup is disabled by default. To allow it for this synthetic-only
    cleanup, set TITAN_ACTIVE_STORE_ENABLE_SUPABASE_TEST_CLEANUP=true.
    """
    wanted_symbol = _symbol(symbol)
    wanted_source = str(source or "SYNTHETIC_PIPELINE_TEST").strip().upper()
    errors = []

    def is_target(row):
        if not _is_open(row):
            return False
        if wanted_symbol and _symbol(row.get("symbol")) != wanted_symbol:
            return False
        if not _truthy(row.get("test_trade")):
            return False
        row_source = str(row.get("source") or "").strip().upper()
        if wanted_source and row_source != wanted_source:
            return False
        return True

    fieldnames, rows = _read_csv_rows()
    kept = []
    local_removed = 0
    for row in rows:
        if is_target(row):
            local_removed += 1
            continue
        kept.append(row)

    schema_fields = _write_csv_rows(kept, fieldnames)

    supabase_removed = 0
    supabase_cleanup_enabled = str(
        os.getenv("TITAN_ACTIVE_STORE_ENABLE_SUPABASE_TEST_CLEANUP", "")
    ).strip().lower() in {"1", "true", "yes", "y"}
    if supabase_cleanup_enabled:
        client, client_error = _get_supabase_client()
        if client is None:
            if client_error:
                errors.append(client_error)
        else:
            try:
                query = (
                    client.table("trades")
                    .update(
                        {
                            "status": "SYNTHETIC_TEST_REMOVED",
                            "updated_at": _timestamp_ist(),
                        }
                    )
                    .eq("source", wanted_source)
                    .eq("test_trade", True)
                    .in_("status", list(OPEN_STATUSES))
                )
                if wanted_symbol:
                    query = query.eq("symbol", wanted_symbol)
                result = query.execute()
                supabase_removed = len(result.data or []) if hasattr(result, "data") else 0
            except Exception as exc:
                errors.append(f"SUPABASE_TEST_CLEANUP_FAILED:{exc}")

    open_rows = [row for row in kept if _is_open(row)]
    _write_debug(
        write_destination="LOCAL_ACTIVE_TRADES_CSV"
        + ("+SUPABASE_TRADES" if supabase_cleanup_enabled else ""),
        read_sources_checked=[str(ACTIVE_TRADES_CSV)]
        + (["SUPABASE_TRADES"] if supabase_cleanup_enabled else []),
        open_trades=open_rows,
        synthetic_trade_found=any(is_target(row) for row in open_rows),
        schema_fields=schema_fields,
        errors=errors,
    )
    return {
        "removed": local_removed + supabase_removed,
        "local_removed": local_removed,
        "supabase_removed": supabase_removed,
        "supabase_cleanup_enabled": supabase_cleanup_enabled,
        "errors": errors,
    }
