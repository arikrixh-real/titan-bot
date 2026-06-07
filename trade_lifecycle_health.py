import csv
import json
from datetime import datetime, time, timezone
from pathlib import Path

from runtime_dependency_graph import SAFETY_FLAGS
from data.active_trade_store import classify_legacy_active_trade_files
from utils.market_hours import IST, TRADE_WINDOW_END, as_ist_datetime, is_trading_day


RUNTIME_DIR = Path("data") / "runtime"
JOURNAL_DIR = Path("data") / "journals"
ACTIVE_TRADES_CSV = JOURNAL_DIR / "active_trades.csv"
TRADE_OUTCOMES_CSV = JOURNAL_DIR / "trade_outcomes.csv"
OUTCOME_TRACKER_STATUS_PATH = RUNTIME_DIR / "outcome_tracker_status.json"
LIVE_PRICE_STATUS_PATH = Path("data") / "live_price_status.json"
LIVE_PRICE_CACHE_META_PATH = RUNTIME_DIR / "live_price_cache_meta.json"
TRADE_LIFECYCLE_HEALTH_PATH = RUNTIME_DIR / "trade_lifecycle_health.json"
TRADE_LIFECYCLE_RECONCILIATION_PATH = RUNTIME_DIR / "trade_lifecycle_reconciliation.json"
LEGACY_OPEN_TRADE_PATHS = [
    JOURNAL_DIR / "open_trades.csv",
    JOURNAL_DIR / "active_trades.backup.csv",
    JOURNAL_DIR / "active_trades_old.csv",
    Path("data") / "trade_journal.csv",
]
OPEN_STALE_SECONDS = 6 * 60 * 60
OUTCOME_FRESH_SECONDS = 15 * 60


def _read_json_safe(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": str(exc)}
    return payload if isinstance(payload, dict) else {"_read_error": "json_root_not_object"}


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _parse_timestamp(value):
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc).astimezone(IST)
        text = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            parsed = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed.astimezone(IST)
    except Exception:
        return None


def _age_seconds(timestamp, now_ist):
    if timestamp is None:
        return None
    return max(0.0, (now_ist - timestamp).total_seconds())


def _read_csv_rows(path):
    try:
        path = Path(path)
        if not path.exists() or path.stat().st_size == 0:
            return []
        with open(path, "r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except Exception:
        return []


def _open_status(row):
    status = str(row.get("status") or "").upper().strip()
    outcome = str(row.get("outcome") or "").upper().strip()
    result = str(row.get("result") or "").upper().strip()
    if status in {"OPEN", "LIVE", "ACTIVE"} and outcome not in {"TP", "SL"} and result not in {"WIN", "LOSS"}:
        return True
    return False


def _closed_tp_sl_status(row):
    status = str(row.get("status") or "").upper().strip()
    outcome = str(row.get("outcome") or "").upper().strip()
    result = str(row.get("result") or "").upper().strip()
    return (
        outcome in {"TP", "SL"}
        or result in {"WIN", "LOSS"}
        or status in {"CLOSED_TP", "CLOSED_SL"}
    )


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _is_learning_trade(row):
    status = str(row.get("status") or "").upper().strip()
    alert_sent = str(row.get("alert_sent") or row.get("telegram_alerted") or "").upper().strip()
    source = str(row.get("_source") or "").lower()
    if _truthy(row.get("is_paper_trade")) or str(row.get("paper_trade_id") or "").strip():
        return True
    if "learning" in source or "paper" in source or "watchlist" in source:
        return True
    if status in {"WATCHLIST", "LEARNING", "PAPER_OPEN"}:
        return True
    return alert_sent == "NO"


def _has_levels(row):
    for field in ("entry", "sl", "target"):
        try:
            if float(row.get(field) or 0) <= 0:
                return False
        except (TypeError, ValueError):
            return False
    return True


def _past_eod(opened_at, now_ist):
    if opened_at is None:
        return False
    if opened_at.date() < now_ist.date():
        return True
    if is_trading_day(now_ist):
        eod = datetime.combine(now_ist.date(), TRADE_WINDOW_END, tzinfo=IST)
        return now_ist > eod and opened_at <= eod
    return True


def _classified_open_trade(row, now_ist):
    opened_at = _parse_timestamp(row.get("opened_at") or row.get("timestamp"))
    last_checked = _parse_timestamp(row.get("last_checked_at"))
    opened_age = _age_seconds(opened_at, now_ist)
    last_check_age = _age_seconds(last_checked, now_ist)
    missing_levels = not _has_levels(row)
    eod_unresolved = _past_eod(opened_at, now_ist)
    stale_open = bool(
        eod_unresolved
        or opened_age is None
        or opened_age > OPEN_STALE_SECONDS
        or last_checked is None
        or last_check_age > OUTCOME_FRESH_SECONDS
    )
    if missing_levels:
        lifecycle_status = "CLOSED_MANUAL_RECONCILIATION_REQUIRED"
        reason = "MISSING_ENTRY_SL_OR_TARGET"
    elif _is_learning_trade(row):
        lifecycle_status = "LEARNING_OPEN"
        reason = "PAPER_OR_LEARNING_WATCHLIST_TRADE"
    elif eod_unresolved:
        lifecycle_status = "EOD_UNRESOLVED"
        reason = "OPEN_TRADE_PAST_EOD_WITHOUT_TP_SL_OUTCOME"
    elif stale_open:
        lifecycle_status = "STALE_OPEN"
        reason = "OPEN_TRADE_NOT_RECENTLY_CHECKED"
    else:
        lifecycle_status = "OPEN_PENDING"
        reason = "AWAITING_TP_SL_OR_NEXT_CHECK"
    return {
        "trade_id": row.get("trade_id"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "opened_at": opened_at.isoformat() if opened_at else None,
        "last_checked_at": last_checked.isoformat() if last_checked else None,
        "opened_age_seconds": round(opened_age, 3) if opened_age is not None else None,
        "last_check_age_seconds": round(last_check_age, 3) if last_check_age is not None else None,
        "entry": row.get("entry"),
        "sl": row.get("sl"),
        "target": row.get("target"),
        "is_learning_trade": _is_learning_trade(row),
        "source": row.get("_source"),
        "lifecycle_status": lifecycle_status,
        "unresolved_outcome_reason": reason,
    }


def _source_rows(path, source_name):
    rows = []
    for row in _read_csv_rows(path):
        enriched = dict(row)
        enriched["_source"] = source_name
        rows.append(enriched)
    return rows


def _dedupe_trade_rows(rows):
    deduped = []
    seen = set()
    for row in rows:
        key = _outcome_key(row)
        if not key:
            key = "|".join(str(row.get(field) or "").strip().upper() for field in ("_source", "symbol", "opened_at", "status"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _count_closed_tp_sl(rows):
    return sum(1 for row in rows if _closed_tp_sl_status(row))


def _build_trade_lifecycle_reconciliation(
    now_ist,
    active_rows,
    outcome_rows,
    unresolved,
    dashboard_live_trade_count,
    output_path=TRADE_LIFECYCLE_RECONCILIATION_PATH,
):
    all_open_rows = _dedupe_trade_rows(
        [dict(row, _source=row.get("_source") or str(ACTIVE_TRADES_CSV).replace("\\", "/")) for row in active_rows if _open_status(row)]
    )
    all_unresolved = [_classified_open_trade(row, now_ist) for row in all_open_rows]
    legacy_records = classify_legacy_active_trade_files(LEGACY_OPEN_TRADE_PATHS)
    legacy_open_rows_by_file = {
        record["path"]: record["open_row_count"]
        for record in legacy_records
        if record.get("exists") and record.get("open_row_count", 0) > 0
    }

    active_live = [row for row in unresolved if row["lifecycle_status"] == "OPEN_PENDING"]
    learning_open = [row for row in all_unresolved if row["lifecycle_status"] == "LEARNING_OPEN"]
    stale_open = [row for row in all_unresolved if row["lifecycle_status"] == "STALE_OPEN"]
    eod_unresolved = [row for row in all_unresolved if row["lifecycle_status"] == "EOD_UNRESOLVED"]
    manual_required = [row for row in all_unresolved if row["lifecycle_status"] == "CLOSED_MANUAL_RECONCILIATION_REQUIRED"]
    closed_tp_sl = _count_closed_tp_sl(outcome_rows)

    dashboard_source = "trade_lifecycle_health.active_live_trades"
    performance_source = "data/journals/trade_outcomes.csv:CLOSED_TP_CLOSED_SL_ONLY"
    if dashboard_live_trade_count is not None and dashboard_live_trade_count != len(active_live):
        explanation = (
            f"Dashboard live count source reported {dashboard_live_trade_count}; "
            f"truth classification found {len(active_live)} current-day active live trades, "
            f"{len(learning_open)} learning/watchlist open trades, "
            f"{len(stale_open)} stale open trades, and {len(eod_unresolved)} EOD unresolved trades."
        )
    else:
        explanation = (
            f"Dashboard live count uses current-day active live trades only; "
            f"performance uses {closed_tp_sl} closed TP/SL trades only."
        )

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "active_live_trades": {"count": len(active_live), "trades": active_live},
        "learning_open_trades": {"count": len(learning_open), "trades": learning_open},
        "stale_open_trades": {"count": len(stale_open), "trades": stale_open},
        "eod_unresolved_trades": {"count": len(eod_unresolved), "trades": eod_unresolved},
        "closed_tp_sl_trades": {"count": closed_tp_sl},
        "manual_reconciliation_required": {
            "count": len(manual_required),
            "required": bool(manual_required or stale_open or eod_unresolved),
            "trades": manual_required,
        },
        "legacy_quarantine": {
            "classification": "LEGACY_QUARANTINED",
            "files": legacy_records,
            "open_rows_by_file": legacy_open_rows_by_file,
            "warning": bool(legacy_open_rows_by_file),
        },
        "dashboard_live_trade_count_source": dashboard_source,
        "performance_trade_count_source": performance_source,
        "mismatch_explanation": explanation,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    _write_json(output_path, payload)
    return payload


def _outcome_key(row):
    trade_id = str(row.get("trade_id") or "").strip()
    if trade_id:
        return trade_id
    return "|".join(
        str(row.get(field) or "").strip().upper()
        for field in ("symbol", "side", "entry", "sl", "target")
    )


def _last_outcome_timestamp(outcome_status, outcomes):
    candidates = []
    for key in ("generated_at_ist", "timestamp_ist", "last_outcome_check", "updated_at"):
        parsed = _parse_timestamp(outcome_status.get(key))
        if parsed:
            candidates.append(parsed)
    for row in outcomes:
        parsed = _parse_timestamp(row.get("closed_at"))
        if parsed:
            candidates.append(parsed)
    return max(candidates) if candidates else None


def _stale_price_dependency(now_ist):
    payload = _read_json_safe(LIVE_PRICE_STATUS_PATH)
    meta = _read_json_safe(LIVE_PRICE_CACHE_META_PATH)
    timestamp = None
    for source in (payload, meta):
        for key in ("generated_at_ist", "timestamp_ist", "last_successful_live_fetch", "cache_last_updated", "updated_at"):
            timestamp = _parse_timestamp(source.get(key))
            if timestamp:
                break
        if timestamp:
            break
    age = _age_seconds(timestamp, now_ist)
    stale = bool(age is None or age > OUTCOME_FRESH_SECONDS)
    return stale, round(age, 3) if age is not None else None


def build_trade_lifecycle_health(
    now=None,
    active_trades_path=ACTIVE_TRADES_CSV,
    outcomes_path=TRADE_OUTCOMES_CSV,
    output_path=TRADE_LIFECYCLE_HEALTH_PATH,
):
    now_ist = as_ist_datetime(now)
    active_rows = _read_csv_rows(active_trades_path)
    outcome_rows = _read_csv_rows(outcomes_path)
    outcome_status = _read_json_safe(OUTCOME_TRACKER_STATUS_PATH)
    open_rows = [row for row in active_rows if _open_status(row)]
    unresolved = [_classified_open_trade(row, now_ist) for row in open_rows]
    active_live = [row for row in unresolved if row["lifecycle_status"] == "OPEN_PENDING"]
    learning_open = [row for row in unresolved if row["lifecycle_status"] == "LEARNING_OPEN"]
    stale_open = [row for row in unresolved if row["lifecycle_status"] in {"STALE_OPEN", "EOD_UNRESOLVED"}]
    eod = [row for row in unresolved if row["lifecycle_status"] == "EOD_UNRESOLVED"]
    missing_levels = [row for row in unresolved if row["lifecycle_status"] == "CLOSED_MANUAL_RECONCILIATION_REQUIRED"]
    outcome_keys = {_outcome_key(row) for row in outcome_rows if _outcome_key(row)}
    open_keys = {_outcome_key(row) for row in open_rows if _outcome_key(row)}
    trade_results_mismatch = bool(open_keys & outcome_keys)
    last_outcome_check = _last_outcome_timestamp(outcome_status, outcome_rows)
    outcome_age = _age_seconds(last_outcome_check, now_ist)
    outcome_tracker_fresh = bool(last_outcome_check and outcome_age <= OUTCOME_FRESH_SECONDS)
    stale_price_dependency, price_age = _stale_price_dependency(now_ist)

    dashboard_live_trade_count = None
    dashboard_mismatch = False
    runtime_status = _read_json_safe(RUNTIME_DIR / "titan_runtime_status.json")
    dashboard_trade_truth = runtime_status.get("dashboard_trade_truth") if isinstance(runtime_status.get("dashboard_trade_truth"), dict) else {}
    if dashboard_trade_truth:
        try:
            dashboard_live_trade_count = int(dashboard_trade_truth.get("live_trades_count"))
        except (TypeError, ValueError):
            dashboard_live_trade_count = None
    if dashboard_live_trade_count is not None:
        dashboard_mismatch = dashboard_live_trade_count != len(active_live)

    reconciliation = _build_trade_lifecycle_reconciliation(
        now_ist,
        active_rows,
        outcome_rows,
        unresolved,
        dashboard_live_trade_count,
        Path(output_path).with_name("trade_lifecycle_reconciliation.json"),
    )

    warnings = []
    if stale_open:
        warnings.append("stale_open_trades")
    if eod:
        warnings.append("eod_unresolved_trades")
    if missing_levels:
        warnings.append("missing_trade_levels")
    if stale_price_dependency:
        warnings.append("stale_price_dependency")
    if not outcome_tracker_fresh:
        warnings.append("outcome_tracker_stale_or_missing")
    if dashboard_mismatch:
        warnings.append("dashboard_live_trade_count_mismatch")
    if trade_results_mismatch:
        warnings.append("trade_results_vs_active_trade_mismatch")
    if reconciliation["manual_reconciliation_required"]["required"]:
        warnings.append("manual_reconciliation_required")

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "overall_status": "WARNING" if warnings else "PASS",
        "open_trades_count": len(open_rows),
        "active_live_trades_count": len(active_live),
        "learning_open_trades_count": len(learning_open),
        "stale_open_trades_count": len(stale_open),
        "unresolved_eod_trades_count": len(eod),
        "missing_levels_count": len(missing_levels),
        "stale_price_dependency": stale_price_dependency,
        "price_dependency_age_seconds": price_age,
        "outcome_tracker_fresh": outcome_tracker_fresh,
        "last_outcome_check": last_outcome_check.isoformat() if last_outcome_check else None,
        "dashboard_live_trade_count": dashboard_live_trade_count,
        "dashboard_mismatch": dashboard_mismatch,
        "trade_results_vs_journal_mismatch": trade_results_mismatch,
        "closed_tp_sl_trades_count": reconciliation["closed_tp_sl_trades"]["count"],
        "manual_reconciliation_required": reconciliation["manual_reconciliation_required"]["required"],
        "trade_lifecycle_reconciliation_path": str(Path(output_path).with_name("trade_lifecycle_reconciliation.json")).replace("\\", "/"),
        "unresolved_trades": unresolved,
        "recommended_action": "MANUAL_REVIEW_UNRESOLVED_TRADES" if unresolved else "NO_OPEN_TRADE_ACTION_REQUIRED",
        "warnings": warnings,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    _write_json(output_path, payload)
    return payload


def run_trade_lifecycle_health_check():
    return build_trade_lifecycle_health()


if __name__ == "__main__":
    print(json.dumps(run_trade_lifecycle_health_check(), indent=2, sort_keys=True))
