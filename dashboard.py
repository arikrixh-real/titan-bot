import os
import time
import requests
from datetime import datetime, timezone

import streamlit as st
from supabase import create_client


# ================= CONFIG =================
st.set_page_config(
    page_title="TITAN Dashboard",
    page_icon="🧠",
    layout="wide"
)

# ================= AUTO REFRESH =================
REFRESH_INTERVAL_SECONDS = 5

if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

if time.time() - st.session_state.last_refresh > REFRESH_INTERVAL_SECONDS:
    st.session_state.last_refresh = time.time()
    st.rerun()


# ================= ENV / SECRETS FIX =================
SUPABASE_URL = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY")

GITHUB_REPO = os.getenv("GITHUB_REPO") or st.secrets.get("GITHUB_REPO")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or st.secrets.get("GITHUB_TOKEN", "")


st.title("🧠 TITAN Command Dashboard")
st.caption("Live monitoring panel for GitHub runs, scans, news, learning, evolution and trade intelligence")

# ================= ERROR CHECK =================
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Supabase ENV missing. Check Streamlit secrets.")
    st.stop()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ================= HELPERS =================
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
<div style="margin-bottom:20px;">
  <div style="display:flex; justify-content:space-between; font-weight:800; font-size:15px; margin-bottom:6px;">
    <span>{title}</span>
    <span>{value}%</span>
  </div>
  <div style="width:100%; height:16px; background:#242832; border-radius:999px; overflow:hidden;">
    <div style="width:{value}%; height:100%; background:#1f8cff;"></div>
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
<div style="background:{color}; padding:12px; border-radius:8px; margin-bottom:8px; color:white; font-weight:bold;">
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
        t = row.get("created_at")
        if t:
            try:
                times.append(datetime.fromisoformat(t.replace("Z", "+00:00")))
            except:
                pass
    return max(times) if times else None


def minutes_since(dt):
    if not dt:
        return None
    return int((datetime.now(timezone.utc) - dt).total_seconds() / 60)


def github_status():
    if not GITHUB_REPO:
        return {"status": "NOT SET", "conclusion": "-", "active": False}

    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/runs?per_page=1"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()
        run = data["workflow_runs"][0]

        status = run.get("status", "")
        conclusion = run.get("conclusion", "")

        active = status == "completed" and conclusion == "success"

        return {
            "status": status.upper(),
            "conclusion": str(conclusion).upper(),
            "active": active
        }
    except:
        return {"status": "ERROR", "conclusion": "-", "active": False}


# ================= DATA =================
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
win_rate = (wins / total_trades * 100) if total_trades else 0

rr_values = [float(t.get("rr", 0)) for t in trade_data if t.get("rr") is not None]
avg_rr = sum(rr_values) / len(rr_values) if rr_values else 0


# ================= GITHUB + SCAN =================
github = github_status()
latest_scan = get_latest_time(scan_data)
scan_age = minutes_since(latest_scan)

github_ok = github["active"]
scan_fresh = scan_age is not None and scan_age <= 10


# ================= CALCULATIONS =================
market_pct = percent(scan_count, 1000)
news_pct = percent(news_count, 500)
learn_pct = percent(learning_count, 100)
accuracy_pct = int(win_rate)

data_pct = percent(scan_count + news_count + learning_count, 1500)

evolution_pct = min(int((learn_pct * 0.45) + (news_pct * 0.35) + (market_pct * 0.20)), 100)
intelligence_pct = min(int((data_pct * 0.40) + (evolution_pct * 0.35) + (news_pct * 0.25)), 100)
trade_ready_pct = min(int((market_pct * 0.35) + (news_pct * 0.30) + (learn_pct * 0.20) + (accuracy_pct * 0.15)), 100)


# ================= UI =================
st.subheader("🚦 TITAN Live Status")

a1, a2, a3, a4 = st.columns(4)
a1.metric("System", "RUNNING")
a2.metric("GitHub", github["status"])
a3.metric("Result", github["conclusion"])
a4.metric("Last Scan", f"{scan_age} min" if scan_age else "N/A")

st.divider()


st.subheader("📊 Performance")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Trades", total_trades)
m2.metric("Wins", wins)
m3.metric("Losses", losses)
m4.metric("Win %", f"{win_rate:.2f}")
m5.metric("Avg RR", f"{avg_rr:.2f}")

st.divider()


st.subheader("🧠 Intelligence")

p1, p2, p3, p4 = st.columns(4)

with p1:
    progress_bar("Overall", intelligence_pct)
    progress_bar("Evolution", evolution_pct)

with p2:
    progress_bar("Accuracy", accuracy_pct)
    progress_bar("Learning", learn_pct)

with p3:
    progress_bar("News", news_pct)
    progress_bar("Coverage", market_pct)

with p4:
    progress_bar("Readiness", trade_ready_pct)
    progress_bar("Data", data_pct)

st.divider()


st.subheader("⚙️ Engine Status")

e1, e2, e3 = st.columns(3)

with e1:
    engine_card("GitHub Runner", github_ok)
    engine_card("Scan Engine", scan_fresh)

with e2:
    engine_card("News Engine", news_count > 0)
    engine_card("Trade Engine", total_trades > 0)

with e3:
    engine_card("Learning Engine", learning_count > 0)
    engine_card("Evolution Engine", learning_count > 0)


st.divider()
st.caption(f"Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")