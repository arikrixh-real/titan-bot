import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


RUNTIME_DIR = Path("data") / "runtime"
DASHBOARD_SYNC_STATUS_PATH = RUNTIME_DIR / "dashboard_sync_status.json"
PAPER_ENGINE_STATUS_PATH = RUNTIME_DIR / "paper_engine_status.json"
MASTER_BRAIN_STATUS_PATH = RUNTIME_DIR / "master_brain_status.json"
SCANNER_STATUS_PATH = RUNTIME_DIR / "scanner_status.json"
RUNTIME_SNAPSHOTS_PATH = RUNTIME_DIR / "runtime_snapshots.jsonl"
IST = timezone(timedelta(hours=5, minutes=30))


def _timestamp_ist():
    return datetime.now(IST).isoformat()


def _read_json(path):
    try:
        path = Path(path)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _is_active_status(payload):
    if not isinstance(payload, dict):
        return False

    status = str(payload.get("status") or "").upper()
    if not status:
        return False

    inactive_markers = ("STOPPED", "FAILED", "ERROR", "INACTIVE")
    return not any(marker in status for marker in inactive_markers)


def _safe_bool(value, fallback=False):
    return value if isinstance(value, bool) else fallback


def _safe_number(value, default=0):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _paper_account_value(paper_status, key, default=0.0):
    if not isinstance(paper_status, dict):
        return default
    account = paper_status.get("paper_account_summary")
    if not isinstance(account, dict):
        return default
    return _safe_number(account.get(key), default)


def _build_snapshot():
    dashboard_status = _read_json(DASHBOARD_SYNC_STATUS_PATH)
    paper_status = _read_json(PAPER_ENGINE_STATUS_PATH)
    master_brain_status = _read_json(MASTER_BRAIN_STATUS_PATH)
    scanner_status = _read_json(SCANNER_STATUS_PATH)

    summary = {}
    if isinstance(dashboard_status, dict):
        summary = dashboard_status.get("autonomous_runtime_summary") or {}
    if not isinstance(summary, dict):
        summary = {}

    scanner_active = _safe_bool(summary.get("scanner_active"), _is_active_status(scanner_status))
    master_brain_active = _safe_bool(
        summary.get("master_brain_active"),
        _is_active_status(master_brain_status),
    )
    paper_engine_active = _safe_bool(
        summary.get("paper_engine_active"),
        _is_active_status(paper_status),
    )

    attention_reasons = summary.get("attention_reasons")
    if not isinstance(attention_reasons, list):
        attention_reasons = []
    attention_reasons = [str(reason) for reason in attention_reasons if reason]

    fallback_reasons = {
        "scanner_inactive": scanner_active,
        "master_brain_inactive": master_brain_active,
        "paper_engine_inactive": paper_engine_active,
    }
    for reason, active in fallback_reasons.items():
        if not active and reason not in attention_reasons:
            attention_reasons.append(reason)

    snapshot = {
        "timestamp_ist": _timestamp_ist(),
        "runtime_mode": str(summary.get("runtime_mode") or "UNKNOWN"),
        "daemon_alive": _safe_bool(summary.get("daemon_alive"), False),
        "scanner_active": scanner_active,
        "master_brain_active": master_brain_active,
        "paper_engine_active": paper_engine_active,
        "open_paper_positions": _safe_number(
            summary.get("open_paper_positions"),
            _safe_number(paper_status.get("open_positions_count") if isinstance(paper_status, dict) else None),
        ),
        "paper_equity": _safe_number(
            summary.get("paper_equity"),
            _paper_account_value(paper_status, "equity"),
        ),
        "realized_pnl": _paper_account_value(paper_status, "realized_pnl"),
        "unrealized_pnl": _paper_account_value(paper_status, "unrealized_pnl"),
        "needs_attention": _safe_bool(summary.get("needs_attention"), bool(attention_reasons)),
        "attention_reasons": attention_reasons,
    }
    if snapshot["attention_reasons"]:
        snapshot["needs_attention"] = True

    return snapshot


def append_runtime_snapshot(path=RUNTIME_SNAPSHOTS_PATH):
    snapshot = _build_snapshot()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(snapshot, separators=(",", ":"), sort_keys=True))
        file.write("\n")
    return snapshot


def log_runtime_snapshot():
    return append_runtime_snapshot()


if __name__ == "__main__":
    print(json.dumps(append_runtime_snapshot(), separators=(",", ":"), sort_keys=True))
