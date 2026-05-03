import os
import json
import requests
from datetime import datetime, timezone, timedelta

import streamlit as st
from supabase import create_client
from streamlit_autorefresh import st_autorefresh


st.set_page_config(
    page_title="TITAN Dashboard",
    page_icon="🧠",
    layout="wide"
)

st_autorefresh(interval=5000, key="titan_live_refresh")


SUPABASE_URL = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY")
GITHUB_REPO = os.getenv("GITHUB_REPO") or st.secrets.get("GITHUB_REPO")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or st.secrets.get("GITHUB_TOKEN", "")


st.title("🧠 TITAN Command Dashboard")
st.caption("24/7 monitoring panel for GitHub, Supabase, scans, news, learning, evolution and trade intelligence")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Supabase ENV missing. Check Streamlit secrets.")
    st.stop()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_table(table_name, limit=1000):
    try:
        response = (
            supabase.table(table_name)
            .select("*")
            .limit(limit)
            .execute()
        )
        return response.data or []
    except Exception:
        return []


def percent(value, target):
    if target <= 0:
        return 0
    return min(int((value / target) * 100), 100)


def estimate_size_mb(data):
    try:
        raw = json.dumps(data, default=str)
        return len(raw.encode("utf-8")) / (1024 * 1024)
    except Exception:
        return 0


def to_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def latest_time(data):
    times = []
    for row in data:
        dt = to_dt(row.get("created_at"))
        if dt:
            times.append(dt)
    return max(times) if times else None


def minutes_since(dt):
    if not dt:
        return None
    return int((datetime.now(timezone.utc) - dt).total_seconds() / 60)


def format_ist(dt):
    if not dt:
        return "N/A"
    ist = dt.astimezone(timezone(timedelta(hours=5, minutes=30)))
    return ist.strftime("%d %b %Y, %I:%M:%S %p")


def progress_bar(title, value):
    st.markdown(
        f"""
<div style="margin-bottom:20px;">
  <div style="display:flex; justify-content:space-between; font-weight:800; font-size:15px; margin-bottom:6px;">
    <span>{title}</span>
    <span>{value}%</span>
  </div>
  <div style="width:100%; height:17px; background:#242832; border-radius:999px; overflow:hidden; border:1px solid #343946;">
    <div style="width:{value}%; height:100%; background:#1f8cff; border-radius:999px;"></div>
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
<div style="background:{color}; padding:13px; border-radius:8px; margin-bottom:9px; color:white; font-weight:800;">
{title}: {text}
</div>
        """,
        unsafe_allow_html=True
    )


def github_status():
    if not GITHUB_REPO:
        return {
            "status": "NOT SET",
            "conclusion": "-",
            "active": False,
            "updated_at": None,
            "run_age": None
        }

    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/runs?per_page=1"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()
        run = data["workflow_runs"][0]

        status = run.get("status", "")
        conclusion = run.get("conclusion", "")
        updated_at = to_dt(run.get("updated_at"))

        active = status == "completed" and conclusion == "success"
        run_age = minutes_since(updated_at)

        return {
            "status": status.upper(),
            "conclusion": str(conclusion).upper(),
            "active": active,
            "updated_at": updated_at,
            "run_age": run_age
        }

    except Exception:
        return {
            "status": "ERROR",
            "conclusion": "-",
            "active": False,
            "updated_at": None,
            "run_age": None
        }


scan_data = fetch_table("scan_symbols")
trade_data = fetch_table("trade_results")
news_data = fetch_table("news_memory")
learning_data = fetch_table("learning_memory")

scan_count = len(scan_data)
trade_count = len(trade_data)
news_count = len(news_data)
learning_count = len(learning_data)
total_data_points = scan_count + news_count + learning_count + trade_count

scan_size = estimate_size_mb(scan_data)
trade_size = estimate_size_mb(trade_data)
news_size = estimate_size_mb(news_data)
learning_size = estimate_size_mb(learning_data)
total_estimated_size = scan_size + trade_size + news_size + learning_size

latest_scan = latest_time(scan_data)
latest_news = latest_time(news_data)
latest_learning = latest_time(learning_data)

scan_age = minutes_since(latest_scan)
news_age = minutes_since(latest_news)
learning_age = minutes_since(latest_learning)

github = github_status()

wins = sum(1 for t in trade_data if str(t.get("result", "")).upper() == "WIN")
losses = sum(1 for t in trade_data if str(t.get("result", "")).upper() == "LOSS")
pending = max(trade_count - wins - losses, 0)

win_rate = (wins / trade_count * 100) if trade_count else 0

rr_values = []
for t in trade_data:
    try:
        if t.get("rr") is not None:
            rr_values.append(float(t.get("rr")))
    except Exception:
        pass

avg_rr = sum(rr_values) / len(rr_values) if rr_values else 0


market_pct = percent(scan_count, 1000)
news_pct = percent(news_count, 500)
learn_pct = percent(learning_count, 100)
accuracy_pct = int(win_rate)
data_pct = percent(total_data_points, 1500)
supabase_storage_pct = percent(total_estimated_size, 500)

evolution_pct = min(int((learn_pct * 0.45) + (news_pct * 0.35) + (market_pct * 0.20)), 100)
intelligence_pct = min(int((data_pct * 0.40) + (evolution_pct * 0.35) + (news_pct * 0.25)), 100)
trade_ready_pct = min(int((market_pct * 0.35) + (news_pct * 0.30) + (learn_pct * 0.20) + (accuracy_pct * 0.15)), 100)

scan_fresh = scan_age is not None and scan_age <= 10
github_fresh = github["run_age"] is not None and github["run_age"] <= 10


st.subheader("🚦 TITAN Live Status")

a1, a2, a3, a4, a5 = st.columns(5)
a1.metric("System", "RUNNING")
a2.metric("GitHub", github["status"])
a3.metric("Result", github["conclusion"])
a4.metric("GitHub Run Age", f"{github['run_age']} min" if github["run_age"] is not None else "N/A")
a5.metric("Last Scan Age", f"{scan_age} min" if scan_age is not None else "N/A")

st.caption(f"Latest GitHub Run: {format_ist(github['updated_at'])}")
st.caption(f"Latest Scan Stored: {format_ist(latest_scan)}")

st.divider()


st.subheader("🗄️ Supabase Storage Details")

db1, db2, db3, db4, db5 = st.columns(5)
db1.metric("Supabase", "CONNECTED")
db2.metric("Total Rows", total_data_points)
db3.metric("Estimated Size", f"{total_estimated_size:.2f} MB")
db4.metric("Tables Active", "4 / 4")
db5.metric("Storage Load", f"{supabase_storage_pct}%")

progress_bar("Supabase Data Load", supabase_storage_pct)

t1, t2, t3, t4 = st.columns(4)
t1.metric("scan_symbols", f"{scan_count} rows", f"{scan_size:.2f} MB")
t2.metric("news_memory", f"{news_count} rows", f"{news_size:.2f} MB")
t3.metric("learning_memory", f"{learning_count} rows", f"{learning_size:.2f} MB")
t4.metric("trade_results", f"{trade_count} rows", f"{trade_size:.2f} MB")

st.divider()


st.subheader("📊 Trading Performance")

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Signals / Trades", trade_count)
m2.metric("Wins", wins)
m3.metric("Losses", losses)
m4.metric("Pending", pending)
m5.metric("Win Rate", f"{win_rate:.2f}%")
m6.metric("Avg RR", f"{avg_rr:.2f}")

st.divider()


st.subheader("🧠 TITAN Intelligence Progress")

p1, p2, p3, p4 = st.columns(4)

with p1:
    progress_bar("Overall Intelligence", intelligence_pct)
    progress_bar("Evolution", evolution_pct)

with p2:
    progress_bar("Accuracy", accuracy_pct)
    progress_bar("Learning", learn_pct)

with p3:
    progress_bar("News Intelligence", news_pct)
    progress_bar("Market Coverage", market_pct)

with p4:
    progress_bar("Trade Readiness", trade_ready_pct)
    progress_bar("Data Strength", data_pct)

st.divider()


st.subheader("📡 Data Overview")

d1, d2, d3, d4, d5 = st.columns(5)
d1.metric("Scan Records", scan_count)
d2.metric("News Records", news_count)
d3.metric("Learning Records", learning_count)
d4.metric("Trade Records", trade_count)
d5.metric("Total Data Points", total_data_points)

st.caption(f"Latest News Stored: {format_ist(latest_news)}")
st.caption(f"Latest Learning Stored: {format_ist(latest_learning)}")

st.divider()


st.subheader("⚙️ Engine Status")

e1, e2, e3 = st.columns(3)

with e1:
    engine_card("GitHub 5-Min Runner", github["active"] and github_fresh)
    engine_card("Scan Engine", scan_fresh)

with e2:
    engine_card("Supabase Storage", total_data_points > 0)
    engine_card("News Engine", news_count > 0 and (news_age is None or news_age <= 1440))

with e3:
    engine_card("Learning Engine", learning_count > 0)
    engine_card("Trade Engine", trade_count > 0)
    engine_card("Evolution Engine", learning_count > 0)

st.divider()


st.subheader("🧠 TITAN Summary")

s1, s2, s3, s4 = st.columns(4)
s1.metric("Market Coverage", scan_count)
s2.metric("Data Strength", total_data_points)
s3.metric("Readiness", f"{trade_ready_pct}%")
s4.metric("Intelligence", f"{intelligence_pct}%")

st.divider()
st.caption(f"Dashboard refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")