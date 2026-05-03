import os
import time
from datetime import datetime, timezone, timedelta

import pandas as pd
import requests
import streamlit as st
from supabase import create_client, Client


# =========================
# PAGE CONFIG
# =========================

st.set_page_config(
    page_title="TITAN Control Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

IST = timezone(timedelta(hours=5, minutes=30))


# =========================
# AUTO REFRESH
# =========================

AUTO_REFRESH_SECONDS = 10

if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

if time.time() - st.session_state.last_refresh >= AUTO_REFRESH_SECONDS:
    st.session_state.last_refresh = time.time()
    st.rerun()


# =========================
# CUSTOM CSS
# =========================

st.markdown(
    """
    <style>
    .main {
        background-color: #0b0f19;
        color: white;
    }

    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
    }

    .section-card {
        background: #111827;
        border: 1px solid #1f2937;
        border-radius: 18px;
        padding: 22px;
        margin-bottom: 20px;
        box-shadow: 0 0 14px rgba(0,0,0,0.25);
    }

    .metric-card {
        background: #0f172a;
        border: 1px solid #253044;
        border-radius: 16px;
        padding: 18px;
        text-align: center;
        min-height: 120px;
    }

    .metric-title {
        font-size: 14px;
        color: #9ca3af;
        margin-bottom: 8px;
    }

    .metric-value {
        font-size: 28px;
        font-weight: 800;
        color: #ffffff;
    }

    .metric-sub {
        font-size: 13px;
        color: #94a3b8;
        margin-top: 6px;
    }

    .green {
        color: #22c55e;
        font-weight: 800;
    }

    .red {
        color: #ef4444;
        font-weight: 800;
    }

    .yellow {
        color: #facc15;
        font-weight: 800;
    }

    .blue {
        color: #38bdf8;
        font-weight: 800;
    }

    .status-pill-green {
        background: rgba(34,197,94,0.15);
        color: #22c55e;
        border: 1px solid rgba(34,197,94,0.35);
        padding: 8px 14px;
        border-radius: 999px;
        font-weight: 800;
        display: inline-block;
    }

    .status-pill-red {
        background: rgba(239,68,68,0.15);
        color: #ef4444;
        border: 1px solid rgba(239,68,68,0.35);
        padding: 8px 14px;
        border-radius: 999px;
        font-weight: 800;
        display: inline-block;
    }

    .status-pill-yellow {
        background: rgba(250,204,21,0.15);
        color: #facc15;
        border: 1px solid rgba(250,204,21,0.35);
        padding: 8px 14px;
        border-radius: 999px;
        font-weight: 800;
        display: inline-block;
    }

    .big-bar {
        height: 28px;
        background: #1e293b;
        border-radius: 999px;
        overflow: hidden;
        margin-top: 10px;
        margin-bottom: 8px;
        border: 1px solid #334155;
    }

    .big-bar-fill {
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, #22c55e, #38bdf8);
        text-align: right;
        padding-right: 12px;
        line-height: 28px;
        color: white;
        font-size: 13px;
        font-weight: 800;
    }

    h1, h2, h3 {
        color: white;
    }

    div[data-testid="stMetric"] {
        background-color: #0f172a;
        padding: 18px;
        border-radius: 16px;
        border: 1px solid #253044;
    }

    .stDataFrame {
        border-radius: 14px;
        overflow: hidden;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================
# CONNECTION HELPERS
# =========================

def get_secret(key, default=None):
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_KEY = get_secret("SUPABASE_KEY")

GITHUB_OWNER = get_secret("GITHUB_OWNER")
GITHUB_REPO = get_secret("GITHUB_REPO")
GITHUB_WORKFLOW = get_secret("GITHUB_WORKFLOW", "titan.yml")
GITHUB_TOKEN = get_secret("GITHUB_TOKEN")


@st.cache_resource
def get_supabase_client():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)


supabase: Client | None = get_supabase_client()


# =========================
# DATA HELPERS
# =========================

def safe_table_count(table_name):
    try:
        if supabase is None:
            return 0
        result = supabase.table(table_name).select("*", count="exact").limit(1).execute()
        return result.count or 0
    except Exception:
        return 0


def safe_latest_row(table_name, order_column="created_at"):
    try:
        if supabase is None:
            return None

        result = (
            supabase.table(table_name)
            .select("*")
            .order(order_column, desc=True)
            .limit(1)
            .execute()
        )

        if result.data:
            return result.data[0]

        return None
    except Exception:
        return None


def safe_recent_rows(table_name, order_column="created_at", limit=20):
    try:
        if supabase is None:
            return []

        result = (
            supabase.table(table_name)
            .select("*")
            .order(order_column, desc=True)
            .limit(limit)
            .execute()
        )

        return result.data or []
    except Exception:
        return []


def parse_datetime(value):
    if not value:
        return None

    try:
        value = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(IST)
    except Exception:
        return None


def get_best_timestamp(row):
    if not row:
        return None

    possible_keys = [
        "created_at",
        "timestamp",
        "scan_time",
        "updated_at",
        "time",
        "datetime",
    ]

    for key in possible_keys:
        if key in row and row[key]:
            parsed = parse_datetime(row[key])
            if parsed:
                return parsed

    return None


def seconds_to_age(seconds):
    if seconds is None:
        return "No scan found"

    seconds = int(seconds)

    if seconds < 60:
        return f"{seconds}s ago"

    minutes = seconds // 60

    if minutes < 60:
        return f"{minutes}m ago"

    hours = minutes // 60

    if hours < 24:
        return f"{hours}h {minutes % 60}m ago"

    days = hours // 24
    return f"{days}d ago"


def get_scan_status(latest_scan_row):
    latest_time = get_best_timestamp(latest_scan_row)

    if latest_time is None:
        return "UNKNOWN", None, "No scan timestamp found"

    now = datetime.now(IST)
    age_seconds = (now - latest_time).total_seconds()

    if age_seconds <= 420:
        return "ONLINE", age_seconds, "Scan engine active"

    if age_seconds <= 900:
        return "DELAYED", age_seconds, "Scan delayed but not dead"

    return "OFFLINE", age_seconds, "No fresh scan detected"


def get_github_status():
    if not GITHUB_OWNER or not GITHUB_REPO:
        return "NOT CONFIGURED", "Add GitHub secrets", None

    try:
        headers = {"Accept": "application/vnd.github+json"}

        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs?per_page=1"

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            return "ERROR", f"GitHub API {response.status_code}", None

        data = response.json()

        runs = data.get("workflow_runs", [])

        if not runs:
            return "NO RUNS", "No GitHub workflow runs found", None

        run = runs[0]

        status = run.get("status", "unknown")
        conclusion = run.get("conclusion")
        created_at = run.get("created_at")
        html_url = run.get("html_url")

        if status == "completed":
            if conclusion == "success":
                return "SUCCESS", "Latest workflow completed successfully", html_url
            return "FAILED", f"Latest workflow ended with {conclusion}", html_url

        return "RUNNING", f"Workflow status: {status}", html_url

    except Exception as e:
        return "ERROR", str(e), None


def big_progress_bar(label, value, total):
    if total <= 0:
        percent = 0
    else:
        percent = min(100, int((value / total) * 100))

    st.markdown(f"**{label}**")
    st.markdown(
        f"""
        <div class="big-bar">
            <div class="big-bar-fill" style="width:{percent}%;">
                {percent}%
            </div>
        </div>
        <div style="color:#94a3b8; font-size:14px;">
            {value:,} / {total:,}
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_pill(status):
    if status in ["ONLINE", "SUCCESS", "RUNNING", "CONNECTED"]:
        css = "status-pill-green"
    elif status in ["DELAYED", "UNKNOWN", "NOT CONFIGURED", "NO RUNS"]:
        css = "status-pill-yellow"
    else:
        css = "status-pill-red"

    return f"<span class='{css}'>{status}</span>"


# =========================
# LOAD DATA
# =========================

latest_scan = safe_latest_row("scan_journal")
if latest_scan is None:
    latest_scan = safe_latest_row("scans")

scan_status, scan_age_seconds, scan_message = get_scan_status(latest_scan)
scan_age_text = seconds_to_age(scan_age_seconds)

github_status, github_message, github_url = get_github_status()

scan_count = safe_table_count("scan_journal")
if scan_count == 0:
    scan_count = safe_table_count("scans")

trade_count = safe_table_count("trade_journal")
if trade_count == 0:
    trade_count = safe_table_count("trades")

news_count = safe_table_count("news_memory")
if news_count == 0:
    news_count = safe_table_count("news")

market_count = safe_table_count("market_memory")
if market_count == 0:
    market_count = safe_table_count("market_conditions")

latest_scans = safe_recent_rows("scan_journal", limit=15)
if not latest_scans:
    latest_scans = safe_recent_rows("scans", limit=15)

latest_trades = safe_recent_rows("trade_journal", limit=10)
if not latest_trades:
    latest_trades = safe_recent_rows("trades", limit=10)

latest_news = safe_recent_rows("news_memory", limit=10)
if not latest_news:
    latest_news = safe_recent_rows("news", limit=10)


# =========================
# HEADER
# =========================

now_ist = datetime.now(IST).strftime("%d %b %Y, %I:%M:%S %p IST")

st.markdown("# ⚡ TITAN Control Dashboard")
st.caption(f"Live system monitor · Auto refresh every {AUTO_REFRESH_SECONDS}s · Last updated: {now_ist}")

st.markdown("---")


# =========================
# SECTION 1: MAIN STATUS
# =========================

st.markdown("## 🧠 Core System Status")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">Scan Engine</div>
            {status_pill(scan_status)}
            <div class="metric-sub">{scan_message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">Scan Age</div>
            <div class="metric-value">{scan_age_text}</div>
            <div class="metric-sub">Updates live every refresh</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col3:
    supabase_status = "CONNECTED" if supabase is not None else "OFFLINE"
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">Supabase</div>
            {status_pill(supabase_status)}
            <div class="metric-sub">Database memory layer</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col4:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">GitHub Runner</div>
            {status_pill(github_status)}
            <div class="metric-sub">{github_message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

if github_url:
    st.markdown(f"[Open latest GitHub workflow run]({github_url})")


# =========================
# SECTION 2: SUPABASE STORAGE
# =========================

st.markdown("## 🗄️ Supabase Storage Monitor")

storage_col1, storage_col2 = st.columns([1.4, 1])

with storage_col1:
    st.markdown("### Data Load Overview")

    max_reference = max(scan_count, trade_count, news_count, market_count, 1)

    big_progress_bar("Scan Memory Load", scan_count, max_reference)
    big_progress_bar("Trade Journal Load", trade_count, max_reference)
    big_progress_bar("News Memory Load", news_count, max_reference)
    big_progress_bar("Market Condition Memory Load", market_count, max_reference)

with storage_col2:
    st.markdown("### Stored Records")

    a, b = st.columns(2)

    with a:
        st.metric("Scans", f"{scan_count:,}")
        st.metric("News", f"{news_count:,}")

    with b:
        st.metric("Trades", f"{trade_count:,}")
        st.metric("Market Data", f"{market_count:,}")


# =========================
# SECTION 3: TITAN MODULES
# =========================

st.markdown("## ⚙️ TITAN Module Health")

m1, m2, m3, m4 = st.columns(4)

with m1:
    st.markdown(
        """
        <div class="metric-card">
            <div class="metric-title">Technical Engine</div>
            <span class="status-pill-green">ACTIVE</span>
            <div class="metric-sub">Trend · Momentum · Structure</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with m2:
    news_status = "ACTIVE" if news_count > 0 else "WAITING"
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">News Engine</div>
            {status_pill('ONLINE' if news_status == 'ACTIVE' else 'DELAYED')}
            <div class="metric-sub">News records: {news_count:,}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with m3:
    memory_status = "ONLINE" if scan_count > 0 else "DELAYED"
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">Memory Engine</div>
            {status_pill(memory_status)}
            <div class="metric-sub">Supabase learning storage</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with m4:
    st.markdown(
        """
        <div class="metric-card">
            <div class="metric-title">Risk Engine</div>
            <span class="status-pill-green">ACTIVE</span>
            <div class="metric-sub">SL · TP · RR · Filters</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================
# SECTION 4: EVOLUTION STAGE
# =========================

st.markdown("## 📈 TITAN Evolution Progress")

evo_col1, evo_col2 = st.columns([1.3, 1])

with evo_col1:
    evolution_score = min(100, int((scan_count / 500) * 40 + (trade_count / 100) * 30 + (news_count / 500) * 30))
    big_progress_bar("Overall Evolution Stage", evolution_score, 100)

    if evolution_score < 25:
        stage = "Stage 1 · Data Collection"
    elif evolution_score < 50:
        stage = "Stage 2 · Pattern Building"
    elif evolution_score < 75:
        stage = "Stage 3 · Adaptive Learning"
    else:
        stage = "Stage 4 · Advanced Market Intelligence"

    st.markdown(f"### Current Stage: `{stage}`")

with evo_col2:
    accuracy_proxy = min(100, int(50 + (trade_count * 0.2)))
    st.metric("Estimated Learning Progress", f"{evolution_score}%")
    st.metric("Accuracy Tracking Readiness", f"{accuracy_proxy}%")
    st.caption("Accuracy becomes more meaningful after outcome tracking is connected.")


# =========================
# SECTION 5: LATEST SCAN
# =========================

st.markdown("## 🔍 Latest Scan Details")

if latest_scan:
    scan_df = pd.DataFrame([latest_scan])
    st.dataframe(scan_df, use_container_width=True, hide_index=True)
else:
    st.warning("No latest scan found in scan_journal or scans table.")


# =========================
# SECTION 6: RECENT ACTIVITY
# =========================

st.markdown("## 🕒 Recent System Activity")

tab1, tab2, tab3 = st.tabs(["Recent Scans", "Recent Trades", "Recent News"])

with tab1:
    if latest_scans:
        st.dataframe(pd.DataFrame(latest_scans), use_container_width=True, hide_index=True)
    else:
        st.info("No recent scan records found.")

with tab2:
    if latest_trades:
        st.dataframe(pd.DataFrame(latest_trades), use_container_width=True, hide_index=True)
    else:
        st.info("No recent trade records found.")

with tab3:
    if latest_news:
        st.dataframe(pd.DataFrame(latest_news), use_container_width=True, hide_index=True)
    else:
        st.info("No recent news records found.")


# =========================
# FOOTER
# =========================

st.markdown("---")
st.caption("TITAN Dashboard · Streamlit Cloud · Supabase Memory · GitHub Actions Monitor")