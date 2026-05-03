import os
import time
import requests
from datetime import datetime, timezone

import streamlit as st
from supabase import create_client


st.set_page_config(
    page_title="TITAN Dashboard",
    page_icon="🧠",
    layout="wide"
)

REFRESH_INTERVAL_SECONDS = 5

if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

if time.time() - st.session_state.last_refresh > REFRESH_INTERVAL_SECONDS:
    st.session_state.last_refresh = time.time()
    st.rerun()


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

GITHUB_REPO = os.getenv("GITHUB_REPO")  
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

st.title("🧠 TITAN Command Dashboard")
st.caption("Live monitoring panel for GitHub runs, scans, news, learning, evolution and trade intelligence")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Supabase ENV missing.")
    st.stop()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_table(table_name):
    try:
        response = supabase.table(table_name).select("*").execute()
        return response.data or []
    except:
        return []


def percent(value, target):
    if target <= 0:
        return 0
    return min(int((value / target) * 100), 100)


def progress_bar(title, value):
    st.markdown(
        f"""
<div style="margin-bottom:22px;">
  <div style="display:flex; justify-content:space-between; font-size:16px; font-weight:800; color:#f5f5f5; margin-bottom:8px;">
    <span>{title}</span>
    <span>{value}%</span>
  </div>
  <div style="width:100%; height:18px; background:#242832; border-radius:999px; overflow:hidden; border:1px solid #343946;">
    <div style="width:{value}%; height:100%; background:#1f8cff; border-radius:999px; box-shadow:0 0 12px rgba(31,140,255,0.65);"></div>
  </div>
</div>
        """,
        unsafe_allow_html=True
    )


def engine_card(title, is_running):
    color = "#0f5132" if is_running else "#842029"
    text = "🟢 RUNNING" if is_running else "🔴 OFFLINE"

    st.markdown(
        f"""
<div style="background-color:{color}; padding:15px; border-radius:10px; margin-bottom:10px; color:white; font-weight:bold;">
{title}: {text}
</div>
        """,
        unsafe_allow_html=True
    )


def get_latest_time(data):
    if not data:
        return None

    times = []
    for row in data:
        created = row.get("created_at")
        if created:
            try:
                times.append(datetime.fromisoformat(created.replace("Z", "+00:00")))
            except:
                pass

    if not times:
        return None

    return max(times)


def minutes_since(dt):
    if not dt:
        return None
    now = datetime.now(timezone.utc)
    return int((now - dt).total_seconds() / 60)


def github_status():
    if not GITHUB_REPO:
        return {
            "enabled": False,
            "status": "NOT CONNECTED",
            "conclusion": "Set GITHUB_REPO",
            "updated_at": "N/A",
            "active": False
        }

    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/runs?per_page=1"
        headers = {}

        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()

        run = data["workflow_runs"][0]

        status = run.get("status", "unknown")
        conclusion = run.get("conclusion", "running")
        updated_at = run.get("updated_at", "N/A")

        active = status == "completed" and conclusion == "success"

        return {
            "enabled": True,
            "status": status.upper(),
            "conclusion": str(conclusion).upper(),
            "updated_at": updated_at,
            "active": active
        }

    except Exception as e:
        return {
            "enabled": True,
            "status": "ERROR",
            "conclusion": str(e),
            "updated_at": "N/A",
            "active": False
        }


scan_data = fetch_table("scan_symbols")
trade_data = fetch_table("trade_results")
news_data = fetch_table("news_memory")
learning_data = fetch_table("learning_memory")

scan_count = len(scan_data)
news_count = len(news_data)
learning_count = len(learning_data)
total_trades = len(trade_data)

wins = sum(1 for t in trade_data if str(t.get("result", "")).upper() == "WIN")
losses = sum(1 for t in trade_data if str(t.get("result", "")).upper() == "LOSS")
win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

rr_values = [float(t.get("rr", 0)) for t in trade_data if t.get("rr") is not None]
avg_rr = sum(rr_values) / len(rr_values) if rr_values else 0

latest_scan_time = get_latest_time(scan_data)
scan_age = minutes_since(latest_scan_time)

github = github_status()

github_runner_ok = github["active"]
scan_fresh = scan_age is not None and scan_age <= 10

market_coverage_pct = percent(scan_count, 1000)
news_intelligence_pct = percent(news_count, 500)
learning_strength_pct = percent(learning_count, 100)
accuracy_pct = int(win_rate)
data_strength_pct = percent(scan_count + news_count + learning_count, 1500)

evolution_pct = min(
    int((learning_strength_pct * 0.45) + (news_intelligence_pct * 0.35) + (market_coverage_pct * 0.20)),
    100
)

intelligence_pct = min(
    int((data_strength_pct * 0.40) + (evolution_pct * 0.35) + (news_intelligence_pct * 0.25)),
    100
)

trade_readiness_pct = min(
    int((market_coverage_pct * 0.35) + (news_intelligence_pct * 0.30) + (learning_strength_pct * 0.20) + (accuracy_pct * 0.15)),
    100
)


st.subheader("🚦 TITAN Live Status")

a1, a2, a3, a4 = st.columns(4)

a1.metric("System", "RUNNING")
a2.metric("GitHub Runner", github["status"])
a3.metric("Last Run Result", github["conclusion"])
a4.metric("Last Scan Age", f"{scan_age} min" if scan_age is not None else "N/A")

if not GITHUB_REPO:
    st.warning("GitHub status not connected. Set GITHUB_REPO environment variable like: yourusername/yourrepo")

st.divider()


st.subheader("📊 Performance Metrics")

m1, m2, m3, m4, m5 = st.columns(5)

m1.metric("Total Trades", total_trades)
m2.metric("Wins", wins)
m3.metric("Losses", losses)
m4.metric("Win Rate %", f"{win_rate:.2f}")
m5.metric("Avg RR", f"{avg_rr:.2f}")

st.divider()


st.subheader("🧠 TITAN Intelligence Progress")

p1, p2, p3, p4 = st.columns(4)

with p1:
    progress_bar("Overall Intelligence", intelligence_pct)
    progress_bar("Evolution Progress", evolution_pct)

with p2:
    progress_bar("Accuracy", accuracy_pct)
    progress_bar("Learning Strength", learning_strength_pct)

with p3:
    progress_bar("News Intelligence", news_intelligence_pct)
    progress_bar("Market Coverage", market_coverage_pct)

with p4:
    progress_bar("Trade Readiness", trade_readiness_pct)
    progress_bar("Data Strength", data_strength_pct)

st.divider()


st.subheader("📡 Data Overview")

d1, d2, d3, d4 = st.columns(4)

d1.metric("Scanned Records", scan_count)
d2.metric("News Processed", news_count)
d3.metric("Learning Records", learning_count)
d4.metric("Total Data Points", scan_count + news_count + learning_count)

st.divider()


st.subheader("⚙️ Engine Status")

e1, e2, e3 = st.columns(3)

with e1:
    engine_card("GitHub 5-Min Runner", github_runner_ok)
    engine_card("Scan Engine", scan_fresh)

with e2:
    engine_card("News Engine", news_count > 0)
    engine_card("Trade Engine", total_trades > 0)

with e3:
    engine_card("Learning Engine", learning_count > 0)
    engine_card("Evolution Engine", learning_count > 0)

st.divider()


st.subheader("🧠 TITAN Intelligence Summary")

s1, s2, s3 = st.columns(3)

s1.metric("Signals Generated", total_trades)
s2.metric("Market Coverage", scan_count)
s3.metric("Data Strength", scan_count + news_count + learning_count)

st.divider()
st.caption(f"Last dashboard refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")