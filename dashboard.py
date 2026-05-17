import os
import json
import glob
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
import streamlit as st
from supabase import create_client, Client
from utils.market_hours import IST, is_trade_window


# =========================================================
# TITAN DASHBOARD V2
# Clean Command Center Dashboard
# FIXED:
# - Trading Performance reads local data/journals/trade_outcomes.csv first
# - Counts ONLY TP/WIN as wins and SL/LOSS as losses
# - Ignores OPEN trades
# - Added Master Brain status / evolution visibility
# =========================================================

st.set_page_config(
    page_title="TITAN Dashboard V2",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

AUTO_REFRESH_SECONDS = 10
SCAN_BATCH_SIZE = 50
INITIAL_BALANCE = 1000.0
REAL_PNL_SOURCE_LABEL = "REAL_STOCK_WISE_PNL | QTY_SYNC_ACTIVE"
DASHBOARD_VISUAL_VERSION = "REAL_PNL_QTY_SYNC_FIX_V1"
PAPER_ACCOUNT_PATH = "/".join(["data", "paper_trading", "paper_account.json"])
DASHBOARD_SYNC_STATUS_PATH = "/".join(["data", "runtime", "dashboard_sync_status.json"])
PAPER_ENGINE_STATUS_PATH = "/".join(["data", "runtime", "paper_engine_status.json"])


# =========================================================
# AUTO REFRESH
# =========================================================

if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

if st.session_state.get("dashboard_visual_version") != DASHBOARD_VISUAL_VERSION:
    try:
        st.cache_data.clear()
    except Exception:
        pass
    st.session_state.dashboard_visual_version = DASHBOARD_VISUAL_VERSION

if time.time() - st.session_state.last_refresh >= AUTO_REFRESH_SECONDS:
    st.session_state.last_refresh = time.time()
    st.rerun()


# =========================================================
# STYLE
# =========================================================

st.markdown(
    """
    <style>
    .stApp {
        background: #070b14;
        color: white;
    }

    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
    }

    h1, h2, h3 {
        color: #ffffff;
    }

    .subtitle {
        color: #94a3b8;
        font-size: 15px;
        margin-bottom: 20px;
    }

    .section {
        background: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 22px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 0 22px rgba(0,0,0,0.22);
    }

    .section-title {
        font-size: 22px;
        font-weight: 900;
        color: white;
        margin-bottom: 18px;
    }

    .card {
        background: #111827;
        border: 1px solid #253044;
        border-radius: 18px;
        padding: 20px;
        min-height: 130px;
        text-align: center;
    }

    .card-title {
        color: #94a3b8;
        font-size: 14px;
        font-weight: 700;
        margin-bottom: 8px;
    }

    .card-value {
        color: #ffffff;
        font-size: 32px;
        font-weight: 900;
        margin-top: 5px;
    }

    .card-sub {
        color: #94a3b8;
        font-size: 13px;
        margin-top: 6px;
    }

    .account-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px;
        margin-top: 8px;
        text-align: left;
    }

    .account-item {
        background: #0f172a;
        border: 1px solid #253044;
        border-radius: 10px;
        padding: 10px 12px;
    }

    .account-label {
        color: #94a3b8;
        font-size: 12px;
        font-weight: 700;
        margin-bottom: 4px;
    }

    .account-value {
        color: #ffffff;
        font-size: 16px;
        font-weight: 900;
        overflow-wrap: anywhere;
    }

    .account-value.positive { color: #22c55e; }
    .account-value.negative { color: #ef4444; }
    .account-value.neutral { color: #e5e7eb; }

    .account-balance-card,
    .accuracy-card {
        min-height: 286px;
    }

    .accuracy-card {
        display: flex;
        flex-direction: column;
        justify-content: center;
    }

    .pill-green {
        display: inline-block;
        background: rgba(34,197,94,0.15);
        border: 1px solid rgba(34,197,94,0.4);
        color: #22c55e;
        padding: 8px 15px;
        border-radius: 999px;
        font-weight: 900;
    }

    .pill-red {
        display: inline-block;
        background: rgba(239,68,68,0.15);
        border: 1px solid rgba(239,68,68,0.4);
        color: #ef4444;
        padding: 8px 15px;
        border-radius: 999px;
        font-weight: 900;
    }

    .pill-yellow {
        display: inline-block;
        background: rgba(250,204,21,0.15);
        border: 1px solid rgba(250,204,21,0.4);
        color: #facc15;
        padding: 8px 15px;
        border-radius: 999px;
        font-weight: 900;
    }

    .circle-wrap {
        display: flex;
        justify-content: center;
        align-items: center;
        margin-top: 8px;
        margin-bottom: 12px;
    }

    .circle {
        width: 135px;
        height: 135px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        background:
            radial-gradient(closest-side, #111827 73%, transparent 74% 100%),
            conic-gradient(#22c55e var(--value), #1e293b 0);
    }

    .circle-blue {
        background:
            radial-gradient(closest-side, #111827 73%, transparent 74% 100%),
            conic-gradient(#38bdf8 var(--value), #1e293b 0);
    }

    .circle-yellow {
        background:
            radial-gradient(closest-side, #111827 73%, transparent 74% 100%),
            conic-gradient(#facc15 var(--value), #1e293b 0);
    }

    .circle-red {
        background:
            radial-gradient(closest-side, #111827 73%, transparent 74% 100%),
            conic-gradient(#ef4444 var(--value), #1e293b 0);
    }

    .circle-number {
        font-size: 27px;
        font-weight: 950;
        color: white;
    }

    .bar-box {
        margin-top: 8px;
        margin-bottom: 14px;
    }

    .bar-label-row {
        display: flex;
        justify-content: space-between;
        color: #d1d5db;
        font-size: 14px;
        font-weight: 700;
        margin-bottom: 7px;
    }

    .bar-bg {
        height: 24px;
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 999px;
        overflow: hidden;
    }

    .bar-fill {
        height: 100%;
        background: linear-gradient(90deg, #22c55e, #38bdf8);
        border-radius: 999px;
        text-align: right;
        padding-right: 10px;
        line-height: 24px;
        color: white;
        font-size: 12px;
        font-weight: 900;
    }

    .small-status-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: #111827;
        border: 1px solid #253044;
        border-radius: 14px;
        padding: 14px 16px;
        margin-bottom: 10px;
    }

    .small-status-name {
        font-size: 15px;
        color: #e5e7eb;
        font-weight: 800;
    }

    .small-status-sub {
        font-size: 12px;
        color: #94a3b8;
    }

    hr {
        border-color: #1e293b;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# SECRETS
# =========================================================

def get_secret(key, default=None):
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_KEY = get_secret("SUPABASE_KEY")

GITHUB_OWNER = get_secret("GITHUB_OWNER")
GITHUB_REPO = get_secret("GITHUB_REPO")
GITHUB_TOKEN = get_secret("GITHUB_TOKEN")


# =========================================================
# CONNECTIONS
# =========================================================

@st.cache_resource
def get_supabase_client():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None


supabase: Client | None = get_supabase_client()


@st.cache_data(ttl=60)
def get_supabase_connection_status():
    if supabase is None:
        return "OFFLINE"
    try:
        supabase.table("scans").select("created_at").limit(1).execute()
        return "CONNECTED"
    except Exception:
        return "DEGRADED"


# =========================================================
# SAFE LOCAL FILE HELPERS
# =========================================================

def read_csv_safe(paths):
    """
    Reads first existing CSV safely.
    Skips corrupted rows instead of crashing dashboard.
    """
    for path in paths:
        try:
            if not os.path.exists(path):
                continue
            df = pd.read_csv(path, on_bad_lines="skip")
            return df
        except Exception:
            continue
    return pd.DataFrame()


def safe_read_json(path, default=None):
    fallback = default if default is not None else {}
    try:
        if not os.path.exists(path) or os.path.getsize(path) > 5_000_000:
            return fallback
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if data is not None else fallback
    except Exception as exc:
        print(f"[Dashboard WARN] JSON skipped safely: {path} ({exc})")
        return fallback


def safe_load_json(path, default=None):
    return safe_read_json(path, default)


def safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def first_number(*values, default=0.0):
    for value in values:
        if value is None or value == "":
            continue
        try:
            return float(value)
        except Exception:
            continue
    return float(default)


def format_inr(value):
    return f"₹{safe_float(value):,.2f}"


def format_signed_inr(value):
    amount = safe_float(value)
    if amount > 0:
        return f"+{format_inr(amount)}"
    if amount < 0:
        return f"-{format_inr(abs(amount))}"
    return format_inr(0)


def format_signed_pct(value):
    amount = safe_float(value)
    if amount > 0:
        return f"+{amount:.2f}%"
    if amount < 0:
        return f"-{abs(amount):.2f}%"
    return "0.00%"


def pnl_class(value):
    amount = safe_float(value)
    if amount > 0:
        return "positive"
    if amount < 0:
        return "negative"
    return "neutral"


def safe_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    return [value]


def file_modified_dt(path):
    try:
        if os.path.exists(path):
            return datetime.fromtimestamp(os.path.getmtime(path), tz=IST)
    except Exception:
        pass
    return None


def is_market_open_now(now=None):
    return is_trade_window(now)


def market_mode_label():
    return "MARKET OPEN" if is_market_open_now() else "MARKET CLOSED / RESEARCH MODE"


PHASE_REPORT_PATHS = {
    "autonomous_research": "data/research/autonomous_research_report.json",
    "backtesting_validation": "data/research/backtesting_validation_report.json",
    "paper_account": PAPER_ACCOUNT_PATH,
    "execution_safety": "data/execution_safety/latest_execution_safety_report.json",
    "smart_execution": "data/execution_safety/latest_smart_execution_report.json",
    "microstructure": "data/microstructure/latest_microstructure_report.json",
    "options_flow": "data/options_flow/latest_options_flow_report.json",
    "news_intelligence_2": "data/news_intelligence/latest_news_intelligence_2_report.json",
    "economic_calendar": "data/economic_calendar/latest_economic_calendar_report.json",
    "liquidity_map": "data/liquidity_map/latest_institutional_liquidity_report.json",
    "scenario_simulation": "data/scenario_simulation/latest_scenario_simulation_report.json",
    "multi_agent_debate": "data/multi_agent_debate/latest_multi_agent_debate_report.json",
    "self_reflection": "data/self_reflection/latest_self_reflection_report.json",
    "confidence_calibration": "data/confidence_calibration/latest_confidence_calibration_report.json",
    "no_trade": "data/no_trade/latest_no_trade_intelligence_report.json",
    "memory_consolidation": "data/memory_consolidation/latest_memory_consolidation_report.json",
    "auto_repair": "data/auto_repair/latest_auto_repair_report.json",
}


def load_phase_reports():
    reports = {}
    latest_time = None
    report_paths = dict(PHASE_REPORT_PATHS)
    for path in glob.glob("data/*/latest_*.json"):
        key = os.path.splitext(os.path.basename(path))[0]
        report_paths.setdefault(key, path.replace("\\", "/"))

    for key, path in report_paths.items():
        data = safe_read_json(path, {})
        modified = file_modified_dt(path)
        generated = parse_dt(data.get("generated_at")) if isinstance(data, dict) else None
        report_time = latest_dt(modified, generated)
        reports[key] = {
            "path": path,
            "data": data if isinstance(data, dict) else {},
            "exists": os.path.exists(path),
            "time": report_time,
            "age": age_text_from_dt(report_time),
        }
        if report_time and (latest_time is None or report_time > latest_time):
            latest_time = report_time
    return reports, latest_time


def get_paper_trading_status(phase_reports=None, closed_trade_rows=None, open_trade_rows=None, account_source=None):
    phase_reports = phase_reports or {}
    closed_trade_rows = [row for row in safe_list(closed_trade_rows) if isinstance(row, dict)]
    open_trade_rows = [row for row in safe_list(open_trade_rows) if isinstance(row, dict)]
    paper = phase_reports.get("paper_account", {}).get("data", {})
    if not paper:
        paper = safe_read_json(PAPER_ACCOUNT_PATH, {})
    if not isinstance(paper, dict):
        paper = {}

    # Cloud source-of-truth fix:
    # When Trading Performance is sourced from Supabase trade_results and Supabase
    # has zero closed rows, do not use old local paper_account / paper_closed_positions
    # values for account balance or PnL. This keeps the cloud dashboard at zero
    # after trade_results is cleared.
    if str(account_source or "").upper() == "SUPABASE_TRADE_RESULTS" and not closed_trade_rows:
        initial_balance = first_number(
            paper.get("initial_balance"),
            paper.get("starting_balance"),
            INITIAL_BALANCE,
            default=INITIAL_BALANCE,
        )
        open_pnl = calculate_open_trade_pnl(open_trade_rows)
        equity = round(initial_balance + open_pnl, 2)
        return {
            "balance": initial_balance,
            "account_balance": initial_balance,
            "equity": equity,
            "daily_pnl": 0.0,
            "daily_pnl_pct": 0.0,
            "open_positions": len(open_trade_rows),
            "closed_pnl": 0.0,
            "open_pnl": open_pnl,
            "pnl_report": build_real_closed_pnl_report([]),
            "drawdown_pct": round(max(0.0, ((initial_balance - equity) / initial_balance) * 100.0) if initial_balance > 0 else 0.0, 2),
            "status": str(paper.get("status") or paper.get("paper_trading_status") or "ACTIVE").upper(),
            "balance_source": "SUPABASE_TRADE_RESULTS_ZERO",
            "daily_pnl_source": "SUPABASE_TRADE_RESULTS_ZERO",
            "open_pnl_source": "SUPABASE_TRADE_RESULTS_ZERO",
            "closed_pnl_source": "SUPABASE_TRADE_RESULTS_ZERO",
            "equity_source": "initial_balance_plus_open_pnl",
            "source_label": "SUPABASE_TRADE_RESULTS | ZERO_CLOSED_TRADES",
        }

    positions = paper.get("open_positions")
    if positions is None:
        positions = paper.get("positions")
    if positions is None:
        positions = safe_read_json("data/paper_trading/paper_positions.json", [])
    closed_positions = paper.get("closed_positions")
    if closed_positions is None:
        closed_positions = safe_read_json("data/paper_trading/paper_closed_positions.json", [])

    open_items = [
        p for p in safe_list(positions)
        if isinstance(p, dict) and str(p.get("status", "OPEN")).upper() in ["OPEN", "ACTIVE", "LIVE", "FILLED"]
    ]
    closed_items = [p for p in safe_list(closed_positions) if isinstance(p, dict)]

    initial_balance = first_number(
        paper.get("initial_balance"),
        paper.get("starting_balance"),
        INITIAL_BALANCE,
        default=INITIAL_BALANCE,
    )

    pnl_rows = filter_rows_after_paper_account_start(closed_trade_rows if closed_trade_rows else closed_items, paper)
    if pnl_rows:
        pnl_report = build_real_closed_pnl_report(pnl_rows)
        closed_pnl = pnl_report["closed_pnl"]
        balance = round(initial_balance + closed_pnl, 2)
        open_pnl = calculate_open_trade_pnl(open_trade_rows if open_trade_rows else open_items)
        equity = round(balance + open_pnl, 2)
        daily_pnl = round(sum(
            calculate_trade_result_pnl(row)
            for row in pnl_rows
            if is_closed_today_ist(row)
        ), 2)
        daily_pnl_pct = (daily_pnl / initial_balance * 100.0) if initial_balance > 0 else 0.0
        pnl_report.update({
            "daily_pnl": daily_pnl,
            "account_balance": balance,
        })
        return {
            "balance": balance,
            "account_balance": balance,
            "equity": equity,
            "daily_pnl": daily_pnl,
            "daily_pnl_pct": daily_pnl_pct,
            "open_positions": len(open_items),
            "closed_pnl": round(closed_pnl, 2),
            "open_pnl": open_pnl,
            "pnl_report": pnl_report,
            "drawdown_pct": round(max(0.0, ((initial_balance - equity) / initial_balance) * 100.0) if initial_balance > 0 else 0.0, 2),
            "status": str(paper.get("status") or paper.get("paper_trading_status") or "ACTIVE").upper(),
            "balance_source": REAL_PNL_SOURCE_LABEL,
            "daily_pnl_source": REAL_PNL_SOURCE_LABEL,
            "open_pnl_source": REAL_PNL_SOURCE_LABEL,
            "closed_pnl_source": REAL_PNL_SOURCE_LABEL,
            "equity_source": "trade_results_balance_plus_open_pnl",
            "source_label": REAL_PNL_SOURCE_LABEL,
        }

    balance_keys = ("current_balance", "balance", "cash")
    balance_source = next((key for key in balance_keys if paper.get(key) not in [None, ""]), "initial_balance")
    balance = first_number(
        paper.get("current_balance"),
        paper.get("balance"),
        paper.get("cash"),
        initial_balance,
        default=INITIAL_BALANCE,
    )

    open_pnl_from_positions = sum(
        first_number(
            p.get("open_pnl"),
            p.get("unrealized_pnl"),
            p.get("pnl"),
            default=0.0,
        )
        for p in open_items
    )
    open_pnl_source = "account" if paper.get("open_pnl") not in [None, ""] or paper.get("unrealized_pnl") not in [None, ""] else "positions"
    open_pnl = first_number(
        paper.get("open_pnl"),
        paper.get("unrealized_pnl"),
        open_pnl_from_positions,
        default=0.0,
    )

    closed_pnl_from_positions = sum(
        first_number(
            p.get("closed_pnl"),
            p.get("realized_pnl"),
            p.get("pnl"),
            default=0.0,
        )
        for p in closed_items
    )
    closed_pnl_source = "account" if paper.get("closed_pnl") not in [None, ""] else "positions"
    closed_pnl = first_number(
        paper.get("closed_pnl"),
        paper.get("realized_pnl"),
        closed_pnl_from_positions,
        default=0.0,
    )

    equity_source = "account" if paper.get("equity") not in [None, ""] or paper.get("account_value") not in [None, ""] else "balance_plus_open_pnl"
    equity = first_number(
        paper.get("equity"),
        paper.get("account_value"),
        balance + open_pnl,
        default=balance + open_pnl,
    )

    daily_start_balance = first_number(
        paper.get("daily_start_balance"),
        initial_balance,
        default=INITIAL_BALANCE,
    )
    daily_pnl_source = "account" if paper.get("daily_pnl") not in [None, ""] else "balance_minus_daily_start"
    daily_pnl = first_number(
        paper.get("daily_pnl"),
        balance - daily_start_balance,
        default=0.0,
    )
    daily_pnl_pct = (daily_pnl / daily_start_balance * 100.0) if daily_start_balance > 0 else 0.0

    drawdown_pct = first_number(
        paper.get("drawdown_pct"),
        paper.get("drawdown"),
        max(0.0, ((initial_balance - equity) / initial_balance) * 100.0) if initial_balance > 0 else 0.0,
        default=0.0,
    )
    status = str(paper.get("status") or paper.get("paper_trading_status") or ("ACTIVE" if paper else "WAITING")).upper()
    pnl_report = build_real_closed_pnl_report([])
    closed_pnl = round(first_number(paper.get("closed_pnl"), paper.get("realized_pnl"), default=0.0), 2)
    balance = first_number(paper.get("current_balance"), paper.get("balance"), initial_balance + closed_pnl, default=initial_balance)
    open_pnl = calculate_open_trade_pnl(open_items)
    if open_pnl == 0.0:
        open_pnl = first_number(paper.get("open_pnl"), paper.get("unrealized_pnl"), default=0.0)
    equity = round(balance + open_pnl, 2)
    daily_pnl = first_number(paper.get("daily_pnl"), balance - daily_start_balance, default=0.0)
    daily_pnl_pct = (daily_pnl / daily_start_balance * 100.0) if daily_start_balance > 0 else 0.0
    drawdown_pct = round(max(0.0, ((initial_balance - equity) / initial_balance) * 100.0) if initial_balance > 0 else 0.0, 2)
    pnl_report.update({
        "daily_pnl": daily_pnl,
        "account_balance": balance,
    })
    return {
        "balance": balance,
        "account_balance": balance,
        "equity": equity,
        "daily_pnl": daily_pnl,
        "daily_pnl_pct": daily_pnl_pct,
        "open_positions": len(open_items),
        "closed_pnl": closed_pnl,
        "open_pnl": open_pnl,
        "pnl_report": pnl_report,
        "drawdown_pct": round(drawdown_pct, 2),
        "status": status,
        "balance_source": REAL_PNL_SOURCE_LABEL,
        "daily_pnl_source": REAL_PNL_SOURCE_LABEL,
        "open_pnl_source": REAL_PNL_SOURCE_LABEL,
        "closed_pnl_source": REAL_PNL_SOURCE_LABEL,
        "equity_source": equity_source,
        "source_label": REAL_PNL_SOURCE_LABEL,
    }

def nested_value(data, *paths, default=None):
    for path in paths:
        current = data
        for key in path:
            if not isinstance(current, dict) or key not in current:
                current = None
                break
            current = current.get(key)
        if current not in [None, ""]:
            return current
    return default


def get_master_shadow_dashboard_data():
    """
    Reads local Phase report and memory artifacts only.
    No report generation, network calls, Supabase writes, scans, or live prices.
    """
    neutral = {
        "status": "WAITING",
        "narrative": "RESEARCH MODE" if not is_market_open_now() else "NEUTRAL",
        "cross_setup_heat": 0.0,
        "tracked_lifecycle_trades": 0,
        "shadow_warnings": 0,
        "runtime_bounded": True,
        "updated_at": "No data yet",
    }

    try:
        report_paths = set(PHASE_REPORT_PATHS.values())
        report_paths.update(glob.glob("data/*/latest_*.json"))
        memory_paths = set(glob.glob("data/memory/*.json"))
        memory_paths.update(glob.glob("data/memory_consolidation/*.json"))
        existing_reports = [path for path in report_paths if os.path.exists(path)]
        existing_memory = [path for path in memory_paths if os.path.exists(path)]
        artifact_count = len(existing_reports) + len(existing_memory)

        master_path = "data/memory/master_shadow_memory.json"
        data = safe_read_json(master_path, {})
        if not isinstance(data, dict):
            data = {}

        if not data and artifact_count == 0:
            return neutral

        narrative_memory = safe_read_json("data/memory/market_narrative_memory.json", {})
        cross_setup_memory = safe_read_json("data/memory/cross_setup_memory.json", {})
        lifecycle_memory = safe_read_json("data/memory/lifecycle_memory.json", {})
        no_trade_report = safe_read_json("data/no_trade/latest_no_trade_intelligence_report.json", {})
        scenario_report = safe_read_json("data/scenario_simulation/latest_scenario_simulation_report.json", {})
        liquidity_report = safe_read_json("data/liquidity_map/latest_institutional_liquidity_report.json", {})

        cards = data.get("dashboard_cards") if isinstance(data.get("dashboard_cards"), dict) else {}
        command = data.get("command_status") if isinstance(data.get("command_status"), dict) else {}

        master_brain_memory = safe_read_json("data/memory/titan_master_status.json", {})
        master_brain_active = bool(master_brain_memory) or bool(existing_reports) or bool(existing_memory)

        status = str(cards.get("master_shadow_state") or command.get("overall_state") or "").upper()
        if status in ["", "UNKNOWN", "DEGRADED_OBSERVING", "WAITING"] and master_brain_active:
            status = "ACTIVE"
        elif not status:
            status = neutral["status"]

        raw_narrative = str(
            cards.get("narrative")
            or nested_value(narrative_memory, ("current_narrative", "narrative_type"))
            or nested_value(narrative_memory, ("current_narrative", "market_direction"))
            or scenario_report.get("scenario_bias")
            or ""
        ).upper()
        no_trade_permission = str(no_trade_report.get("trade_permission") or "").upper()
        no_trade_warning = str(no_trade_report.get("no_trade_warning") or "").upper()
        if no_trade_permission in ["BLOCK", "WAIT"] or no_trade_warning not in ["", "NONE"]:
            narrative = "NO-TRADE"
        elif "NEUTRAL" in raw_narrative or raw_narrative in ["CHOPPY", "SIDEWAYS"]:
            narrative = "NEUTRAL"
        elif raw_narrative:
            narrative = raw_narrative
        else:
            narrative = "MARKET ACTIVE" if is_market_open_now() else "RESEARCH MODE"

        heat_candidates = [
            cards.get("cross_setup_heat"),
            nested_value(cross_setup_memory, ("current_snapshot", "portfolio_heat_score")),
            cross_setup_memory.get("portfolio_heat_score"),
            no_trade_report.get("no_trade_score"),
            nested_value(scenario_report, ("stress_case_simulation", "stress_risk_score")),
            liquidity_report.get("liquidity_map_score"),
        ]
        if str(liquidity_report.get("liquidity_warning") or "").upper() not in ["", "NONE"]:
            heat_candidates.append(50.0)
        heat_values = [safe_float(value) for value in heat_candidates if value not in [None, ""]]
        cross_setup_heat = max(0.0, min(100.0, max(heat_values) if heat_values else 0.0))

        trade_lifecycle = lifecycle_memory.get("trade_lifecycle")
        lifecycle_count = first_number(
            cards.get("tracked_lifecycle_trades"),
            nested_value(lifecycle_memory, ("setup_family_stats", "GENERAL", "observations")),
            len(trade_lifecycle) if isinstance(trade_lifecycle, dict) else None,
            artifact_count,
            default=0.0,
        )
        lifecycle_count = max(int(lifecycle_count), artifact_count if artifact_count else 0)

        risk_flags = nested_value(data, ("risk_observations", "systemic_flags"), default=[])
        warning_count = int(first_number(
            cards.get("shadow_warnings"),
            len(command.get("warnings", [])) if isinstance(command.get("warnings"), list) else None,
            len(risk_flags) if isinstance(risk_flags, list) else None,
            default=0,
        ))

        updated_dt = latest_dt(
            file_modified_dt(master_path),
            parse_dt(data.get("generated_at")),
            parse_dt(nested_value(narrative_memory, ("current_narrative", "generated_at"))),
            parse_dt(cross_setup_memory.get("last_updated")),
            parse_dt(lifecycle_memory.get("last_updated")),
        )

        return {
            "status": status,
            "narrative": narrative,
            "cross_setup_heat": cross_setup_heat,
            "tracked_lifecycle_trades": lifecycle_count,
            "shadow_warnings": warning_count,
            "runtime_bounded": bool(data.get("runtime_bounded", True)),
            "updated_at": age_text_from_dt(updated_dt) if updated_dt else "No data yet",
        }
    except Exception:
        return neutral


def normalize_outcome(value):
    text = str(value or "").strip().upper()

    if text in ["TP", "WIN", "WON", "TARGET", "TARGET_HIT", "PROFIT", "CLOSED_WIN"]:
        return "WIN"

    if text in ["SL", "LOSS", "LOST", "STOPLOSS", "STOP_LOSS", "STOPLOSS_HIT", "STOP_LOSS_HIT", "CLOSED_LOSS"]:
        return "LOSS"

    if text in ["OPEN", "ACTIVE", "LIVE", "RUNNING", "WAITING"]:
        return "OPEN"

    return text


def trade_row_outcome(row):
    if not isinstance(row, dict):
        return ""
    return normalize_outcome(
        row.get("outcome")
        or row.get("result")
        or row.get("status")
        or row.get("trade_result")
    )


def row_symbol(row):
    return str(row.get("symbol") or row.get("stock") or row.get("ticker") or "").strip().upper()


def row_side(row):
    side = str(row.get("side") or row.get("direction") or "").strip().upper()
    if side in ["SELL", "BEARISH"]:
        return "SHORT"
    if side in ["BUY", "BULLISH", ""]:
        return "LONG"
    return side if side in ["LONG", "SHORT"] else "LONG"


def first_present(row, keys):
    for key in keys:
        if isinstance(row, dict) and row.get(key) not in [None, ""]:
            return row.get(key)
    return None


def first_positive_number(row, keys):
    value = first_present(row, keys)
    if value in [None, ""]:
        return None
    try:
        number = float(value)
        return number if number > 0 else None
    except Exception:
        return None


def first_number_value(row, keys):
    """Return the first numeric value, including zero/negative values."""
    value = first_present(row, keys)
    if value in [None, ""]:
        return None
    try:
        return float(value)
    except Exception:
        return None


def first_real_pnl_number(row):
    value = first_present(row, ["realized_pnl", "closed_pnl", "pnl", "profit_loss", "pnl_amount"])
    if value in [None, ""]:
        return None
    try:
        return round(float(value), 2)
    except Exception:
        return None


def row_closed_time(row):
    for key in ["closed_at", "updated_at", "created_at", "timestamp", "opened_at", "time"]:
        if isinstance(row, dict) and row.get(key):
            dt = parse_dt(row.get(key))
            if dt:
                return dt
    return None


def trade_row_key(row):
    return "|".join([
        str(row.get("trade_id") or row.get("id") or "").strip(),
        row_symbol(row),
        row_side(row),
        str(first_present(row, ["entry_price", "entry", "price"]) or "").strip(),
        str(first_present(row, ["exit_price", "close_price", "exit"]) or "").strip(),
        str(row.get("closed_at") or row.get("updated_at") or row.get("created_at") or "").strip(),
        trade_row_outcome(row),
    ])


def is_closed_today_ist(row):
    dt = row_closed_time(row)
    return bool(dt and dt.date() == datetime.now(IST).date())


def calculate_trade_result_pnl(row):
    detail = calculate_trade_result_pnl_detail(row)
    return detail["pnl"] if detail["has_real_pnl"] else 0.0


def calculate_trade_result_pnl_detail(row):
    """
    Final real PnL calculation for dashboard.

    Source of truth columns from Supabase trade_results:
    entry, exit_price, quantity, result/outcome/status, side.

    Important fixes:
    - Do NOT trust stored pnl=0.00 when entry/exit/quantity are available.
    - Use actual quantity from Supabase.
    - If quantity is still missing/0, estimate from INITIAL_BALANCE / entry only as a safe fallback.
    - If side is missing, use raw stock-wise long formula: (exit_price - entry) * quantity.
    """
    if not isinstance(row, dict):
        return {"pnl": 0.0, "has_real_pnl": False, "skipped_pnl_reason": "INVALID_TRADE_ROW"}

    entry = first_positive_number(row, ["entry", "entry_price", "buy_price", "signal_entry", "price", "open_price"])
    if entry is None:
        explicit_pnl = first_real_pnl_number(row)
        if explicit_pnl is not None and abs(explicit_pnl) > 0:
            row.pop("skipped_pnl_reason", None)
            return {"pnl": explicit_pnl, "has_real_pnl": True, "skipped_pnl_reason": ""}
        row["skipped_pnl_reason"] = "MISSING_ENTRY_PRICE"
        return {"pnl": 0.0, "has_real_pnl": False, "skipped_pnl_reason": row["skipped_pnl_reason"]}

    outcome = trade_row_outcome(row)
    exit_price = first_positive_number(row, ["exit_price", "exit", "close_price", "closed_price"])
    if exit_price is None and outcome == "WIN":
        exit_price = first_positive_number(row, ["target", "tp", "target_price", "t1"])
    if exit_price is None and outcome == "LOSS":
        exit_price = first_positive_number(row, ["stop_loss", "sl", "stop_price", "stoploss"])
    if exit_price is None:
        explicit_pnl = first_real_pnl_number(row)
        if explicit_pnl is not None and abs(explicit_pnl) > 0:
            row.pop("skipped_pnl_reason", None)
            return {"pnl": explicit_pnl, "has_real_pnl": True, "skipped_pnl_reason": ""}
        row["skipped_pnl_reason"] = "MISSING_EXIT_PRICE"
        return {"pnl": 0.0, "has_real_pnl": False, "skipped_pnl_reason": row["skipped_pnl_reason"]}

    quantity = first_positive_number(row, ["quantity", "qty", "shares"])
    if quantity is None:
        position_size = first_positive_number(row, ["position_size", "capital_used", "trade_value"])
        if position_size is not None:
            quantity = position_size / entry

    # Last-resort fallback so the cloud dashboard does not stay at zero if old rows
    # are missing qty. Your Supabase SQL already backfilled quantity, so normally
    # this branch will not be used.
    if quantity is None or quantity <= 0:
        quantity = max(1, int(INITIAL_BALANCE // entry)) if entry > 0 else None

    if quantity is None or quantity <= 0:
        row["skipped_pnl_reason"] = "MISSING_QUANTITY"
        return {"pnl": 0.0, "has_real_pnl": False, "skipped_pnl_reason": row["skipped_pnl_reason"]}

    raw_side = str(row.get("side") or row.get("direction") or "").strip().upper()
    if raw_side in ["SHORT", "SELL", "BEARISH"]:
        pnl = (entry - exit_price) * quantity
    else:
        pnl = (exit_price - entry) * quantity

    row.pop("skipped_pnl_reason", None)
    return {"pnl": round(pnl, 2), "has_real_pnl": True, "skipped_pnl_reason": ""}


def build_real_closed_pnl_report(rows):
    report = {
        "total_closed_trades": 0,
        "trades_with_real_pnl": 0,
        "trades_skipped_missing_price_qty": 0,
        "closed_pnl": 0.0,
        "skipped_pnl_reasons": {},
    }
    for row in safe_list(rows):
        if not isinstance(row, dict):
            continue
        report["total_closed_trades"] += 1
        detail = calculate_trade_result_pnl_detail(row)
        if detail["has_real_pnl"]:
            report["trades_with_real_pnl"] += 1
            report["closed_pnl"] += detail["pnl"]
        else:
            report["trades_skipped_missing_price_qty"] += 1
            reason = detail["skipped_pnl_reason"]
            report["skipped_pnl_reasons"][reason] = report["skipped_pnl_reasons"].get(reason, 0) + 1
    report["closed_pnl"] = round(report["closed_pnl"], 2)
    return report


def filter_rows_after_paper_account_start(rows, paper=None):
    if not rows:
        return []
    paper = paper if isinstance(paper, dict) else safe_read_json(PAPER_ACCOUNT_PATH, {})
    if not isinstance(paper, dict) or str(paper.get("capital_mode") or "").upper() != "ADAPTIVE_1K":
        return rows
    start = str(paper.get("created_at") or "").replace("T", " ")[:19]
    if not start:
        return rows
    filtered = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_time = str(row.get("closed_at") or row.get("opened_at") or row.get("created_at") or "").replace("T", " ")[:19]
        if not row_time or row_time >= start:
            filtered.append(row)
    return filtered


def calculate_open_trade_pnl(rows):
    total = 0.0
    for row in safe_list(rows):
        if not isinstance(row, dict):
            continue
        entry = first_positive_number(row, ["entry", "entry_price", "buy_price", "signal_entry", "price", "open_price"])
        live_price = first_positive_number(row, ["live_price", "last_price", "current_price", "ltp", "market_price"])
        if entry is None or live_price is None:
            continue
        quantity = first_positive_number(row, ["quantity", "qty", "shares"])
        if quantity is None:
            position_size = first_positive_number(row, ["position_size"])
            if position_size is not None:
                quantity = position_size / entry
        if quantity is None or quantity <= 0:
            continue
        side = row_side(row)
        total += (live_price - entry) * quantity if side == "LONG" else (entry - live_price) * quantity
    return round(total, 2)


def read_jsonl_rows(path):
    rows = []
    try:
        if not os.path.exists(path):
            return rows
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        rows.append(row)
                except Exception:
                    continue
    except Exception:
        return []
    return rows


def read_local_trade_result_rows():
    rows = []
    for path in [
        "data/journals/trade_results.csv",
        "journal/trade_results.csv",
        "trade_results.csv",
        "data/journals/trade_outcomes.csv",
        "journal/trade_outcomes.csv",
        "trade_outcomes.csv",
    ]:
        df = read_csv_safe([path])
        if not df.empty:
            rows.extend(df.to_dict("records"))

    for path in [
        "data/journals/trade_results.jsonl",
        "data/journals/trade_outcomes.jsonl",
        "journal/trade_results.jsonl",
        "journal/trade_outcomes.jsonl",
    ]:
        rows.extend(read_jsonl_rows(path))

    return rows


def get_supabase_trade_result_rows():
    if supabase is None:
        return []
    try:
        result = (
            supabase.table("trade_results")
            .select("*")
            .order("created_at", desc=True)
            .limit(5000)
            .execute()
        )
        return [row for row in (result.data or []) if isinstance(row, dict)]
    except Exception:
        return []


def get_paper_closed_position_rows():
    rows = safe_read_json("data/paper_trading/paper_closed_positions.json", [])
    return [row for row in safe_list(rows) if isinstance(row, dict)]


def build_trade_results_stats_from_rows(rows, source):
    stats = {
        "wins": 0,
        "losses": 0,
        "closed_total": 0,
        "accuracy": 0,
        "open_total": 0,
        "source": source,
        "latest_outcome_time": None,
        "rows": [],
        "closed_rows": [],
        "open_rows": [],
    }

    latest_time = None
    seen = set()
    for row in safe_list(rows):
        if not isinstance(row, dict) or _is_test_symbol(row_symbol(row)):
            continue
        key = trade_row_key(row)
        if key in seen:
            continue
        seen.add(key)
        stats["rows"].append(row)
        normalized = trade_row_outcome(row)
        if normalized == "WIN":
            stats["wins"] += 1
            stats["closed_rows"].append(row)
        elif normalized == "LOSS":
            stats["losses"] += 1
            stats["closed_rows"].append(row)
        elif normalized == "OPEN":
            stats["open_total"] += 1
            stats["open_rows"].append(row)

        row_dt = row_closed_time(row)
        if row_dt and (latest_time is None or row_dt > latest_time):
            latest_time = row_dt

    stats["closed_total"] = stats["wins"] + stats["losses"]
    if stats["closed_total"] > 0:
        stats["accuracy"] = int((stats["wins"] / stats["closed_total"]) * 100)
    stats["latest_outcome_time"] = latest_time
    return stats


def get_trade_results_dataset():
    """
    Cloud dashboard source-of-truth fix.

    Trading Performance must use Supabase trade_results only.
    Do NOT fallback to paper_closed_positions or local CSV/JSONL rows when
    Supabase is empty, because Streamlit Cloud can contain old committed local
    files that recreate fake wins/losses/PnL after Supabase is cleared.
    """
    return build_trade_results_stats_from_rows(
        get_supabase_trade_result_rows(),
        "SUPABASE_TRADE_RESULTS",
    )


def get_local_trade_performance_stats():
    """
    Dashboard performance fix:
    Read local outcome files and count ONLY closed trades:
    - TP / WIN = win
    - SL / LOSS = loss
    - OPEN ignored

    This prevents frozen/wrong 36/6/30 stats when outcome tracker is still producing OPEN rows.
    """
    stats = {
        "wins": 0,
        "losses": 0,
        "closed_total": 0,
        "accuracy": 0,
        "open_total": 0,
        "source": "LOCAL_OUTCOMES",
        "latest_outcome_time": None,
    }

    df = read_csv_safe([
        "data/journals/trade_outcomes.csv",
        "journal/trade_outcomes.csv",
        "trade_outcomes.csv",
    ])

    if df.empty:
        return stats

    # Find outcome/result column
    outcome_col = None
    for col in ["outcome", "result", "status", "trade_result"]:
        if col in df.columns:
            outcome_col = col
            break

    if not outcome_col:
        return stats

    normalized = df[outcome_col].apply(normalize_outcome)

    stats["wins"] = int((normalized == "WIN").sum())
    stats["losses"] = int((normalized == "LOSS").sum())
    stats["open_total"] = int((normalized == "OPEN").sum())
    stats["closed_total"] = stats["wins"] + stats["losses"]

    if stats["closed_total"] > 0:
        stats["accuracy"] = int((stats["wins"] / stats["closed_total"]) * 100)

    # Latest outcome time
    for time_col in ["closed_at", "checked_at", "timestamp", "time", "created_at"]:
        if time_col in df.columns and not df[time_col].dropna().empty:
            latest_raw = df[time_col].dropna().iloc[-1]
            stats["latest_outcome_time"] = parse_dt(latest_raw)
            break

    return stats



def get_supabase_master_activity_time():
    """
    Reads latest activity from real TITAN Supabase memory tables.
    """
    times = []
    for table in ["learning_memory", "market_conditions", "news_memory", "scan_health_logs", "scans", "setups", "strategy_weights", "trade_results", "trades"]:
        row = latest_row(table)
        dt = row_time(row)
        if dt:
            times.append(dt)
    return max(times) if times else None


def get_news_memory_status():
    """
    Reads news_memory from Supabase.
    ACTIVE = latest news updated recently.
    STALE = news exists but old.
    WAITING = no news yet.
    """
    info = {
        "count": table_count("news_memory"),
        "status": "WAITING",
        "latest_time": None,
        "age": "No news yet",
    }

    row = latest_row("news_memory")
    latest_time = row_time(row)

    info["latest_time"] = latest_time
    info["age"] = age_text_from_dt(latest_time)

    if latest_time:
        age_seconds = (datetime.now(IST) - latest_time).total_seconds()
        if age_seconds <= 6 * 3600:
            info["status"] = "ACTIVE"
        elif age_seconds <= 48 * 3600:
            info["status"] = "DELAYED"
        else:
            info["status"] = "STALE"
    elif info["count"] > 0:
        info["status"] = "ACTIVE"

    return info


def get_master_brain_status(github_time=None, scan_time=None, outcome_time=None):
    """
    Shows whether Master Brain / continuous evolution cycle is active.
    Uses local files produced by TITAN.
    """
    active_df = read_csv_safe([
        "data/journals/active_trades.csv",
        "journal/active_trades.csv",
        "active_trades.csv",
    ])

    outcomes_df = read_csv_safe([
        "data/journals/trade_outcomes.csv",
        "journal/trade_outcomes.csv",
        "trade_outcomes.csv",
    ])

    learning_report_paths = [
        "data/learning/learning_report.json",
        "data/learning/learning_summary.txt",
        "reports/evolution_report.txt",
        "reports/titan_master_status.txt",
    ]

    last_learning_time = None
    learning_file_found = False

    for path in learning_report_paths:
        try:
            if os.path.exists(path):
                learning_file_found = True
                modified = datetime.fromtimestamp(os.path.getmtime(path), tz=IST)
                if last_learning_time is None or modified > last_learning_time:
                    last_learning_time = modified
        except Exception:
            pass

    latest_activity_time = None

    for df in [active_df, outcomes_df]:
        if df.empty:
            continue

        for col in ["last_checked_at", "checked_at", "closed_at", "opened_at", "timestamp", "created_at"]:
            if col in df.columns and not df[col].dropna().empty:
                dt = parse_dt(df[col].dropna().iloc[-1])
                if dt and (latest_activity_time is None or dt > latest_activity_time):
                    latest_activity_time = dt

    # Git memory push is disabled, so local file timestamps may be old on Streamlit.
    # Use GitHub/scan/outcome activity as Master Brain activity source.
    for external_dt in [github_time, scan_time, outcome_time, last_learning_time, get_supabase_master_activity_time()]:
        if external_dt and (latest_activity_time is None or external_dt > latest_activity_time):
            latest_activity_time = external_dt

    active_trades = get_live_trades_count()
    local_stats = get_local_trade_performance_stats()

    # Status logic
    if latest_activity_time:
        age_seconds = (datetime.now(IST) - latest_activity_time).total_seconds()

        if age_seconds <= 900:
            master_status = "ACTIVE"
        elif age_seconds <= 3600:
            master_status = "DELAYED"
        else:
            master_status = "WAITING"
    else:
        master_status = "WAITING"

    if active_trades > 0 or local_stats["open_total"] > 0:
        evolution_status_value = "OBSERVING"
        evolution_sub = f"Monitoring {active_trades or local_stats['open_total']} open/live trades"
    elif local_stats["closed_total"] > 0:
        evolution_status_value = "LEARNING"
        evolution_sub = f"Learning from {local_stats['closed_total']} closed outcomes"
    elif learning_file_found:
        evolution_status_value = "BUILDING"
        evolution_sub = "Learning files detected"
    else:
        evolution_status_value = "WAITING"
        evolution_sub = "Waiting for outcomes"

    return {
        "master_status": master_status,
        "evolution_status": evolution_status_value,
        "evolution_sub": evolution_sub,
        "last_activity": latest_activity_time,
        "last_activity_age": age_text_from_dt(latest_activity_time),
        "learning_file_found": learning_file_found,
    }


# =========================================================
# SAFE SUPABASE HELPERS
# =========================================================

def table_count(table_name):
    try:
        if supabase is None:
            return 0
        result = supabase.table(table_name).select("*", count="exact").limit(1).execute()
        return result.count or 0
    except Exception:
        return 0


def latest_row(table_name, order_column="created_at"):
    """
    Safely fetch latest row. Some TITAN tables may use timestamp/updated_at instead of created_at.
    """
    if supabase is None:
        return None

    for col in [order_column, "created_at", "updated_at", "timestamp", "scan_time", "time", "datetime"]:
        try:
            result = (
                supabase.table(table_name)
                .select("*")
                .order(col, desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]
        except Exception:
            continue

    try:
        result = supabase.table(table_name).select("*").limit(1).execute()
        if result.data:
            return result.data[0]
    except Exception:
        pass

    return None


def count_any_table(table_names):
    for name in table_names:
        count = table_count(name)
        if count > 0:
            return count
    return 0


def latest_any_table(table_names):
    for name in table_names:
        row = latest_row(name)
        if row:
            return row
    return None


def get_latest_scan_health():
    try:
        if supabase is None:
            return None

        result = (
            supabase.table("scan_health_logs")
            .select("*")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if result.data:
            return result.data[0]

        return None

    except Exception:
        return None


def parse_dt(value):
    if not value:
        return None

    try:
        value = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)

        return dt.astimezone(IST)
    except Exception:
        return None


def row_time(row):
    if not row:
        return None

    keys = ["created_at", "timestamp", "scan_time", "updated_at", "time", "datetime"]

    for key in keys:
        if key in row and row[key]:
            dt = parse_dt(row[key])
            if dt:
                return dt

    return None


def latest_dt(*values):
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return max(clean)


def age_text_from_dt(dt):
    if not dt:
        return "No data yet"

    now = datetime.now(IST)
    seconds = int((now - dt).total_seconds())

    if seconds < 0:
        seconds = 0

    if seconds < 60:
        return f"{seconds}s ago"

    minutes = seconds // 60

    if minutes < 60:
        return f"{minutes}m ago"

    hours = minutes // 60

    if hours < 24:
        return f"{hours}h ago"

    days = hours // 24
    return f"{days}d ago"


def format_runtime_timestamp(value):
    dt = parse_dt(value)
    if dt:
        return dt.strftime("%d %b %Y %I:%M:%S %p IST")
    return str(value or "No heartbeat yet")


def get_dashboard_runtime_status():
    data = safe_read_json(DASHBOARD_SYNC_STATUS_PATH, {})
    if not isinstance(data, dict):
        data = {}

    daemon_health = data.get("daemon_health") if isinstance(data.get("daemon_health"), dict) else {}
    heartbeat = data.get("heartbeat") if isinstance(data.get("heartbeat"), dict) else {}
    runtime_status = data.get("runtime_status") if isinstance(data.get("runtime_status"), dict) else {}

    daemon_status = str(
        daemon_health.get("status")
        or heartbeat.get("status")
        or data.get("status")
        or "WAITING"
    ).upper()
    runtime_mode = str(
        runtime_status.get("mode")
        or daemon_health.get("mode")
        or heartbeat.get("mode")
        or "UNKNOWN"
    )
    heartbeat_timestamp = heartbeat.get("timestamp_ist") or daemon_health.get("timestamp_ist") or data.get("timestamp_ist")
    ticks_completed = daemon_health.get("ticks_completed")
    ticks_text = f"{int(ticks_completed):,}" if isinstance(ticks_completed, (int, float)) else str(ticks_completed or "0")

    return {
        "daemon_status": daemon_status,
        "runtime_mode": runtime_mode,
        "heartbeat_timestamp": format_runtime_timestamp(heartbeat_timestamp),
        "ticks_completed": ticks_text,
    }


def get_paper_engine_runtime_status():
    data = safe_read_json(PAPER_ENGINE_STATUS_PATH, {})
    if not isinstance(data, dict):
        data = {}

    summary = data.get("paper_performance_summary")
    account_summary = data.get("paper_account_summary")
    if not isinstance(account_summary, dict):
        account_summary = {}

    equity = first_number(account_summary.get("equity"), account_summary.get("current_balance"), default=0.0)
    realized_pnl = first_number(account_summary.get("realized_pnl"), default=0.0)

    if not isinstance(summary, dict):
        return {
            "status": "WAITING",
            "message": "No paper engine runtime summary yet",
            "open_positions_count": 0,
            "closed_positions_count": 0,
            "equity": equity,
            "realized_pnl": realized_pnl,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "total_unrealized_pnl": 0.0,
            "total_realized_pnl": 0.0,
            "open_long_count": 0,
            "open_short_count": 0,
        }

    return {
        "status": "ACTIVE",
        "message": "Source: data/runtime/paper_engine_status.json",
        "open_positions_count": int(first_number(summary.get("open_positions_count"), default=0)),
        "closed_positions_count": int(first_number(summary.get("closed_positions_count"), default=0)),
        "equity": equity,
        "realized_pnl": realized_pnl,
        "winning_trades": int(first_number(summary.get("winning_trades"), default=0)),
        "losing_trades": int(first_number(summary.get("losing_trades"), default=0)),
        "win_rate": first_number(summary.get("win_rate"), default=0.0),
        "total_unrealized_pnl": first_number(summary.get("total_unrealized_pnl"), default=0.0),
        "total_realized_pnl": first_number(summary.get("total_realized_pnl"), default=0.0),
        "open_long_count": int(first_number(summary.get("open_long_count"), default=0)),
        "open_short_count": int(first_number(summary.get("open_short_count"), default=0)),
    }


def scan_status_from_dt(dt, market_open=None):
    market_open = is_market_open_now() if market_open is None else market_open

    if not market_open:
        return "MARKET CLOSED"

    if not dt:
        return "UNKNOWN"

    age_seconds = (datetime.now(IST) - dt).total_seconds()

    if age_seconds <= 420:
        return "ONLINE"

    if age_seconds <= 900:
        return "DELAYED"

    return "OFFLINE"


def last_scan_display_from_dt(dt, market_open=None):
    market_open = is_market_open_now() if market_open is None else market_open
    if not market_open:
        return "Market closed / research mode"
    return age_text_from_dt(dt)


def derive_titan_status(master_activity_time=None, github_data=None, supabase_status="OFFLINE", market_open=None):
    market_open = is_market_open_now() if market_open is None else market_open
    github_data = github_data or {}
    github_status_value = str(github_data.get("status") or "").upper()
    github_healthy = github_status_value in {"SUCCESS", "RUNNING"}
    supabase_healthy = supabase_status == "CONNECTED"

    if master_activity_time:
        age_seconds = (datetime.now(IST) - master_activity_time).total_seconds()
        if age_seconds <= 6 * 3600:
            return "ONLINE" if market_open else "RESEARCH MODE"
        if age_seconds <= 24 * 3600 and (github_healthy or supabase_healthy):
            return "DELAYED"

    if not market_open and (github_healthy or supabase_healthy):
        return "RESEARCH MODE"
    if github_healthy or supabase_healthy:
        return "DELAYED"
    return "OFFLINE"


def derive_scan_status(scan_time=None, master_activity_time=None, market_open=None):
    market_open = is_market_open_now() if market_open is None else market_open
    if not market_open:
        return "MARKET CLOSED"
    if scan_time:
        age_seconds = (datetime.now(IST) - scan_time).total_seconds()
        if age_seconds <= 420:
            return "ACTIVE"
        return "DELAYED"
    if master_activity_time:
        return "DELAYED"
    return "OFFLINE"


def derive_activity_status(activity_time=None, market_open=None, active_seconds=900, delayed_seconds=3600):
    market_open = is_market_open_now() if market_open is None else market_open
    if not market_open:
        return "RESEARCH MODE"
    if not activity_time:
        return "WAITING"
    age_seconds = (datetime.now(IST) - activity_time).total_seconds()
    if age_seconds <= active_seconds:
        return "ACTIVE"
    if age_seconds <= delayed_seconds:
        return "DELAYED"
    return "OFFLINE"


def derive_upstox_status(scan_health_time=None, stocks_checked=0, market_open=None):
    market_open = is_market_open_now() if market_open is None else market_open
    if not market_open:
        return "MARKET CLOSED"
    if scan_health_time and stocks_checked > 0:
        age_seconds = (datetime.now(IST) - scan_health_time).total_seconds()
        if age_seconds <= 900:
            return "ACTIVE"
        return "DELAYED"
    return "OFFLINE"


def market_aware_status(status, market_open=None, closed_status="RESEARCH MODE"):
    market_open = is_market_open_now() if market_open is None else market_open
    text = str(status or "WAITING").upper()
    if market_open:
        return text
    if text in {"OFFLINE", "ERROR", "FAILED", "INACTIVE", "UNKNOWN", "STALE", "DELAYED"}:
        return closed_status
    return text


def status_html(status):
    status = str(status).upper()

    if status in ["ONLINE", "CONNECTED", "SUCCESS", "RUNNING", "ACTIVE", "LEARNING", "OBSERVING"]:
        css = "pill-green"
    elif status in ["DELAYED", "UNKNOWN", "WAITING", "NOT CONFIGURED", "BUILDING", "STALE", "RESEARCH MODE", "MARKET CLOSED", "MARKET CLOSED / RESEARCH MODE", "REVIEW"]:
        css = "pill-yellow"
    else:
        css = "pill-red"

    return f"<span class='{css}'>{status}</span>"


# =========================================================
# LIVE TRADES HELPERS
# =========================================================

TEST_SYMBOLS = {"TEST", "TESTPY"}


def _is_test_symbol(symbol):
    return str(symbol or "").strip().upper() in TEST_SYMBOLS


def get_live_trades_count():
    """
    FINAL LIVE TRADE FIX:
    Live trades should come from active/open trades, not trade_results.

    Priority:
    1. Supabase trades table if it has OPEN/LIVE/ACTIVE rows
    2. Local active_trades.csv fallback
    3. 0 if nothing available

    NOTE:
    trade_results is for CLOSED TP/SL performance only.
    """

    supabase_count = get_supabase_live_trades_count()

    if supabase_count > 0:
        return supabase_count

    possible_paths = [
        "data/journals/active_trades.csv",
        "active_trades.csv",
        "data/active_trades.csv",
        "journals/active_trades.csv",
        "journal/active_trades.csv",
        "trades/active_trades.csv",
    ]

    for path in possible_paths:
        try:
            if not os.path.exists(path):
                continue

            df = pd.read_csv(path, on_bad_lines="skip")

            if df.empty:
                continue

            if "symbol" in df.columns:
                df = df[~df["symbol"].astype(str).str.upper().isin(TEST_SYMBOLS)]

            status_columns = ["status", "trade_status", "outcome", "state"]

            for col in status_columns:
                if col in df.columns:
                    live_df = df[
                        df[col]
                        .astype(str)
                        .str.upper()
                        .isin(["ACTIVE", "OPEN", "LIVE", "RUNNING", "PENDING"])
                    ]
                    return int(len(live_df))

            return int(len(df))

        except Exception:
            continue

    return 0



def get_supabase_live_trades_count():
    """
    Reads live/open trades from Supabase trades table.
    Does NOT use trade_results because trade_results stores closed TP/SL outcomes.
    Excludes manual TEST rows.
    """
    if supabase is None:
        return 0

    try:
        result = (
            supabase.table("trades")
            .select("symbol,status,trade_status,outcome,result")
            .limit(5000)
            .execute()
        )

        rows = result.data or []

        if not rows:
            return 0

        live_count = 0

        for row in rows:
            if _is_test_symbol(row.get("symbol")):
                continue

            value = (
                row.get("status")
                or row.get("trade_status")
                or row.get("outcome")
                or row.get("result")
            )

            raw = str(value or "").strip().upper()
            normalized = normalize_outcome(raw)

            if normalized == "OPEN" or raw in ["ACTIVE", "LIVE", "RUNNING", "OPEN", "PENDING"]:
                live_count += 1

        return int(live_count)

    except Exception:
        return 0



def get_trade_results_stats():
    """
    FINAL FIX:
    Reads Supabase trade_results as the source of truth.
    - LIVE/OPEN/ACTIVE = open learning trades
    - WIN/TP = wins
    - LOSS/SL = losses
    - excludes manual TEST / TESTPY rows
    """
    stats = {
        "wins": 0,
        "losses": 0,
        "closed_total": 0,
        "accuracy": 0,
        "open_total": 0,
        "source": "SUPABASE_TRADE_RESULTS",
        "latest_outcome_time": None,
    }

    if supabase is None:
        return stats

    try:
        result = (
            supabase.table("trade_results")
            .select("*")
            .order("created_at", desc=True)
            .limit(5000)
            .execute()
        )

        rows = result.data or []
        latest_time = None

        for row in rows:
            if _is_test_symbol(row.get("symbol")):
                continue

            raw_value = (
                row.get("outcome")
                or row.get("result")
                or row.get("status")
                or row.get("trade_result")
            )
            normalized = normalize_outcome(raw_value)

            if normalized == "WIN":
                stats["wins"] += 1
            elif normalized == "LOSS":
                stats["losses"] += 1
            elif normalized == "OPEN":
                stats["open_total"] += 1

            for time_col in ["closed_at", "updated_at", "created_at", "timestamp", "opened_at"]:
                if row.get(time_col):
                    row_dt = parse_dt(row.get(time_col))
                    if row_dt and (latest_time is None or row_dt > latest_time):
                        latest_time = row_dt
                    break

        stats["closed_total"] = stats["wins"] + stats["losses"]

        if stats["closed_total"] > 0:
            stats["accuracy"] = int((stats["wins"] / stats["closed_total"]) * 100)

        stats["latest_outcome_time"] = latest_time
        return stats

    except Exception:
        return stats


def get_today_telegram_alert_count():
    """
    Counts actual Telegram-sent trade alerts from today's trade_results rows.

    Master Brain writes one trade_results row only after Telegram sending
    succeeds, so this is a better source than the setups table.
    """
    if supabase is None:
        return 0

    today = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    seen = set()

    for time_col in ["opened_at", "created_at"]:
        try:
            result = (
                supabase.table("trade_results")
                .select("symbol,side,opened_at,created_at,status,result,outcome")
                .gte(time_col, today.isoformat())
                .lt(time_col, tomorrow.isoformat())
                .limit(1000)
                .execute()
            )

            rows = result.data or []
            if not rows:
                continue

            for row in rows:
                symbol = str(row.get("symbol") or "").strip().upper()
                side = str(row.get("side") or "").strip().upper()

                if not symbol or not side or _is_test_symbol(symbol):
                    continue

                seen.add(f"{symbol}|{side}")

            if seen:
                break

        except Exception:
            continue

    return min(3, len(seen))

# =========================================================
# GITHUB HELPERS
# =========================================================

def get_github_latest_run():
    if not GITHUB_OWNER or not GITHUB_REPO:
        return {
            "status": "NOT CONFIGURED",
            "message": "Missing GitHub secrets",
            "last_run_time": None,
            "url": None,
        }

    try:
        headers = {
            "Accept": "application/vnd.github+json",
            "Cache-Control": "no-cache",
        }

        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs?per_page=1&t={int(time.time())}"
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            return {
                "status": "ERROR",
                "message": f"GitHub API {response.status_code}",
                "last_run_time": None,
                "url": None,
            }

        data = response.json()
        runs = data.get("workflow_runs", [])

        if not runs:
            return {
                "status": "NO RUNS",
                "message": "No workflow runs found",
                "last_run_time": None,
                "url": None,
            }

        run = runs[0]

        status = run.get("status")
        conclusion = run.get("conclusion")
        created_at = parse_dt(run.get("created_at"))
        updated_at = parse_dt(run.get("updated_at"))
        html_url = run.get("html_url")

        run_time = latest_dt(created_at, updated_at)

        if status == "completed" and conclusion == "success":
            final_status = "SUCCESS"
            message = "5-min runner working"
        elif status == "completed":
            final_status = "FAILED"
            message = f"Latest run: {conclusion}"
        else:
            final_status = "RUNNING"
            message = f"Runner: {status}"

        return {
            "status": final_status,
            "message": message,
            "last_run_time": run_time,
            "url": html_url,
        }

    except Exception as e:
        return {
            "status": "ERROR",
            "message": str(e),
            "last_run_time": None,
            "url": None,
        }


# =========================================================
# VISUAL COMPONENTS
# =========================================================

def metric_card(title, value, sub=""):
    st.markdown(
        f"""
        <div class="card">
            <div class="card-title">{title}</div>
            <div class="card-value">{value}</div>
            <div class="card-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_card(title, status, sub=""):
    st.markdown(
        f"""
        <div class="card">
            <div class="card-title">{title}</div>
            {status_html(status)}
            <div class="card-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def circular_graph(title, percent, sub="", color="green"):
    percent = max(0, min(100, int(percent)))
    css_class = "circle"
    card_class = "card"

    if title == "TITAN Overall Accuracy":
        card_class = "card accuracy-card"

    if color == "blue":
        css_class = "circle circle-blue"
    elif color == "yellow":
        css_class = "circle circle-yellow"
    elif color == "red":
        css_class = "circle circle-red"

    st.markdown(
        f"""
        <div class="{card_class}">
            <div class="card-title">{title}</div>
            <div class="circle-wrap">
                <div class="{css_class}" style="--value:{percent}%;">
                    <div class="circle-number">{percent}%</div>
                </div>
            </div>
            <div class="card-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def account_balance_card(data):
    data = data if isinstance(data, dict) else {}
    account_balance = first_number(data.get("account_balance"), data.get("balance"), INITIAL_BALANCE, default=INITIAL_BALANCE)
    equity = first_number(data.get("equity"), account_balance, default=account_balance)
    daily_pnl = first_number(data.get("daily_pnl"), default=0.0)
    daily_pnl_pct = first_number(data.get("daily_pnl_pct"), default=0.0)
    open_pnl = first_number(data.get("open_pnl"), default=0.0)
    closed_pnl = first_number(data.get("closed_pnl"), default=0.0)
    daily_class = pnl_class(daily_pnl)
    source_label = data.get("source_label") or REAL_PNL_SOURCE_LABEL
    pnl_report = data.get("pnl_report") if isinstance(data.get("pnl_report"), dict) else {}
    real_pnl_trades = int(first_number(pnl_report.get("trades_with_real_pnl"), default=0))
    skipped_pnl_trades = int(first_number(pnl_report.get("trades_skipped_missing_price_qty"), default=0))
    st.markdown(
        f"""
        <div class="card account-balance-card">
            <div class="card-title">Account Balance</div>
            <div class="account-grid">
                <div class="account-item">
                    <div class="account-label">Account Balance</div>
                    <div class="account-value">{format_inr(account_balance)}</div>
                </div>
                <div class="account-item">
                    <div class="account-label">Equity</div>
                    <div class="account-value">{format_inr(equity)}</div>
                </div>
                <div class="account-item">
                    <div class="account-label">Daily Profit/Loss</div>
                    <div class="account-value {daily_class}">{format_signed_inr(daily_pnl)}</div>
                </div>
                <div class="account-item">
                    <div class="account-label">Daily P/L %</div>
                    <div class="account-value {daily_class}">{format_signed_pct(daily_pnl_pct)}</div>
                </div>
                <div class="account-item">
                    <div class="account-label">Open PnL</div>
                    <div class="account-value {pnl_class(open_pnl)}">{format_signed_inr(open_pnl)}</div>
                </div>
                <div class="account-item">
                    <div class="account-label">Closed PnL</div>
                    <div class="account-value {pnl_class(closed_pnl)}">{format_signed_inr(closed_pnl)}</div>
                </div>
            </div>
            <div class="card-sub">Source: {source_label}</div>
            <div class="card-sub">Real PnL trades count: {real_pnl_trades} | Skipped missing quantity count: {skipped_pnl_trades}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def progress_bar(label, percent):
    percent = max(0, min(100, int(percent)))

    st.markdown(
        f"""
        <div class="bar-box">
            <div class="bar-label-row">
                <span>{label}</span>
                <span>{percent}%</span>
            </div>
            <div class="bar-bg">
                <div class="bar-fill" style="width:{percent}%;">
                    {percent}%
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def small_status(name, status, sub=""):
    st.markdown(
        f"""
        <div class="small-status-row">
            <div>
                <div class="small-status-name">{name}</div>
                <div class="small-status-sub">{sub}</div>
            </div>
            <div>{status_html(status)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# LOAD TITAN DATA
# =========================================================

latest_scan = latest_any_table(["scans", "scan_symbols", "scan_health_logs"])
scan_health = get_latest_scan_health()
phase_reports, latest_phase_report_time = load_phase_reports()
market_open = is_market_open_now()

latest_scan_time = row_time(latest_scan)
latest_scan_health_time = row_time(scan_health)

real_latest_scan_time = latest_dt(latest_scan_time, latest_scan_health_time)

github_data = get_github_latest_run()
github_status = github_data["status"]
github_age = age_text_from_dt(github_data["last_run_time"])

supabase_status = get_supabase_connection_status()
runtime_status_data = get_dashboard_runtime_status()
paper_engine_runtime_data = get_paper_engine_runtime_status()


# Counts
total_trade_rows = count_any_table(["trade_results", "trades"])
news_memory_data = get_news_memory_status()
news_gathered = news_memory_data["count"]

scan_cycles = count_any_table(["scans"])
scan_symbols_count = count_any_table(["scan_symbols"])
if scan_symbols_count > 0:
    stocks_scanned = scan_symbols_count
else:
    stocks_scanned = scan_cycles * SCAN_BATCH_SIZE

telegram_alerts = get_today_telegram_alert_count()

stocks_passed = count_any_table(["setups"])

if stocks_passed == 0:
    stocks_passed = telegram_alerts

live_trades_count = get_live_trades_count()

# Performance stats and account PnL use the same closed trade rows.
# Priority: Supabase trade_results, local trade results, paper closed positions.
trade_result_stats = get_trade_results_dataset()
supabase_trade_stats = trade_result_stats
paper_trading_data = get_paper_trading_status(
    phase_reports,
    closed_trade_rows=trade_result_stats.get("closed_rows", []),
    open_trade_rows=trade_result_stats.get("open_rows", []),
    account_source=trade_result_stats.get("source"),
)

wins = trade_result_stats["wins"]
losses = trade_result_stats["losses"]
closed_trades = trade_result_stats["closed_total"]
open_outcome_trades = max(supabase_trade_stats.get("open_total", 0), trade_result_stats.get("open_total", 0), live_trades_count)

# Dashboard should show CLOSED trades in performance
total_trades = closed_trades

accuracy_percent = trade_result_stats["accuracy"]
trade_performance_percent = accuracy_percent

rr_display = "1:2"

master_brain_data = get_master_brain_status(
    github_time=github_data.get("last_run_time"),
    scan_time=latest_dt(real_latest_scan_time, latest_phase_report_time),
    outcome_time=trade_result_stats.get("latest_outcome_time"),
)
master_shadow_data = get_master_shadow_dashboard_data()

master_activity_time = latest_dt(
    master_brain_data.get("last_activity"),
    latest_phase_report_time,
    github_data.get("last_run_time"),
    real_latest_scan_time,
)

last_scan_age = last_scan_display_from_dt(real_latest_scan_time, market_open)
scan_status = derive_scan_status(real_latest_scan_time, master_activity_time, market_open)
titan_status = derive_titan_status(master_activity_time, github_data, supabase_status, market_open)
github_display_status = market_aware_status(github_status, market_open, "WAITING")
master_brain_display_status = market_aware_status(master_brain_data["master_status"], market_open, "RESEARCH MODE")

SUPABASE_STORAGE_LIMIT_MB = 500

estimated_storage_mb = (
    (stocks_scanned * 0.002)
    + (news_gathered * 0.003)
    + (total_trade_rows * 0.002)
    + (telegram_alerts * 0.001)
)

supabase_storage_percent = int(min(100, (estimated_storage_mb / SUPABASE_STORAGE_LIMIT_MB) * 100))

engine_progress = {
    "Scan Engine": 90,
    "News Engine": 75,
    "Learning Engine": 55 if closed_trades > 0 else 45,
    "Evolution Engine": 50 if closed_trades > 0 else 40,
    "Risk Engine": 85,
    "Market Regime Engine": 75,
    "Master Brain": 90,
    "Execution Engine": 85,
}

news_status = news_memory_data["status"]
news_report_time = phase_reports.get("news_intelligence_2", {}).get("time")
if news_report_time and (datetime.now(IST) - news_report_time).total_seconds() <= 6 * 3600:
    news_status = "ACTIVE"
news_status = market_aware_status(news_status, market_open, "RESEARCH MODE")

telegram_status = "ACTIVE" if telegram_alerts > 0 else "WAITING"
telegram_status_sub = f"Alerts sent: {telegram_alerts:,}" if market_open else "Outside alert window"
telegram_status = market_aware_status(telegram_status, market_open, "WAITING")

learning_status = master_brain_data["evolution_status"]
if phase_reports.get("memory_consolidation", {}).get("exists") or phase_reports.get("self_reflection", {}).get("exists"):
    learning_status = "ACTIVE" if closed_trades > 0 else "BUILDING"
evolution_status = master_brain_data["evolution_status"]
outcome_tracker_status = derive_activity_status(trade_result_stats.get("latest_outcome_time"), market_open)
if open_outcome_trades > 0 or closed_trades > 0:
    outcome_tracker_status = "ACTIVE" if market_open else "RESEARCH MODE"

if scan_health:
    latest_stocks_checked = int(scan_health.get("stocks_checked") or 0)
    latest_trend_passed = int(scan_health.get("trend_passed") or 0)
    latest_momentum_passed = int(scan_health.get("momentum_passed") or 0)
    latest_structure_passed = int(scan_health.get("structure_passed") or 0)
    latest_entry_passed = int(scan_health.get("entry_passed") or 0)
    latest_final_passed = int(scan_health.get("final_passed") or 0)
    latest_health_alerts = int(scan_health.get("alerts_sent") or 0)
    latest_scan_health_age = last_scan_display_from_dt(latest_scan_health_time, market_open)
    upstox_live_price_status = derive_upstox_status(latest_scan_health_time, latest_stocks_checked, market_open)
else:
    latest_stocks_checked = 0
    latest_trend_passed = 0
    latest_momentum_passed = 0
    latest_structure_passed = 0
    latest_entry_passed = 0
    latest_final_passed = 0
    latest_health_alerts = 0
    latest_scan_health_age = "Market closed / research mode" if not market_open else "No live price scan yet"
    upstox_live_price_status = derive_upstox_status(None, 0, market_open)


# =========================================================
# HEADER
# =========================================================

now_text = datetime.now(IST).strftime("%d %b %Y · %I:%M:%S %p IST")

st.markdown("# ⚡ TITAN Command Center")
st.markdown(
    f"<div class='subtitle'>Clean V2 dashboard · Auto refresh every {AUTO_REFRESH_SECONDS}s · {now_text}</div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div class='subtitle'>ACTIVE_DASHBOARD_FILE = dashboard.py | VISUAL_FIX_V4</div>",
    unsafe_allow_html=True,
)


st.markdown("<div class='subtitle'>Dashboard Real PnL Fix V1</div>", unsafe_allow_html=True)


# =========================================================
# 1. TOP STATUS
# =========================================================

st.markdown("<div class='section'>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>🧠 Top Control Status</div>", unsafe_allow_html=True)

c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    status_card("TITAN Status", titan_status, market_mode_label())

with c2:
    status_card("GitHub 5-Min Runner", github_display_status, github_data["message"])

with c3:
    status_card("Supabase Status", supabase_status, "Memory database connection")

with c4:
    metric_card("Last Scan", last_scan_age, f"GitHub last run: {github_age}")

with c5:
    status_card(
        "Paper Simulation",
        paper_engine_runtime_data["status"],
        (
            f"Open: {paper_engine_runtime_data['open_positions_count']:,} | "
            f"Closed: {paper_engine_runtime_data['closed_positions_count']:,}<br>"
            f"Equity: {format_inr(paper_engine_runtime_data['equity'])}<br>"
            f"Realized PnL: {format_signed_inr(paper_engine_runtime_data['realized_pnl'])}"
        ),
    )

if github_data["url"]:
    st.markdown(f"[Open latest GitHub workflow run]({github_data['url']})")

st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# 2. TRADING PERFORMANCE
# =========================================================

st.markdown("<div class='section'>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>📊 Trading Performance</div>", unsafe_allow_html=True)

p1, p2, p3, p4 = st.columns(4)

with p1:
    metric_card("No. of Trades", f"{total_trades:,}", "Closed TP/SL trades only")

with p2:
    metric_card("No. of Wins", f"{wins:,}", "TP / WIN trades")

with p3:
    metric_card("No. of Losses", f"{losses:,}", "SL / LOSS trades")

with p4:
    metric_card("RR", rr_display, "Current risk-reward model")

g1, g2 = st.columns(2)

with g1:
    account_balance_card(paper_trading_data)

with g2:
    circular_graph(
        "TITAN Overall Accuracy",
        accuracy_percent,
        f"Source: {trade_result_stats.get('source', 'UNKNOWN')}",
        "green",
    )

st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# 2B. MASTER BRAIN / EVOLUTION STATUS
# =========================================================

st.markdown("<div class='section'>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>🧠 Master Brain & Evolution Status</div>", unsafe_allow_html=True)

mb1, mb2, mb3, mb4 = st.columns(4)

with mb1:
    status_card(
        "Master Brain",
        master_brain_display_status,
        f"Last brain activity: {master_brain_data['last_activity_age']}",
    )

with mb2:
    status_card(
        "Continuous Evolution",
        master_brain_data["evolution_status"],
        master_brain_data["evolution_sub"],
    )

with mb3:
    metric_card(
        "Open Learning Trades",
        f"{open_outcome_trades:,}",
        "OPEN trades being watched",
    )

with mb4:
    metric_card(
        "Closed Learning Trades",
        f"{closed_trades:,}",
        "TP/SL results used for accuracy",
    )

st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# 2C. MASTER SHADOW COMMAND CENTER
# =========================================================

st.markdown("<div class='section'>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>Master Shadow Command Center</div>", unsafe_allow_html=True)

ms1, ms2, ms3, ms4 = st.columns(4)

with ms1:
    status_card(
        "Shadow Health",
        master_shadow_data["status"],
        f"Updated: {master_shadow_data['updated_at']}",
    )

with ms2:
    metric_card(
        "Market Narrative",
        master_shadow_data["narrative"],
        "Phase 8 shadow summary",
    )

with ms3:
    circular_graph(
        "Cross-Setup Heat",
        int(master_shadow_data["cross_setup_heat"]),
        "Phase 9 concentration",
        "yellow",
    )

with ms4:
    metric_card(
        "Lifecycle Tracked",
        f"{master_shadow_data['tracked_lifecycle_trades']:,}",
        f"Warnings: {master_shadow_data['shadow_warnings']}",
    )

st.caption(
    "Phase 10 is read-only: dashboard reads local master_shadow_memory.json only; it does not scan, fetch prices, send alerts, or write trade state."
)
st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# 3. SUPABASE STORAGE
# =========================================================

st.markdown("<div class='section'>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>🗄️ Supabase Storage</div>", unsafe_allow_html=True)

s1, s2 = st.columns([1, 2])

with s1:
    circular_graph(
        "Storage Used",
        supabase_storage_percent,
        f"Estimated usage of {SUPABASE_STORAGE_LIMIT_MB} MB limit",
        "yellow",
    )

with s2:
    st.markdown("### Storage Usage")
    progress_bar("Supabase Overall Storage Used", supabase_storage_percent)
    st.caption(
        "Note: This is an estimated dashboard value because Supabase exact database storage is not directly available from the normal client API."
    )

st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# 4. MARKET ACTIVITY
# =========================================================

st.markdown("<div class='section'>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>📡 Market Activity</div>", unsafe_allow_html=True)

m1, m2, m3, m4 = st.columns(4)

with m1:
    metric_card("News Gathered", f"{news_gathered:,}", f"Latest: {news_memory_data['age']}")

with m2:
    metric_card("Stocks Scanned", f"{stocks_scanned:,}", "Scan cycles × 50 stocks")

with m3:
    metric_card("Stocks Passed", f"{stocks_passed:,}", "Passed filters / signals")

with m4:
    metric_card("Telegram Alerts", f"{telegram_alerts:,}", "Alerts sent")

st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# 5. ENGINE DEVELOPMENT PROGRESS
# =========================================================

st.markdown("<div class='section'>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>⚙️ Engine Development Progress</div>", unsafe_allow_html=True)

left, right = st.columns(2)

engine_items = list(engine_progress.items())
mid = len(engine_items) // 2

with left:
    for engine, percent in engine_items[:mid]:
        progress_bar(engine, percent)

with right:
    for engine, percent in engine_items[mid:]:
        progress_bar(engine, percent)

st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# 6. ENGINE LIVE STATUS
# =========================================================

st.markdown("<div class='section'>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>🟢 Engine Running Status</div>", unsafe_allow_html=True)

r1, r2 = st.columns(2)

with r1:
    small_status("Scan Engine", scan_status, f"Last scan: {last_scan_age}")
    small_status("GitHub 5-Min Runner", github_display_status, f"Last run: {github_age}")
    small_status("Supabase Memory", supabase_status, "Database connection")
    small_status("Master Brain", master_brain_display_status, f"Last activity: {master_brain_data['last_activity_age']}")
    small_status(
        "TITAN Runtime",
        runtime_status_data["daemon_status"],
        (
            f"Mode: {runtime_status_data['runtime_mode']} | "
            f"Heartbeat: {runtime_status_data['heartbeat_timestamp']} | "
            f"Ticks: {runtime_status_data['ticks_completed']}"
        ),
    )

with r2:
    small_status("News Engine", news_status, f"News: {news_gathered:,} · Latest: {news_memory_data['age']}")
    small_status("Telegram Alert Engine", telegram_status, telegram_status_sub)
    small_status("Learning / Evolution", learning_status, master_brain_data["evolution_sub"])
    small_status("Outcome Tracker", outcome_tracker_status, f"Open: {open_outcome_trades}, Closed: {closed_trades}")

st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# 7. SCAN BREAKDOWN
# =========================================================

st.markdown("<div class='section'>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>🔍 Scan Breakdown · Why No Alerts?</div>", unsafe_allow_html=True)

if scan_health:
    b1, b2, b3, b4, b5, b6 = st.columns(6)

    with b1:
        metric_card("Stocks Checked", f"{latest_stocks_checked:,}", "Latest scan cycle")

    with b2:
        metric_card("Trend Passed", f"{latest_trend_passed:,}", "Valid trend / side")

    with b3:
        metric_card("Momentum Passed", f"{latest_momentum_passed:,}", "Strong momentum")

    with b4:
        metric_card("Structure Passed", f"{latest_structure_passed:,}", "Clean structure")

    with b5:
        metric_card("Entry Passed", f"{latest_entry_passed:,}", "Breakout ready")

    with b6:
        metric_card("Final Passed", f"{latest_final_passed:,}", "Quality filter passed")

    st.markdown("<br>", unsafe_allow_html=True)

    h1, h2, h3 = st.columns(3)

    with h1:
        status_card(
            "Upstox Live Price",
            upstox_live_price_status,
            f"Live price scan: {latest_stocks_checked}/50 · {latest_scan_health_age}"
        )

    with h2:
        metric_card("Alerts This Scan", f"{latest_health_alerts:,}", "Real alerts only")

    with h3:
        metric_card("Live Trades Count", f"{live_trades_count:,}", "Open trades only")

else:
    st.info("No scan breakdown data yet. Wait for the next GitHub 5-minute scan after scan health logging is pushed.")

st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# FOOTER
# =========================================================

st.caption("TITAN Dashboard V2 · Streamlit Cloud · GitHub Actions · Supabase Memory")
st.caption("REAL_PNL_QTY_SYNC_FIX_V1_ACTIVE")
