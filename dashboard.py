import csv
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from runtime_execution_mode import active_execution_mode, write_execution_mode
from tools.refresh_mode_scanner_status import refresh_mode_scanner_status

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

try:
    from utils.market_hours import IST, is_trade_window
except Exception:
    IST = timezone.utc
    is_trade_window = None


ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "data" / "runtime"
MODE_PATH = RUNTIME / "execution_mode.json"

FRESH_SECONDS = {
    "daemon": 180,
    "echo": 3600,
    "ltp": 180,
    "scanner": 900,
    "account": 24 * 3600,
    "news": 6 * 3600,
    "storage": 24 * 3600,
    "worker": 15 * 60,
}

CLASSIC_SCANNER_COUNTER_FIELDS = [
    ("Stocks Checked", ("stocks_checked", "stocks_scanned", "symbols_scanned", "scanned_count", "scan_count")),
    ("Trend Passed", ("trend_passed", "trend_passed_count")),
    ("Momentum Passed", ("momentum_passed", "momentum_passed_count")),
    ("Structure Passed", ("structure_passed", "structure_passed_count")),
    ("Raw Breakout Ready", ("raw_breakout_ready_count", "raw_breakout_ready")),
    ("Qualified Breakout Ready", ("qualified_breakout_ready_count", "qualified_breakout_ready", "breakout_ready_count")),
    ("Final Passed", ("final_passed", "final_passed_count")),
]

HFT_SCANNER_COUNTER_FIELDS = [
    ("Stocks Scanned", ("stocks_scanned", "stocks_checked", "symbols_scanned", "candidates_scanned", "ticks_processed")),
    ("Momentum Continuation", ("momentum_continuation",)),
    ("Pullback Continuation", ("pullback_continuation",)),
    ("Volatility Expansion", ("volatility_expansion",)),
    ("Relative Strength Burst", ("relative_strength_burst",)),
    ("Intraday Range Escape", ("intraday_range_escape",)),
    ("Eligible Signals", ("eligible_signals",)),
    ("Final Passed", ("final_passed", "final_passed_count")),
]


PATHS = {
    "daemon_health": RUNTIME / "daemon_health.json",
    "echo_activity": RUNTIME / "echo_activity.json",
    "git_cleanliness": RUNTIME / "git_cleanliness.json",
    "storage_status": RUNTIME / "storage_status.json",
    "supabase_status": RUNTIME / "supabase_status.json",
    "scanner_status": RUNTIME / "scanner_status.json",
    "scanner_filter_truth": RUNTIME / "scanner_filter_truth_status.json",
    "classic_scanner_status": RUNTIME / "classic_scanner_status.json",
    "classic_mode_scanner_status": RUNTIME / "classic_mode_scanner_status.json",
    "classic_scanner_filter_truth": RUNTIME / "classic_scanner_filter_truth_status.json",
    "hft_scanner_status": ROOT / "data" / "hft_mode" / "hft_scanner_status.json",
    "hft_mode_scanner_status": RUNTIME / "hft_mode_scanner_status.json",
    "hft_scanner_filter_truth": ROOT / "data" / "hft_mode" / "hft_scanner_filter_truth_status.json",
    "worker_health": RUNTIME / "worker_health.json",
    "paper_engine_status": RUNTIME / "paper_engine_status.json",
    "paper_account": ROOT / "data" / "paper_trading" / "paper_account.json",
    "upstox_funds": RUNTIME / "upstox" / "account" / "funds.json",
    "upstox_positions": RUNTIME / "upstox" / "account" / "positions.json",
    "trade_outcomes": ROOT / "data" / "journals" / "trade_outcomes.csv",
    "live_price_status": ROOT / "data" / "live_price_status.json",
    "live_price_cache": ROOT / "data" / "live_price_cache.json",
    "live_price_cache_meta_runtime": RUNTIME / "live_price_cache_meta.json",
    "live_price_cache_meta": ROOT / "data" / "live_price_cache_meta.json",
    "news_pulse": RUNTIME / "news_pulse_status.json",
    "news_intelligence": RUNTIME / "news_intelligence_status.json",
    "hft_health": ROOT / "data" / "hft_mode" / "hft_health.json",
    "hft_stats": ROOT / "data" / "hft_mode" / "hft_stats.json",
    "hft_closed_summary": ROOT / "data" / "hft_mode" / "hft_closed_summary.json",
    "hft_outcomes": ROOT / "data" / "hft_mode" / "hft_outcomes.json",
}


st.set_page_config(
    page_title="TITAN Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def now_ist():
    return datetime.now(IST)


def setup_live_refresh():
    if st_autorefresh is not None:
        st_autorefresh(interval=1000, key="titan_live_refresh")


def fallback_live_rerun():
    if st_autorefresh is None:
        time.sleep(1)
        st.rerun()


def read_json(path, default=None):
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if data is not None else default
    except Exception:
        return default


def read_csv_rows(path):
    try:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except Exception:
        return []


def parse_dt(value):
    if value in (None, "", "null"):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=IST)
        except Exception:
            return None
    text = str(value).strip()
    if not text:
        return None
    for suffix in ("Z",):
        if text.endswith(suffix):
            text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except Exception:
                dt = None
        if dt is None:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def payload_time(payload):
    if not isinstance(payload, dict):
        return None
    for key in (
        "timestamp_ist",
        "generated_at_ist",
        "updated_at_ist",
        "last_updated_ist",
        "scan_finished_at_ist",
        "generated_at",
        "timestamp",
        "last_update",
        "latest_news_timestamp_ist",
        "active_run_started_at",
        "last_finished_at",
        "last_started_at",
        "updated_at",
        "last_updated",
    ):
        dt = parse_dt(payload.get(key))
        if dt:
            return dt
    return None


def file_time(path):
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=IST)
    except Exception:
        return None


def age_seconds(dt):
    if not dt:
        return None
    return max(0, (now_ist() - dt).total_seconds())


def is_fresh(payload, path=None, max_age=300):
    dt = payload_time(payload)
    if dt is None and path is not None:
        dt = file_time(path)
    age = age_seconds(dt)
    return age is not None and age <= max_age


def status_text(value):
    text = str(value or "").strip().upper()
    if text in {"RUNNING", "OK", "PASS", "CONNECTED", "READY", "ACTIVE", "CLEAN", "HEALTHY"}:
        return "ACTIVE"
    if text in {"STOPPING", "STOPPED", "OFFLINE", "ERROR", "FAIL", "FAILED", "LOCKED", "DISABLED"}:
        return "INACTIVE"
    if text in {"STALE", "DEGRADED", "WARNING", "WARN", "DIRTY"}:
        return "STALE"
    return "UNKNOWN"


def fmt_number(value):
    if value in (None, "", "UNKNOWN", "STALE"):
        return "—"
    try:
        number = float(value)
    except Exception:
        return str(value)
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def fmt_money(value):
    if value in (None, "", "UNKNOWN", "STALE"):
        return "—"
    try:
        number = float(value)
        sign = "-" if number < 0 else ""
        return f"{sign}₹{abs(number):,.2f}"
    except Exception:
        return "—"


def fmt_pct(value):
    if value in (None, "", "UNKNOWN", "STALE"):
        return "—"
    try:
        return f"{float(value):.2f}%"
    except Exception:
        return "—"


def first_number(payload, keys):
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except Exception:
            continue
    return None


def css_class(value):
    text = str(value or "").upper()
    if text in {"ACTIVE", "CLEAN"}:
        return "good"
    if text in {"DIRTY", "STALE", "CLOSED", "WAITING", "WAITING_FOR_MODE", "SCHEDULED"}:
        return "warn"
    if text in {"INACTIVE", "DISABLED"}:
        return "bad"
    return "muted"


def html_escape(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def metric_tile(label, value, value_class=None, subtext=None):
    value_class = value_class or css_class(value)
    sub_class = "clock" if value_class == "clock" else css_class(subtext)
    sub = f"<div class='tile-sub {sub_class}'>{html_escape(subtext)}</div>" if subtext else ""
    return (
        "<div class='metric-tile'>"
        f"<div class='tile-label'>{html_escape(label)}</div>"
        f"<div class='tile-value {value_class}'>{html_escape(value)}</div>"
        f"{sub}</div>"
    )


def card_html(title, body, extra_class=""):
    return (
        f"<section class='dash-card {extra_class}'>"
        f"<div class='section-title'>{html_escape(title)}</div>"
        f"{body}</section>"
    )


def metric_grid_card(title, items, columns=4, extra_class=""):
    tiles = "".join(metric_tile(*item) for item in items)
    return card_html(title, f"<div class='metric-grid cols-{columns}'>{tiles}</div>", extra_class)


def render_metric_grid_card(title, items, columns=4, extra_class=""):
    st.markdown(metric_grid_card(title, items, columns, extra_class), unsafe_allow_html=True)


def atomic_write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        try:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except Exception:
            pass


def normalize_mode(value):
    text = str(value or "").strip().upper()
    if text in {"HFT", "HFT_MODE", "HIGH_FREQUENCY", "HIGH_FREQUENCY_TRADING"}:
        return "HFT"
    return "CLASSIC"


def read_mode():
    return active_execution_mode()


def write_mode(mode):
    mode = normalize_mode(mode)
    write_execution_mode(mode)
    refresh_mode_scanner_status()


def mode_control_card_html(active_mode):
    classic_class = "active" if active_mode == "CLASSIC" else "inactive"
    hft_class = "active" if active_mode == "HFT" else "inactive"
    body = f"""
    <div class="mode-current">
      <div class="tile-label">Current Active Mode</div>
      <div class="tile-value good">{html_escape(active_mode)}</div>
    </div>
    <div class="mode-pill static" role="group" aria-label="Mode Control">
      <span class="mode-option {classic_class}">CLASSIC</span>
      <span class="mode-option {hft_class}">HFT</span>
    </div>
    """
    return card_html("MODE CONTROL", body, "mode-control-card")


def render_mode_control(active_mode):
    with st.container(key="mode_control_shell"):
        st.markdown(mode_control_card_html(active_mode), unsafe_allow_html=True)
        mode_cols = st.columns(2)
        with mode_cols[0]:
            if st.button("CLASSIC", key="mode_switch_classic", disabled=active_mode == "CLASSIC", use_container_width=True):
                write_mode("CLASSIC")
                st.rerun()
        with mode_cols[1]:
            if st.button("HFT", key="mode_switch_hft", disabled=active_mode == "HFT", use_container_width=True):
                write_mode("HFT")
                st.rerun()


def market_status():
    if is_trade_window is None:
        return "UNKNOWN"
    try:
        return "ACTIVE" if bool(is_trade_window(now_ist())) else "CLOSED"
    except Exception:
        return "UNKNOWN"


def titan_state(daemon):
    if not isinstance(daemon, dict):
        return "UNKNOWN"
    if not is_fresh(daemon, PATHS["daemon_health"], FRESH_SECONDS["daemon"]):
        return "INACTIVE"
    return "ACTIVE" if status_text(daemon.get("status")) == "ACTIVE" else "INACTIVE"


def echo_state(echo):
    if not isinstance(echo, dict):
        return "UNKNOWN"
    if not is_fresh(echo, PATHS["echo_activity"], FRESH_SECONDS["echo"]):
        return "INACTIVE"
    return "ACTIVE" if status_text(echo.get("status")) == "ACTIVE" else "INACTIVE"


def vps_status(daemon):
    if not isinstance(daemon, dict):
        return "UNKNOWN"
    if not is_fresh(daemon, PATHS["daemon_health"], FRESH_SECONDS["daemon"]):
        return "STALE"
    return "ACTIVE" if status_text(daemon.get("status")) == "ACTIVE" else "INACTIVE"


def github_status(git):
    if not isinstance(git, dict):
        return "UNKNOWN"
    dirty = git.get("dirty") or git.get("is_dirty") or git.get("dirty_file_count")
    status = str(git.get("status") or "").upper()
    if status == "DIRTY" or dirty is True:
        return "DIRTY"
    try:
        if float(dirty) > 0:
            return "DIRTY"
    except Exception:
        pass
    if status in {"CLEAN", "OK", "PASS"} or dirty is False:
        return "CLEAN"
    return "UNKNOWN"


def ltp_status(payloads):
    for name in ("live_price_status", "live_price_cache_meta_runtime", "live_price_cache_meta", "live_price_cache"):
        payload = payloads.get(name)
        path = PATHS[name]
        if not isinstance(payload, (dict, list)):
            continue
        fresh = is_fresh(payload if isinstance(payload, dict) else {}, path, FRESH_SECONDS["ltp"])
        if fresh:
            if isinstance(payload, dict):
                raw_status = str(payload.get("status") or "").upper()
                if raw_status in {"ACTIVE", "OK", "PARTIAL", "CONNECTED"}:
                    return "ACTIVE"
                if raw_status in {"INACTIVE", "OFFLINE", "FAILED", "ERROR"}:
                    return "INACTIVE"
            return "ACTIVE"
        return "STALE"
    return "UNKNOWN"


def storage_used(storage, supabase):
    if isinstance(storage, dict):
        used = first_number(storage, ("used_percent", "percent_used", "storage_used_percent"))
        if used is not None:
            return fmt_pct(used)
        if storage.get("used"):
            return str(storage.get("used"))
    if isinstance(supabase, dict):
        used = first_number(supabase, ("used_percent", "storage_used_percent", "database_used_percent"))
        if used is not None:
            return fmt_pct(used)
    return "—"


def freshest_account(payloads):
    paper_candidates = []
    paper = payloads.get("paper_account")
    if isinstance(paper, dict):
        dt = payload_time(paper) or parse_dt(paper.get("daily_start_date"))
        paper_candidates.append(("paper_account", paper, dt, PATHS["paper_account"], "PAPER"))
    engine = payloads.get("paper_engine_status")
    if isinstance(engine, dict):
        paper_candidates.append(("paper_engine_status", engine, payload_time(engine), PATHS["paper_engine_status"], "PAPER"))
    valid_paper = [item for item in paper_candidates if item[2] is not None]
    fresh_paper = [
        item for item in valid_paper
        if age_seconds(item[2]) is not None and age_seconds(item[2]) <= FRESH_SECONDS["account"]
    ]
    fresh_paper.sort(key=lambda item: item[2], reverse=True)

    upstox_candidates = []
    for name in ("upstox_funds", "upstox_positions"):
        payload = payloads.get(name)
        if isinstance(payload, dict):
            dt = payload_time(payload)
            status = str(payload.get("status") or "").upper()
            upstox_candidates.append((name, payload, dt, PATHS[name], status, "UPSTOX"))
    fresh_upstox = [
        item for item in upstox_candidates
        if item[2] is not None and age_seconds(item[2]) is not None and age_seconds(item[2]) <= FRESH_SECONDS["account"]
    ]
    active_upstox = [item for item in fresh_upstox if item[4] == "ACTIVE"]
    if active_upstox:
        active_upstox.sort(key=lambda item: item[2], reverse=True)
        name, payload, _dt, path, _status, source_label = active_upstox[0]
        summary = payload.get("account_summary") if isinstance(payload.get("account_summary"), dict) else payload
        balance = first_number(summary, ("available_margin", "equity", "account_balance", "available_funds", "balance"))
        if balance not in (None, 0) or not fresh_paper:
            return (name, payload, path, source_label), "ACTIVE"
    if fresh_paper:
        name, payload, _dt, path, source_label = fresh_paper[0]
        return (name, payload, path, source_label), "ACTIVE"
    if not valid_paper:
        auth_required = [item for item in fresh_upstox if item[4] in {"AUTH_REQUIRED", "INACTIVE"}]
        if auth_required:
            return None, auth_required[0][4]
        return None, "UNKNOWN"
    valid_paper.sort(key=lambda item: item[2], reverse=True)
    name, payload, dt, path, source_label = valid_paper[0]
    if age_seconds(dt) is None or age_seconds(dt) > FRESH_SECONDS["account"]:
        return None, "STALE"
    return (name, payload, path, source_label), "ACTIVE"


def account_metrics(payloads):
    source, status = freshest_account(payloads)
    if status != "ACTIVE" or not source:
        return status, ("—", "—", "—", "—"), "UNKNOWN"
    _, payload, _, source_label = source
    summary = payload.get("paper_account_summary") if isinstance(payload.get("paper_account_summary"), dict) else payload.get("account_summary") if isinstance(payload.get("account_summary"), dict) else payload
    if source_label == "UPSTOX":
        balance = first_number(summary, ("available_margin", "equity", "account_balance", "available_funds", "balance"))
    else:
        balance = first_number(summary, ("current_balance", "equity", "account_balance", "balance"))
    current_pnl = first_number(summary, ("open_pnl", "unrealized_pnl", "current_pnl"))
    daily_pnl = first_number(summary, ("daily_pnl", "realized_pnl", "total_realized_pnl"))
    closed_pnl = first_number(summary, ("closed_pnl", "realized_pnl", "total_realized_pnl"))
    if current_pnl is None:
        current_pnl = closed_pnl
    pct = None
    if balance not in (None, 0) and daily_pnl is not None:
        pct = (daily_pnl / balance) * 100.0
    return status, (fmt_money(balance), fmt_money(current_pnl), fmt_money(daily_pnl), fmt_pct(pct)), source_label


def is_synthetic(row):
    text = " ".join(str(row.get(k, "")) for k in ("source", "trade_id", "paper_trade_id", "test_trade")).upper()
    return "SYNTHETIC" in text or str(row.get("test_trade", "")).strip().upper() in {"TRUE", "1", "YES"}


def trade_performance(rows, mode=None):
    total = wins = losses = 0
    mode_columns = ("mode", "trading_mode", "execution_mode", "active_mode")
    has_mode_column = any(any(col in row for col in mode_columns) for row in rows)
    if mode and not has_mode_column:
        return None
    for row in rows:
        if is_synthetic(row):
            continue
        if mode:
            raw_mode = next((row.get(col) for col in mode_columns if row.get(col)), "")
            if not raw_mode:
                continue
            row_mode = normalize_mode(raw_mode)
            if row_mode != mode:
                continue
        outcome = str(row.get("outcome") or row.get("result") or "").strip().upper()
        if outcome not in {"TP", "WIN", "WON", "SL", "LOSS", "LOST"}:
            continue
        total += 1
        if outcome in {"TP", "WIN", "WON"}:
            wins += 1
        else:
            losses += 1
    accuracy = (wins / total * 100.0) if total else None
    return {"total": total, "wins": wins, "losses": losses, "accuracy": accuracy, "has_mode_column": has_mode_column}


def news_count(payloads):
    candidates = []
    for name in ("news_pulse", "news_intelligence"):
        payload = payloads.get(name)
        if not isinstance(payload, dict):
            continue
        count = first_number(payload, ("item_count", "article_count", "news_count", "headline_count"))
        if count is not None:
            candidates.append((payload_time(payload), count))
    candidates = [item for item in candidates if item[0] is not None and age_seconds(item[0]) <= FRESH_SECONDS["news"]]
    if not candidates:
        return "—"
    candidates.sort(key=lambda item: item[0], reverse=True)
    return fmt_number(candidates[0][1])


def news_source_status(payloads):
    statuses = []
    for name in ("news_pulse", "news_intelligence"):
        payload = payloads.get(name)
        if not isinstance(payload, dict):
            continue
        dt = payload_time(payload)
        if dt is None:
            statuses.append("UNKNOWN")
        elif age_seconds(dt) <= FRESH_SECONDS["news"]:
            statuses.append("ACTIVE")
        else:
            statuses.append("STALE")
    if "ACTIVE" in statuses:
        return "ACTIVE"
    if "STALE" in statuses:
        return "STALE"
    return "—"


def scanner_counts(scanner, truth, active_mode, target_mode):
    source = scanner_source_for_mode(target_mode, scanner, truth)
    source = {**source, "mode": normalize_mode(target_mode)}
    if source["health"] != "LIVE":
        return source
    payload = source["payload"]
    truth_counts = source.get("truth_counts") or {}
    metrics = []
    for label, keys in source["fields"]:
        value = first_number(truth_counts, keys) or first_number(payload, keys)
        metrics.append((label, value))
    return {**source, "metrics": metrics}


def source_health_html(items):
    chips = []
    for label, value in items:
        chips.append(
            "<div class='source-chip'>"
            f"<span>{html_escape(label)}</span>"
            f"<strong class='{css_class(value)}'>{html_escape(value)}</strong>"
            "</div>"
        )
    return "<div class='source-health-strip'>" + "".join(chips) + "</div>"


def readable_key(key):
    return str(key).replace("_", " ").strip().title()


def scanner_mode(payload):
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("current_mode") or payload.get("mode") or payload.get("scan_mode") or payload.get("scanner_mode") or "").upper()


def scanner_field_definitions(mode):
    return HFT_SCANNER_COUNTER_FIELDS if normalize_mode(mode) == "HFT" else CLASSIC_SCANNER_COUNTER_FIELDS


def scanner_field_candidates(payload, mode):
    if not isinstance(payload, dict):
        return []
    fields = []
    for label, keys in scanner_field_definitions(mode):
        if any(key in payload for key in keys):
            fields.append((label, keys))
    if fields:
        return fields
    for key, value in payload.items():
        key_text = str(key).lower()
        if isinstance(value, (int, float)) and (
            "passed" in key_text or "scanned" in key_text or "checked" in key_text or "qualified" in key_text
        ):
            fields.append((readable_key(key), (key,)))
    return fields


def scanner_source_for_mode(mode, generic_scanner=None, generic_truth=None):
    mode = normalize_mode(mode)
    if mode == "CLASSIC":
        candidates = [
            ("classic_scanner_status", "classic_scanner_filter_truth"),
        ]
    else:
        candidates = [
            ("hft_mode_scanner_status", "hft_scanner_filter_truth"),
        ]
    for payload_name, truth_name in candidates:
        path = PATHS[payload_name]
        payload = read_json(path, None)
        if not isinstance(payload, dict):
            continue
        fields = scanner_field_candidates(payload, mode)
        truth = read_json(PATHS[truth_name], {}) if truth_name in PATHS else {}
        truth_counts = truth.get("exact_counts") if isinstance(truth, dict) and isinstance(truth.get("exact_counts"), dict) else {}
        payload_status = str(payload.get("status") or "").upper()
        if payload_status == "INACTIVE":
            return {"health": "INACTIVE", "payload": payload, "fields": fields, "source_name": payload_name, "truth_counts": truth_counts}
        if payload_status == "UNKNOWN":
            return {"health": "MISSING", "payload": payload, "fields": fields, "source_name": payload_name, "truth_counts": truth_counts}
        if not fields:
            return {"health": "MISSING", "payload": payload, "fields": [], "source_name": payload_name, "truth_counts": truth_counts}
        if payload_status == "STALE" or not is_fresh(payload, path, FRESH_SECONDS["scanner"]):
            return {"health": "STALE", "payload": payload, "fields": fields, "source_name": payload_name, "truth_counts": truth_counts}
        return {"health": "LIVE", "payload": payload, "fields": fields, "source_name": payload_name, "truth_counts": truth_counts}

    return {"health": "MISSING", "payload": None, "fields": [], "source_name": None, "truth_counts": {}}


def stocks_scanned(scanner, active_mode):
    counts = scanner_counts(scanner, {}, active_mode, active_mode)
    if isinstance(counts, dict):
        if counts.get("health") == "STALE":
            return "STALE"
        if counts.get("health") == "LIVE":
            for label, value in counts.get("metrics", []):
                if label in {"Stocks Checked", "Stocks Scanned"}:
                    return fmt_number(value)
    return "—"


def worker_engines(worker_health, source_path=None):
    if not isinstance(worker_health, dict):
        return []
    source_fresh = is_fresh({}, source_path, FRESH_SECONDS["worker"]) if source_path else False
    rows = []
    for key, payload in worker_health.items():
        if not isinstance(payload, dict):
            continue
        name = str(payload.get("task") or key).strip()
        if not name:
            continue
        raw = str(payload.get("status") or "").upper()
        fresh = source_fresh or is_fresh(payload, None, FRESH_SECONDS["worker"])
        if not fresh:
            state = "STALE"
        elif raw in {"RUNNING", "ACTIVE"}:
            state = "ACTIVE"
        elif raw == "WAITING_FOR_MODE":
            state = "WAITING"
        else:
            state = "INACTIVE"
        reason = engine_reason(payload, raw)
        rows.append({"name": name, "state": state, "reason": reason})
    return sorted(rows, key=lambda item: (0 if item["state"] == "ACTIVE" else 1, item["name"]))


def engine_reason(payload, raw_status):
    reason_keys = ("reason", "skip_reason", "status_reason", "source_status", "last_timeout_reason")
    reason_values = {raw_status}
    for key in reason_keys:
        value = payload.get(key)
        if value not in (None, ""):
            reason_values.add(str(value).upper())
    for expected in ("WAITING_FOR_MODE", "OFF_MARKET", "DISABLED", "SCHEDULED"):
        if any(expected in value for value in reason_values):
            return expected
    return ""


def engine_tile_html(engine):
    reason = f"<div class='engine-reason'>{html_escape(engine['reason'])}</div>" if engine.get("reason") else ""
    return (
        "<div class='engine-tile'>"
        f"<div class='engine-name'>{html_escape(engine['name'])}</div>"
        f"<div class='engine-state {css_class(engine['state'])}'>{engine['state']}</div>"
        f"{reason}</div>"
    )


def render_performance(title, perf, total_label="Total Trades"):
    st.markdown(performance_card_html(title, perf, total_label), unsafe_allow_html=True)


def performance_card_html(title, perf, total_label="Total Trades"):
    if perf is None:
        values = [(total_label, "—", "muted"), ("Wins", "—", "muted"), ("Losses", "—", "muted"), ("Accuracy", "—", "muted")]
    else:
        values = [
            (total_label, fmt_number(perf["total"]), "text"),
            ("Wins", fmt_number(perf["wins"]), "good"),
            ("Losses", fmt_number(perf["losses"]), "bad"),
            ("Accuracy", fmt_pct(perf["accuracy"]), "warn"),
        ]
    return metric_grid_card(title, [(label, value, cls) for label, value, cls in values], columns=4)


def render_scanner_card(title, counts):
    st.markdown(scanner_card_html(title, counts), unsafe_allow_html=True)


def scanner_card_html(title, counts):
    if not isinstance(counts, dict):
        counts = {"health": "MISSING", "metrics": []}
    health = str(counts.get("health") or "MISSING").upper()
    health_class = "good" if health == "LIVE" else "warn" if health == "STALE" else "bad" if health == "INACTIVE" else "muted"
    metrics = counts.get("metrics") if isinstance(counts.get("metrics"), list) else []
    metric_values = {label: value for label, value in metrics}
    labels = [label for label, _ in scanner_field_definitions(counts.get("mode"))]
    if health == "LIVE":
        tiles = [(label, fmt_number(metric_values.get(label)), "text" if metric_values.get(label) is not None else "muted") for label in labels]
    elif health == "STALE":
        tiles = [(label, "STALE", "warn") for label in labels]
    else:
        tiles = [(label, "—", "muted") for label in labels]
    body = f"<div class='source-health {health_class}'>{health}</div>"
    body += f"<div class='metric-grid cols-4'>{''.join(metric_tile(*tile) for tile in tiles)}</div>"
    return card_html(title, body, "scanner-card")


def load_payloads():
    return {name: read_json(path, None) for name, path in PATHS.items() if path.suffix == ".json"}


def render_dashboard():
    refresh_now = now_ist()
    print(f"dashboard_rerun_at={refresh_now.isoformat()}")
    payloads = load_payloads()
    rows = read_csv_rows(PATHS["trade_outcomes"])
    active_mode = read_mode()

    daemon = payloads.get("daemon_health")
    echo = payloads.get("echo_activity")
    git = payloads.get("git_cleanliness")
    storage = payloads.get("storage_status")
    supabase = payloads.get("supabase_status")
    scanner = payloads.get("scanner_status")
    truth = payloads.get("scanner_filter_truth")
    worker_health = payloads.get("worker_health")

    st.markdown(STYLE, unsafe_allow_html=True)

    market = market_status()
    st.markdown(
        f"""
        <main class="dashboard-shell">
        <header class="topbar">
          <div>
            <div class="title">TITAN TRADING SYSTEM - DASHBOARD</div>
            <div class="subtitle">Single Page Control Console</div>
          </div>
          <div class="header-status">
            <div class="header-label">Market Status</div>
            <div class="header-value {css_class(market)}">{market}</div>
            <div class="header-time">LIVE REFRESH: 1s</div>
            <div class="header-time">LAST REFRESH: {refresh_now.strftime('%H:%M:%S')}</div>
            <div class="heartbeat">DASHBOARD HEARTBEAT: <span class="good">RUNNING</span></div>
            <div class="heartbeat">TICK: {refresh_now.strftime('%S')}</div>
          </div>
        </header>
        """,
        unsafe_allow_html=True,
    )

    storage_value = storage_used(storage, supabase)
    storage_class = "cyan" if storage_value not in {"—", "STALE", "UNKNOWN"} else "warn" if storage_value == "STALE" else "muted"
    row1 = [
        ("TITAN STATE", titan_state(daemon)),
        ("ECHO STATE", echo_state(echo)),
        ("VPS STATUS", vps_status(daemon)),
        ("GITHUB STATUS", github_status(git)),
        ("UPSTOX LTP STATE", ltp_status(payloads)),
        ("DATABASE STORAGE", storage_value, storage_class),
        ("DATE & CLOCK", refresh_now.strftime("%d %b %Y"), "clock", refresh_now.strftime("%I:%M:%S %p")),
    ]
    render_metric_grid_card("SYSTEM STATUS", row1, columns=7)

    account_status, account, account_source = account_metrics(payloads)
    render_metric_grid_card(
        "ACCOUNT SUMMARY",
        [
            ("Account Balance", account[0], "text" if account[0] != "—" else css_class(account_status), account_status if account_status != "ACTIVE" else None),
            ("Current PNL", account[1], "good" if not account[1].startswith("-") and account[1] != "—" else "bad" if account[1].startswith("-") else "muted"),
            ("Daily PNL", account[2], "good" if not account[2].startswith("-") and account[2] != "—" else "bad" if account[2].startswith("-") else "muted"),
            ("Percentage", account[3], "warn" if account[3] != "—" else css_class(account_status), f"ACCOUNT SOURCE: {account_source}" if account_status == "ACTIVE" else account_status),
        ],
        columns=4,
    )

    overall = trade_performance(rows)
    render_performance("OVERALL TRADING PERFORMANCE", overall, total_label="Total Trades Taken")

    news_scan_card = metric_grid_card(
        "NEWS & SCAN OVERVIEW",
        [
            ("Total Stocks Scanned", stocks_scanned(scanner, active_mode)),
            ("No. of News Gathered", news_count(payloads)),
        ],
        columns=2,
    )
    mode_col, news_col = st.columns(2)
    with mode_col:
        render_mode_control(active_mode)
    with news_col:
        st.markdown(news_scan_card, unsafe_allow_html=True)

    classic_counts = scanner_counts(scanner, truth, active_mode, "CLASSIC")
    hft_counts = scanner_counts(scanner, truth, active_mode, "HFT")
    st.markdown(
        source_health_html(
            [
                ("Account Source", account_source if account_status == "ACTIVE" else account_status),
                ("Classic Scanner Source", classic_counts.get("health", "MISSING") if isinstance(classic_counts, dict) else "MISSING"),
                ("HFT Scanner Source", hft_counts.get("health", "MISSING") if isinstance(hft_counts, dict) else "MISSING"),
                ("News Source", news_source_status(payloads)),
                ("LTP Source", ltp_status(payloads)),
            ]
        ),
        unsafe_allow_html=True,
    )

    mode_has_column = overall.get("has_mode_column") if isinstance(overall, dict) else False
    classic_perf = trade_performance(rows, "CLASSIC") if mode_has_column else None
    hft_perf = trade_performance(rows, "HFT") if mode_has_column else None
    st.markdown(
        "<div class='dash-row two'>"
        + performance_card_html("CLASSIC MODE PERFORMANCE", classic_perf)
        + performance_card_html("HFT MODE PERFORMANCE", hft_perf)
        + "</div>",
        unsafe_allow_html=True,
    )

    classic_scanner = scanner_card_html("CLASSIC MODE SCANNER FILTERS", classic_counts)
    hft_scanner = scanner_card_html("HFT MODE SCANNER FILTERS", hft_counts)
    st.markdown(
        f"<div class='dash-row two scanner-row'>{classic_scanner}{hft_scanner}</div>",
        unsafe_allow_html=True,
    )

    engines = worker_engines(worker_health, PATHS["worker_health"])
    active_engines = [engine for engine in engines if engine["state"] == "ACTIVE"]
    inactive_engines = [engine for engine in engines if engine["state"] != "ACTIVE"]
    active_count = len(active_engines)
    if engines:
        if st.session_state.get("engines_state_tab") not in {"ACTIVE", "INACTIVE"}:
            st.session_state.engines_state_tab = "ACTIVE"
        with st.container(key="engines_state_card"):
            st.markdown("<div class='section-title'>ENGINES STATE</div>", unsafe_allow_html=True)
            st.markdown(
                f"<div class='engine-summary'>Active: <span>{active_count} / {len(engines)}</span></div>",
                unsafe_allow_html=True,
            )
            tab_active, tab_inactive = st.columns(2)
            with tab_active:
                if st.button(
                    "ACTIVE ENGINES",
                    key="engine_tab_active",
                    disabled=st.session_state.engines_state_tab == "ACTIVE",
                    use_container_width=True,
                ):
                    st.session_state.engines_state_tab = "ACTIVE"
                    st.rerun()
            with tab_inactive:
                if st.button(
                    "INACTIVE / WAITING",
                    key="engine_tab_inactive",
                    disabled=st.session_state.engines_state_tab == "INACTIVE",
                    use_container_width=True,
                ):
                    st.session_state.engines_state_tab = "INACTIVE"
                    st.rerun()
            selected_engines = active_engines if st.session_state.engines_state_tab == "ACTIVE" else inactive_engines
            engine_html = "".join(engine_tile_html(engine) for engine in selected_engines)
            st.markdown(f"<div class='engine-grid'>{engine_html}</div>", unsafe_allow_html=True)
    else:
        render_metric_grid_card("ENGINES STATE", [("Engines Active", "UNKNOWN", "muted")], columns=1, extra_class="engine-card")

    st.markdown("</main>", unsafe_allow_html=True)


def main():
    if st_autorefresh is not None:
        setup_live_refresh()
        render_dashboard()
    elif hasattr(st, "fragment"):
        st.fragment(run_every="1s")(render_dashboard)()
    else:
        render_dashboard()
        fallback_live_rerun()


STYLE = """
<style>
section[data-testid="stSidebar"], [data-testid="stSidebar"] {display:none !important;}
* {box-sizing:border-box;}
.block-container {max-width: 100% !important; padding: 18px 22px 28px !important;}
body, .stApp {background:#020811; color:#eaf5ff; font-family: Inter, "Segoe UI", Arial, sans-serif;}
div[data-testid="stVerticalBlock"] {gap: 18px;}
.dashboard-shell {max-width:1600px; width:100%; margin:0 auto; display:block;}
.topbar {
  display:flex; align-items:center; justify-content:space-between; gap:24px;
  padding:18px 20px; margin-bottom:16px; border:1px solid #14324a;
  border-radius:14px; background:linear-gradient(180deg,#091827 0%,#061321 100%);
  box-shadow:0 14px 34px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.04);
}
.title {font-size:27px; font-weight:900; letter-spacing:0; color:#f4fbff;}
.subtitle {font-size:13px; color:#7fa0b8; margin-top:4px; font-weight:650;}
.header-status {text-align:right; min-width:260px;}
.header-label {font-size:11px; color:#7894a8; text-transform:uppercase; font-weight:800;}
.header-value {font-size:23px; font-weight:950; margin-top:2px;}
.header-time {font-size:12px; color:#6edcff; margin-top:4px; font-weight:700; opacity:.78;}
.heartbeat {font-size:11px; color:#8fb3c8; margin-top:5px; font-weight:850; letter-spacing:.03em;}
.source-health-strip {
  display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:12px; margin:18px 0 0;
}
.source-chip {
  border:1px solid #14324a; border-radius:10px; background:#061321;
  padding:10px 12px; min-height:46px; display:flex; align-items:center; justify-content:space-between; gap:10px;
}
.source-chip span {font-size:11px; color:#7894a8; text-transform:uppercase; font-weight:850;}
.source-chip strong {font-size:13px; font-weight:950;}
.dash-card {
  border:1px solid #14324a; border-radius:14px; background:#071522;
  padding:16px; min-height:112px; width:100%;
  box-shadow:0 10px 26px rgba(0,0,0,.24), inset 0 1px 0 rgba(255,255,255,.035);
}
.dash-row {
  display:grid; width:100%; row-gap:18px; column-gap:16px; margin:18px 0 0;
}
.dash-row.two {grid-template-columns:repeat(2,minmax(0,1fr));}
.scanner-row {margin-bottom:18px;}
.dashboard-shell > .dash-card {margin-top:18px;}
.dashboard-shell > .dash-card:first-of-type {margin-top:0;}
.dashboard-shell > div[data-testid="stMarkdownContainer"] + div[data-testid="stMarkdownContainer"] {margin-top:18px;}
.dashboard-shell a {text-decoration:none;}
.dashboard-shell a:visited {color:inherit;}
.section-title {
  color:#32d9ff; text-transform:uppercase; letter-spacing:.04em; font-size:14px;
  font-weight:900; margin:0 0 13px;
}
.metric-grid {display:grid; gap:14px;}
.cols-1 {grid-template-columns:1fr;}
.cols-2 {grid-template-columns:repeat(2,minmax(0,1fr));}
.cols-4 {grid-template-columns:repeat(4,minmax(0,1fr));}
.cols-7 {grid-template-columns:repeat(7,minmax(0,1fr));}
.metric-tile {
  min-height:78px; border:1px solid #173a56; border-radius:12px; background:#091827;
  padding:12px 13px; display:flex; flex-direction:column; justify-content:center;
}
.tile-label {
  font-size:11px; line-height:1.2; color:#7f98aa; text-transform:uppercase;
  font-weight:850; margin-bottom:7px;
}
.tile-value {
  font-size:25px; line-height:1.08; font-weight:950; overflow-wrap:anywhere;
}
.tile-sub {font-size:11px; margin-top:6px; font-weight:800;}
.mode-control-card {min-height:174px; padding-bottom:16px;}
.mode-current {
  border:1px solid #173a56; border-radius:12px; background:#091827;
  padding:12px 13px; margin-bottom:10px;
}
.mode-pill {
  display:grid; grid-template-columns:1fr 1fr; gap:6px; width:100%;
  border:1px solid #173a56; border-radius:999px; background:#040d17; padding:6px;
}
.mode-option {
  display:flex; align-items:center; justify-content:center; min-height:44px; width:100%;
  border-radius:999px; font-size:14px; font-weight:950; letter-spacing:.02em;
  white-space:nowrap; overflow:visible; text-overflow:clip; color:#8ea9bc;
  background:#081522; border:1px solid transparent;
}
.mode-option.inactive {color:#839aad; background:#081522;}
.mode-option.active {
  color:#eaffff; background:linear-gradient(180deg,#0f4c5e,#0a3548);
  border-color:#32d9ff; box-shadow:0 0 0 1px rgba(50,217,255,.18) inset, 0 0 24px rgba(47,224,139,.08);
}
.st-key-mode_control_shell {
  position:relative;
}
.st-key-mode_control_shell div[data-testid="stHorizontalBlock"]:has(.st-key-mode_switch_classic),
.st-key-mode_control_shell div[data-testid="stHorizontalBlock"]:has(.st-key-mode_switch_hft) {
  position:absolute; left:16px; right:16px; bottom:16px; z-index:5; margin:0;
}
.st-key-mode_control_shell .st-key-mode_switch_classic button,
.st-key-mode_control_shell .st-key-mode_switch_hft button {
  min-height:58px; width:100%; border-radius:999px; opacity:0;
  color:transparent; background:transparent; border-color:transparent; box-shadow:none;
  cursor:pointer;
}
.st-key-mode_control_shell .st-key-mode_switch_classic button:disabled,
.st-key-mode_control_shell .st-key-mode_switch_hft button:disabled {
  cursor:default;
}
.source-health {
  display:inline-flex; align-items:center; min-height:28px; margin-bottom:12px;
  border:1px solid #173a56; border-radius:999px; background:#081522;
  padding:5px 10px; font-size:11px; font-weight:950; letter-spacing:.04em;
}
.scanner-card {min-height:310px; display:flex; flex-direction:column;}
.scanner-card .metric-grid {grid-template-columns:repeat(4,minmax(0,1fr)); align-items:stretch; flex:1;}
.scanner-card .metric-tile {min-height:84px;}
.engine-card {margin-top:0;}
.st-key-engines_state_card {
  border:1px solid #14324a; border-radius:14px; background:#071522;
  padding:16px; min-height:112px; width:100%; margin-top:0;
  box-shadow:0 10px 26px rgba(0,0,0,.24), inset 0 1px 0 rgba(255,255,255,.035);
}
.st-key-engines_state_card div[data-testid="stVerticalBlock"] {gap:10px;}
.st-key-engine_tab_active button,
.st-key-engine_tab_inactive button {
  min-height:34px; border-radius:8px; border:1px solid #173a56;
  background:#081522; color:#c8d9e8; font-size:12px; font-weight:950;
}
.st-key-engine_tab_active button:disabled,
.st-key-engine_tab_inactive button:disabled {
  border-color:#32d9ff; background:#0b2a3d; color:#eaf5ff; opacity:1;
}
.engine-summary {
  font-size:24px; font-weight:900; color:#eaf5ff; margin-bottom:2px;
}
.engine-summary span {color:#32d9ff;}
.engine-grid {display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:14px; margin-top:4px;}
.engine-tile {
  border:1px solid #173a56; border-radius:12px; background:#091827;
  min-height:62px; padding:10px 11px; display:flex; flex-direction:column; justify-content:center;
}
.engine-name {
  color:#c8d9e8; font-size:12px; font-weight:850; text-transform:uppercase;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}
.engine-state {font-size:14px; font-weight:950; margin-top:5px;}
.engine-reason {
  color:#8796a5; font-size:10px; font-weight:850; margin-top:3px;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}
.good {color:#2fe08b;}
.bad {color:#ff5c63;}
.warn {color:#f2a93b;}
.muted {color:#8796a5;}
.text {color:#f3f9ff;}
.cyan {color:#32d9ff;}
.clock {color:#e9fbff; text-shadow:0 0 18px rgba(50,217,255,.18);}
button {font-family: Inter, "Segoe UI", Arial, sans-serif !important;}
div[data-testid="stMarkdownContainer"] p {margin:0;}
@media (max-width: 1200px) {
  .cols-7 {grid-template-columns:repeat(4,minmax(0,1fr));}
  .dash-row.two {grid-template-columns:1fr;}
  .engine-grid {grid-template-columns:repeat(4,minmax(0,1fr));}
  .source-health-strip {grid-template-columns:repeat(3,minmax(0,1fr));}
}
@media (max-width: 760px) {
  .topbar {align-items:flex-start; flex-direction:column;}
  .header-status {text-align:left; min-width:0;}
  .cols-4, .cols-7, .cols-2 {grid-template-columns:1fr;}
  .engine-grid {grid-template-columns:1fr;}
  .source-health-strip {grid-template-columns:1fr;}
  .title {font-size:21px;}
}
</style>
"""


if __name__ == "__main__":
    main()
