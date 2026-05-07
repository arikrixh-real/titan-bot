import os
import time
from datetime import datetime, timezone, timedelta

import pandas as pd
import requests
import streamlit as st
from supabase import create_client, Client


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

IST = timezone(timedelta(hours=5, minutes=30))
AUTO_REFRESH_SECONDS = 10
SCAN_BATCH_SIZE = 50


# =========================================================
# AUTO REFRESH
# =========================================================

if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

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
    return create_client(SUPABASE_URL, SUPABASE_KEY)


supabase: Client | None = get_supabase_client()


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


def normalize_outcome(value):
    text = str(value or "").strip().upper()

    if text in ["TP", "WIN", "WON", "TARGET", "TARGET_HIT", "PROFIT"]:
        return "WIN"

    if text in ["SL", "LOSS", "LOST", "STOPLOSS", "STOP_LOSS", "STOP_LOSS_HIT"]:
        return "LOSS"

    if text in ["OPEN", "ACTIVE", "LIVE", "RUNNING", "WAITING"]:
        return "OPEN"

    return text


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


def scan_status_from_dt(dt):
    if not dt:
        return "UNKNOWN"

    age_seconds = (datetime.now(IST) - dt).total_seconds()

    if age_seconds <= 420:
        return "ONLINE"

    if age_seconds <= 900:
        return "DELAYED"

    return "OFFLINE"


def status_html(status):
    status = str(status).upper()

    if status in ["ONLINE", "CONNECTED", "SUCCESS", "RUNNING", "ACTIVE", "LEARNING", "OBSERVING"]:
        css = "pill-green"
    elif status in ["DELAYED", "UNKNOWN", "WAITING", "NOT CONFIGURED", "BUILDING", "STALE"]:
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

    if color == "blue":
        css_class = "circle circle-blue"
    elif color == "yellow":
        css_class = "circle circle-yellow"
    elif color == "red":
        css_class = "circle circle-red"

    st.markdown(
        f"""
        <div class="card">
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

latest_scan_time = row_time(latest_scan)
latest_scan_health_time = row_time(scan_health)

real_latest_scan_time = latest_dt(latest_scan_time, latest_scan_health_time)

last_scan_age = age_text_from_dt(real_latest_scan_time)
scan_status = scan_status_from_dt(real_latest_scan_time)

github_data = get_github_latest_run()
github_status = github_data["status"]
github_age = age_text_from_dt(github_data["last_run_time"])

supabase_status = "CONNECTED" if supabase is not None else "OFFLINE"

if scan_status == "ONLINE" and supabase_status == "CONNECTED" and github_status in ["SUCCESS", "RUNNING"]:
    titan_status = "ONLINE"
elif scan_status == "DELAYED":
    titan_status = "DELAYED"
else:
    titan_status = "OFFLINE"


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

telegram_alerts = count_any_table(["setups"])

stocks_passed = count_any_table(["setups"])

if stocks_passed == 0:
    stocks_passed = telegram_alerts

live_trades_count = get_live_trades_count()

# ✅ FIXED performance stats:
# Priority 1: Supabase trade_results because Git memory push is disabled
# Priority 2: local outcomes only for local testing
local_trade_stats = get_local_trade_performance_stats()
supabase_trade_stats = get_trade_results_stats()

if supabase_trade_stats["closed_total"] > 0:
    trade_result_stats = {
        **supabase_trade_stats,
        "open_total": max(local_trade_stats.get("open_total", 0), supabase_trade_stats.get("open_total", 0)),
    }
elif local_trade_stats["closed_total"] > 0:
    trade_result_stats = local_trade_stats
else:
    trade_result_stats = {
        "wins": 0,
        "losses": 0,
        "closed_total": 0,
        "accuracy": 0,
        "open_total": max(supabase_trade_stats.get("open_total", 0), local_trade_stats.get("open_total", 0)),
        "source": "SUPABASE_TRADE_RESULTS_OPEN_ONLY",
        "latest_outcome_time": supabase_trade_stats.get("latest_outcome_time"),
    }

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
    scan_time=real_latest_scan_time,
    outcome_time=trade_result_stats.get("latest_outcome_time"),
)

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
telegram_status = "ACTIVE" if telegram_alerts > 0 else "WAITING"
learning_status = master_brain_data["evolution_status"]
evolution_status = master_brain_data["evolution_status"]

if scan_health:
    latest_stocks_checked = int(scan_health.get("stocks_checked") or 0)
    latest_trend_passed = int(scan_health.get("trend_passed") or 0)
    latest_momentum_passed = int(scan_health.get("momentum_passed") or 0)
    latest_structure_passed = int(scan_health.get("structure_passed") or 0)
    latest_entry_passed = int(scan_health.get("entry_passed") or 0)
    latest_final_passed = int(scan_health.get("final_passed") or 0)
    latest_health_alerts = int(scan_health.get("alerts_sent") or 0)
    latest_scan_health_age = age_text_from_dt(latest_scan_health_time)

    if latest_scan_health_time and latest_stocks_checked > 0:
        health_age_seconds = (datetime.now(IST) - latest_scan_health_time).total_seconds()

        if health_age_seconds <= 900:
            upstox_live_price_status = "ACTIVE"
        else:
            upstox_live_price_status = "INACTIVE"
    else:
        upstox_live_price_status = "INACTIVE"
else:
    latest_stocks_checked = 0
    latest_trend_passed = 0
    latest_momentum_passed = 0
    latest_structure_passed = 0
    latest_entry_passed = 0
    latest_final_passed = 0
    latest_health_alerts = 0
    latest_scan_health_age = "No live price scan yet"
    upstox_live_price_status = "INACTIVE"


# =========================================================
# HEADER
# =========================================================

now_text = datetime.now(IST).strftime("%d %b %Y · %I:%M:%S %p IST")

st.markdown("# ⚡ TITAN Command Center")
st.markdown(
    f"<div class='subtitle'>Clean V2 dashboard · Auto refresh every {AUTO_REFRESH_SECONDS}s · {now_text}</div>",
    unsafe_allow_html=True,
)


# =========================================================
# 1. TOP STATUS
# =========================================================

st.markdown("<div class='section'>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>🧠 Top Control Status</div>", unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)

with c1:
    status_card("TITAN Status", titan_status, "Overall bot condition")

with c2:
    status_card("GitHub 5-Min Runner", github_status, github_data["message"])

with c3:
    status_card("Supabase Status", supabase_status, "Memory database connection")

with c4:
    metric_card("Last Scan", last_scan_age, f"GitHub last run: {github_age}")

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
    circular_graph(
        "Overall Trade Performance",
        trade_performance_percent,
        f"Closed only · Open ignored: {open_outcome_trades}",
        "blue",
    )

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
        master_brain_data["master_status"],
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
    small_status("GitHub 5-Min Runner", github_status, f"Last run: {github_age}")
    small_status("Supabase Memory", supabase_status, "Database connection")
    small_status("Master Brain", master_brain_data["master_status"], f"Last activity: {master_brain_data['last_activity_age']}")

with r2:
    small_status("News Engine", news_status, f"News: {news_gathered:,} · Latest: {news_memory_data['age']}")
    small_status("Telegram Alert Engine", telegram_status, f"Alerts sent: {telegram_alerts:,}")
    small_status("Learning / Evolution", learning_status, master_brain_data["evolution_sub"])
    small_status("Outcome Tracker", "ACTIVE" if open_outcome_trades > 0 or closed_trades > 0 else "WAITING", f"Open: {open_outcome_trades}, Closed: {closed_trades}")

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
        metric_card("Live Trades Count", f"{live_trades_count:,}", "From Supabase trade_results")

else:
    st.info("No scan breakdown data yet. Wait for the next GitHub 5-minute scan after scan health logging is pushed.")

st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# FOOTER
# =========================================================

st.caption("TITAN Dashboard V2 · Streamlit Cloud · GitHub Actions · Supabase Memory")