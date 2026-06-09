import os
import json
import glob
import time
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from supabase import create_client, Client
from engines.time_filter import current_bot_mode
from utils.market_hours import IST, is_trade_window
from dashboard_truth import build_dashboard_truth_consolidation


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
    page_title="TITAN Control System",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

AUTO_REFRESH_SECONDS = 10
SCAN_BATCH_SIZE = 50
INITIAL_BALANCE = 1000.0
REAL_PNL_SOURCE_LABEL = "REAL_STOCK_WISE_PNL | QTY_SYNC_ACTIVE"
DASHBOARD_VISUAL_VERSION = "REAL_PNL_QTY_SYNC_FIX_V1"
PAPER_ACCOUNT_PATH = "/".join(["data", "paper_trading", "paper_account.json"])
DASHBOARD_SYNC_STATUS_PATH = "/".join(["data", "runtime", "dashboard_sync_status.json"])
JOURNAL_TRUTH_UNIFICATION_PATH = "/".join(["data", "runtime", "journal_truth_unification.json"])
PAPER_ENGINE_STATUS_PATH = "/".join(["data", "runtime", "paper_engine_status.json"])
SCANNER_STATUS_PATH = "/".join(["data", "runtime", "scanner_status.json"])
SCANNER_FILTER_TRUTH_STATUS_PATH = "/".join(["data", "runtime", "scanner_filter_truth_status.json"])
FINAL_VALIDATED_SETUPS_PATH = "/".join(["data", "runtime", "final_validated_setups.json"])
OHLC_HEALTH_STATUS_PATH = "/".join(["data", "runtime", "ohlc_health.json"])
TRADE_LIFECYCLE_HEALTH_PATH = "/".join(["data", "runtime", "trade_lifecycle_health.json"])
TRADE_LIFECYCLE_RECONCILIATION_PATH = "/".join(["data", "runtime", "trade_lifecycle_reconciliation.json"])
REJECTION_HEATMAP_PATH = "/".join(["data", "runtime", "rejection_heatmap.json"])
SIDEWAYS_ANALYSIS_PATH = "/".join(["data", "runtime", "sideways_analysis.json"])
LIVE_PRICE_MONITOR_STATUS_PATH = "/".join(["data", "runtime", "live_price_monitor_status.json"])
RUNTIME_RESILIENCE_STATUS_PATH = "/".join(["data", "runtime", "runtime_resilience_status.json"])
PYRAMID_GOVERNANCE_STATUS_PATH = "/".join(["data", "runtime", "pyramid_governance_status.json"])
WEEKEND_RESEARCH_MODE_STATUS_PATH = "/".join(["data", "runtime", "weekend_research_mode_status.json"])
TITAN_RUNTIME_STATUS_PATH = "/".join(["data", "runtime", "titan_runtime_status.json"])
EVOLUTION_MEMORY_PATH = "/".join(["data", "runtime", "evolution_memory.json"])
STRATEGY_WEIGHT_CHANGE_LOG_PATH = "/".join(["data", "runtime", "strategy_weight_change_log.json"])
REINFORCEMENT_LEARNING_STATUS_PATH = "/".join(["data", "runtime", "reinforcement_learning_status.json"])
META_LEARNING_STATUS_PATH = "/".join(["data", "runtime", "meta_learning_status.json"])
RUNTIME_STATUS_TABLE = "runtime_status"
RUNTIME_FRESH_SECONDS = 15 * 60
SCANNER_STALE_SECONDS = 7 * 60
SCANNER_SIGNATURE_REPEAT_WARNING_CYCLES = 3
SCANNER_FRESH_SECONDS_BY_MODE = {
    "MARKET_MODE": 10 * 60,
    "INTELLIGENCE_MODE": 24 * 3600,
    "RESEARCH_MODE": 24 * 3600,
    "WEEKEND_MODE": 72 * 3600,
}
RUNTIME_STATUS_KEYS = [
    "dashboard_sync",
    "titan_heartbeat",
    "daemon_health",
    "titan_runtime_status",
    "runtime_resilience_status",
    "pyramid_governance_status",
    "weekend_research_mode_status",
    "scanner_status",
    "live_price_monitor_status",
    "master_brain_status",
    "paper_engine_status",
]


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

    .block-container {
        padding-top: 0.45rem;
        padding-bottom: 0.8rem;
    }

    .block-container h1 {
        font-size: 1.45rem;
        line-height: 1.05;
        margin: 0 0 0.25rem 0;
    }

    .block-container h2,
    .block-container h3 {
        font-size: 0.95rem;
        line-height: 1.1;
        margin: 0.15rem 0 0.2rem 0;
    }

    .block-container [data-testid="stVerticalBlock"] {
        gap: 0.35rem;
    }

    .block-container [data-testid="stHorizontalBlock"] {
        gap: 0.45rem;
    }

    .block-container [data-testid="stVerticalBlockBorderWrapper"] {
        padding: 0.35rem;
    }

    .block-container div[data-testid="stDataFrame"] {
        margin-top: 0.15rem;
    }

    .terminal-kpi {
        background: #0b1220;
        border: 1px solid #253044;
        border-left: 4px solid #253044;
        border-radius: 6px;
        padding: 7px 9px;
        min-height: 58px;
        overflow: hidden;
    }

    .terminal-kpi-label {
        color: #94a3b8;
        font-size: 10px;
        font-weight: 800;
        line-height: 1;
        text-transform: uppercase;
        margin-bottom: 4px;
    }

    .terminal-kpi-value {
        color: #ffffff;
        font-size: 18px;
        font-weight: 900;
        line-height: 1.05;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .terminal-kpi-meta {
        color: #64748b;
        font-size: 10px;
        font-weight: 650;
        line-height: 1.15;
        margin-top: 3px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .terminal-panel {
        background: #0b1220;
        border: 1px solid #253044;
        border-radius: 6px;
        padding: 7px 9px;
        min-height: 96px;
    }

    .terminal-panel-title {
        color: #94a3b8;
        font-size: 10px;
        font-weight: 800;
        text-transform: uppercase;
        margin-bottom: 4px;
    }

    .mini-flow-strip {
        display: flex;
        align-items: center;
        gap: 5px;
        min-height: 42px;
        white-space: nowrap;
        overflow: hidden;
    }

    .flow-chip {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        color: #94a3b8;
        border: 1px solid #253044;
        background: #0f172a;
        border-radius: 4px;
        padding: 4px 6px;
        font-size: 10px;
        font-weight: 900;
        line-height: 1;
    }

    .flow-chip.active {
        color: #001b16;
        border-color: #00ffc8;
        background: #00ffc8;
    }

    .flow-arrow {
        color: #475569;
        font-size: 10px;
        font-weight: 900;
    }

    /* =====================================================
       TITAN V4 COMMAND CENTER VISUAL LAYER
       ===================================================== */
    .stApp {
        background:
            linear-gradient(rgba(96,165,250,0.025) 1px, transparent 1px),
            linear-gradient(90deg, rgba(96,165,250,0.018) 1px, transparent 1px),
            radial-gradient(circle at 18% 0%, rgba(37, 99, 235, 0.18), transparent 28%),
            radial-gradient(circle at 90% 10%, rgba(14, 165, 233, 0.12), transparent 24%),
            #07111f;
        background-size: 32px 32px, 32px 32px, auto, auto, auto;
    }

    .block-container {
        max-width: 1880px;
        padding: 0.95rem 1.25rem 1.25rem 1.25rem;
    }

    section[data-testid="stSidebar"] {
        background: #081321;
        border-right: 1px solid rgba(96, 165, 250, 0.16);
        min-width: 292px !important;
        width: 292px !important;
        box-shadow: 18px 0 50px rgba(0, 0, 0, 0.18);
    }

    section[data-testid="stSidebar"] > div {
        padding: 1.15rem 1rem 1rem 1rem;
        width: 292px !important;
    }

    header[data-testid="stHeader"] {
        background: transparent;
        height: 0;
    }

    div[data-testid="stToolbar"],
    div[data-testid="stDecoration"],
    div[data-testid="stStatusWidget"] {
        display: none !important;
    }

    .block-container > div[data-testid="stVerticalBlock"] {
        gap: 0.95rem;
    }

    div[data-testid="stHorizontalBlock"] {
        gap: 1rem;
    }

    div[data-testid="column"] {
        min-width: 0;
    }

    div[data-testid="stExpander"] {
        border: 1px solid rgba(96, 165, 250, 0.16);
        border-radius: 12px;
        background: rgba(8, 19, 33, 0.72);
        margin-top: 12px;
    }

    div[data-testid="stExpander"] summary {
        color: #93a4bb;
        font-weight: 850;
    }

    .v4-sidebar-brand {
        border: 1px solid rgba(96, 165, 250, 0.22);
        background: linear-gradient(180deg, #0f2034 0%, #0b1728 100%);
        border-radius: 12px;
        padding: 18px 15px;
        margin-bottom: 18px;
    }

    .v4-logo-row {
        display: flex;
        align-items: center;
        gap: 10px;
    }

    .v4-logo-mark {
        width: 38px;
        height: 38px;
        border-radius: 10px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        color: #dbeafe;
        font-weight: 950;
        background: linear-gradient(135deg, #2563eb, #0ea5e9);
        box-shadow: 0 0 24px rgba(37, 99, 235, 0.35);
    }

    .v4-brand-title {
        color: #f8fafc;
        font-size: 20px;
        font-weight: 950;
        letter-spacing: 0;
        line-height: 1.05;
    }

    .v4-brand-sub {
        color: #93a4bb;
        font-size: 12px;
        font-weight: 750;
        margin-top: 3px;
    }

    .v4-sidebar-block {
        border: 1px solid rgba(148, 163, 184, 0.16);
        background: #0b1728;
        border-radius: 12px;
        padding: 14px;
        margin: 16px 0;
    }

    .v4-sidebar-block-title {
        color: #64748b;
        font-size: 11px;
        font-weight: 900;
        text-transform: uppercase;
        margin-bottom: 10px;
    }

    .v4-action-row,
    .v4-version-row {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        color: #cbd5e1;
        font-size: 12.5px;
        font-weight: 760;
        padding: 7px 0;
        border-bottom: 1px solid rgba(148, 163, 184, 0.08);
    }

    .v4-action-row:last-child,
    .v4-version-row:last-child {
        border-bottom: 0;
    }

    section[data-testid="stSidebar"] div[data-testid="stRadio"] label {
        min-height: 42px;
        border-radius: 10px;
        padding: 10px 12px !important;
        margin-bottom: 6px;
        color: #94a3b8;
        border: 1px solid transparent;
        background: transparent;
    }

    section[data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input:checked) {
        background: linear-gradient(90deg, #1d4ed8 0%, #2563eb 100%) !important;
        border-color: #7dd3fc;
        box-shadow: 0 12px 28px rgba(29, 78, 216, 0.34);
        color: #ffffff !important;
    }

    section[data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input:checked) * {
        color: #ffffff !important;
        font-weight: 900 !important;
    }

    .v4-topbar {
        display: grid;
        grid-template-columns: minmax(360px, 1fr) 230px 205px 185px;
        gap: 16px;
        align-items: center;
        border: 1px solid rgba(96, 165, 250, 0.18);
        background: rgba(9, 20, 35, 0.92);
        border-radius: 14px;
        padding: 20px 22px;
        margin-bottom: 18px;
        box-shadow: 0 18px 50px rgba(0, 0, 0, 0.22);
        position: sticky;
        top: 0;
        z-index: 20;
        backdrop-filter: blur(10px);
    }

    .v4-page-title {
        color: #f8fafc;
        font-size: 34px;
        font-weight: 950;
        line-height: 1;
        margin-bottom: 6px;
    }

    .v4-page-subtitle {
        color: #93a4bb;
        font-size: 15px;
        font-weight: 760;
    }

    .v4-top-stat {
        min-width: 0;
        border: 1px solid rgba(148, 163, 184, 0.14);
        background: #0b1728;
        border-radius: 11px;
        padding: 12px 14px;
    }

    .v4-top-label {
        color: #64748b;
        font-size: 10px;
        font-weight: 950;
        text-transform: uppercase;
        margin-bottom: 4px;
    }

    .v4-top-value {
        color: #e5eefb;
        font-size: 14px;
        font-weight: 900;
        white-space: nowrap;
    }

    .v4-refresh-dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 999px;
        background: #22c55e;
        box-shadow: 0 0 14px rgba(34, 197, 94, 0.8);
        margin-right: 8px;
    }

    .v4-kpi-grid {
        display: grid;
        grid-template-columns: repeat(5, minmax(0, 1fr));
        gap: 16px;
        margin-bottom: 18px;
    }

    .v4-kpi-card {
        position: relative;
        min-height: 176px;
        border-radius: 14px;
        border: 1px solid rgba(148, 163, 184, 0.16);
        background: linear-gradient(180deg, #0e1a2b 0%, #0a1424 100%);
        padding: 20px;
        overflow: hidden;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
        transform: translateZ(0);
    }

    .v4-kpi-card:before {
        content: "";
        position: absolute;
        inset: 0;
        background: linear-gradient(135deg, rgba(96, 165, 250, 0.10), transparent 44%);
        pointer-events: none;
    }

    .v4-kpi-label {
        position: relative;
        color: #93a4bb;
        font-size: 12.5px;
        font-weight: 950;
        text-transform: uppercase;
        margin-bottom: 14px;
    }

    .v4-kpi-value {
        position: relative;
        color: #f8fafc;
        font-size: 34px;
        font-weight: 950;
        line-height: 1.05;
        overflow-wrap: anywhere;
    }

    .v4-kpi-meta {
        position: relative;
        color: #7f91aa;
        font-size: 12.5px;
        font-weight: 760;
        margin-top: 12px;
        line-height: 1.25;
    }

    .v4-sparkline {
        position: absolute;
        left: 18px;
        right: 18px;
        bottom: 14px;
        height: 32px;
        opacity: 0.88;
    }

    .v4-status-good { color: #22c55e !important; }
    .v4-status-warn { color: #facc15 !important; }
    .v4-status-bad { color: #ef4444 !important; }
    .v4-status-unknown { color: #94a3b8 !important; }

    .v4-main-grid {
        display: grid;
        grid-template-columns: 1.08fr 1.08fr 1.08fr 1fr;
        gap: 16px;
        margin-bottom: 18px;
    }

    .v4-panel {
        border: 1px solid rgba(148, 163, 184, 0.16);
        background: rgba(10, 20, 36, 0.94);
        border-radius: 14px;
        padding: 18px;
        min-height: 330px;
    }

    .v4-panel-title-row {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        align-items: center;
        margin-bottom: 16px;
    }

    .v4-panel-title {
        color: #f8fafc;
        font-size: 19px;
        font-weight: 950;
        line-height: 1.15;
    }

    .v4-count-pill {
        border-radius: 999px;
        padding: 5px 9px;
        color: #dbeafe;
        background: rgba(37, 99, 235, 0.20);
        border: 1px solid rgba(96, 165, 250, 0.28);
        font-size: 12px;
        font-weight: 950;
    }

    .v4-list {
        display: flex;
        flex-direction: column;
        gap: 10px;
    }

    .v4-list-item {
        border: 1px solid rgba(148, 163, 184, 0.12);
        background: #0d1a2b;
        border-radius: 10px;
        padding: 12px 13px;
        min-height: 58px;
    }

    .v4-list-top {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        align-items: center;
        margin-bottom: 4px;
    }

    .v4-list-name {
        color: #e5eefb;
        font-size: 14.5px;
        font-weight: 900;
        overflow-wrap: anywhere;
    }

    .v4-list-meta {
        color: #7f91aa;
        font-size: 12.5px;
        font-weight: 720;
        line-height: 1.25;
        overflow-wrap: anywhere;
    }

    .v4-status-pill {
        flex: 0 0 auto;
        border-radius: 999px;
        padding: 5px 8px;
        font-size: 10.5px;
        font-weight: 950;
        border: 1px solid rgba(148, 163, 184, 0.16);
        background: rgba(148, 163, 184, 0.10);
        color: #cbd5e1;
    }

    .v4-status-pill.good {
        background: rgba(34, 197, 94, 0.12);
        border-color: rgba(34, 197, 94, 0.34);
        color: #4ade80;
    }

    .v4-status-pill.warn {
        background: rgba(250, 204, 21, 0.12);
        border-color: rgba(250, 204, 21, 0.34);
        color: #fde047;
    }

    .v4-status-pill.bad {
        background: rgba(239, 68, 68, 0.12);
        border-color: rgba(239, 68, 68, 0.34);
        color: #f87171;
    }

    .v4-mini-metrics {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px;
    }

    .v4-mini-metric {
        border: 1px solid rgba(148, 163, 184, 0.12);
        background: #0d1a2b;
        border-radius: 10px;
        padding: 12px;
        min-height: 84px;
    }

    .v4-mini-label {
        color: #7f91aa;
        font-size: 11.5px;
        font-weight: 900;
        text-transform: uppercase;
        margin-bottom: 7px;
    }

    .v4-mini-value {
        color: #f8fafc;
        font-size: 19px;
        font-weight: 950;
        overflow-wrap: anywhere;
    }

    .v4-mindmap {
        border: 1px solid rgba(148, 163, 184, 0.16);
        background: rgba(10, 20, 36, 0.96);
        border-radius: 14px;
        padding: 20px;
        margin-bottom: 14px;
    }

    .v4-pyramid {
        display: flex;
        flex-direction: column;
        gap: 18px;
        align-items: center;
        padding: 10px 0 4px 0;
    }

    .v4-pyramid-row {
        position: relative;
        display: grid;
        gap: 16px;
        justify-content: center;
        width: 100%;
    }

    .v4-pyramid-row:before {
        content: "";
        position: absolute;
        top: -12px;
        left: 14%;
        right: 14%;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(96, 165, 250, 0.38), transparent);
    }

    .v4-pyramid-row:first-child:before {
        display: none;
    }

    .v4-pyramid-row.top { grid-template-columns: minmax(260px, 360px); }
    .v4-pyramid-row.mid { grid-template-columns: repeat(3, minmax(230px, 310px)); }
    .v4-pyramid-row.base { grid-template-columns: repeat(5, minmax(175px, 245px)); }

    .v4-node {
        position: relative;
        border-radius: 12px;
        border: 1px solid rgba(148, 163, 184, 0.18);
        background: #0d1a2b;
        padding: 15px;
        min-height: 104px;
        text-align: left;
    }

    .v4-node:after {
        content: "";
        position: absolute;
        left: 50%;
        top: -18px;
        width: 1px;
        height: 18px;
        background: rgba(96, 165, 250, 0.32);
    }

    .v4-pyramid-row:first-child .v4-node:after {
        display: none;
    }

    .v4-node.good {
        border-color: rgba(34, 197, 94, 0.36);
        box-shadow: inset 3px 0 0 #22c55e;
    }

    .v4-node.warn {
        border-color: rgba(250, 204, 21, 0.38);
        box-shadow: inset 3px 0 0 #facc15;
    }

    .v4-node.bad {
        border-color: rgba(239, 68, 68, 0.38);
        box-shadow: inset 3px 0 0 #ef4444;
    }

    .v4-node-name {
        color: #f8fafc;
        font-size: 15px;
        font-weight: 950;
        margin-bottom: 8px;
    }

    .v4-node-state {
        font-size: 12.5px;
        font-weight: 950;
        margin-bottom: 7px;
    }

    .v4-node-meta {
        color: #7f91aa;
        font-size: 11.5px;
        font-weight: 720;
        line-height: 1.25;
    }

    .titan-tv-pulse {
        height: 4px;
        border-radius: 999px;
        overflow: hidden;
        background: rgba(30, 41, 59, 0.72);
        border: 1px solid rgba(96, 165, 250, 0.14);
        margin: 0 0 14px 0;
    }

    .titan-tv-pulse:before {
        content: "";
        display: block;
        width: 32%;
        height: 100%;
        background: linear-gradient(90deg, transparent, #38bdf8, #22c55e, transparent);
        animation: titanPulseSweep 4.8s linear infinite;
    }

    @keyframes titanPulseSweep {
        from { transform: translateX(-120%); }
        to { transform: translateX(340%); }
    }

    .os-section-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 16px;
        margin-bottom: 18px;
    }

    .mindmap-shell {
        position: relative;
        min-height: 690px;
        border: 1px solid rgba(96,165,250,0.18);
        border-radius: 16px;
        background:
            radial-gradient(circle at 50% 0%, rgba(56,189,248,0.10), transparent 32%),
            rgba(8, 18, 32, 0.96);
        overflow: hidden;
        padding: 24px;
    }

    .mindmap-lines {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
        opacity: 0.62;
    }

    .mindmap-tree {
        position: relative;
        z-index: 1;
        display: grid;
        grid-template-rows: auto auto auto;
        gap: 34px;
        height: 100%;
    }

    .mindmap-tier {
        display: flex;
        justify-content: center;
        gap: 18px;
        flex-wrap: wrap;
    }

    .mindmap-node {
        width: 210px;
        min-height: 92px;
        border: 1px solid rgba(148,163,184,0.20);
        border-radius: 12px;
        background: #0d1a2b;
        padding: 14px;
        box-shadow: inset 3px 0 0 #64748b;
    }

    .mindmap-node.core {
        width: 280px;
        min-height: 108px;
        background: #10233a;
    }

    .mindmap-node.good {
        border-color: rgba(34,197,94,0.42);
        box-shadow: inset 4px 0 0 #22c55e;
    }

    .mindmap-node.warn {
        border-color: rgba(245,158,11,0.48);
        box-shadow: inset 4px 0 0 #f59e0b;
    }

    .mindmap-node.bad {
        border-color: rgba(239,68,68,0.48);
        box-shadow: inset 4px 0 0 #ef4444;
    }

    .mindmap-node.unknown {
        border-color: rgba(148,163,184,0.28);
        box-shadow: inset 4px 0 0 #64748b;
    }

    .mindmap-name {
        color: #f8fafc;
        font-size: 15px;
        font-weight: 950;
        margin-bottom: 9px;
    }

    .mindmap-meta {
        color: #94a3b8;
        font-size: 11px;
        font-weight: 760;
        line-height: 1.35;
    }

    @media (max-width: 1280px) {
        .v4-topbar,
        .v4-kpi-grid,
        .v4-main-grid,
        .os-section-grid {
            grid-template-columns: 1fr;
        }

        .v4-pyramid-row.top,
        .v4-pyramid-row.mid,
        .v4-pyramid-row.base {
            grid-template-columns: 1fr;
        }
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


@st.cache_data(ttl=AUTO_REFRESH_SECONDS)
def get_supabase_runtime_status_payloads():
    if supabase is None:
        return {}
    try:
        result = (
            supabase.table(RUNTIME_STATUS_TABLE)
            .select("status_key,payload,timestamp_ist")
            .in_("status_key", RUNTIME_STATUS_KEYS)
            .execute()
        )
    except Exception:
        return {}

    rows = result.data if isinstance(result.data, list) else []
    payloads = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        status_key = str(row.get("status_key") or "").strip()
        payload = row.get("payload")
        if not status_key or not isinstance(payload, dict):
            continue
        payload = dict(payload)
        if row.get("timestamp_ist") and not payload.get("timestamp_ist"):
            payload["timestamp_ist"] = row.get("timestamp_ist")
        payloads[status_key] = payload
    return payloads


def build_runtime_status_from_supabase():
    payloads = get_supabase_runtime_status_payloads()
    if not payloads:
        return None

    dashboard_sync = payloads.get("dashboard_sync")
    data = dict(dashboard_sync) if isinstance(dashboard_sync, dict) else {}
    mapping = {
        "heartbeat": payloads.get("titan_heartbeat"),
        "daemon_health": payloads.get("daemon_health"),
        "runtime_status": payloads.get("titan_runtime_status"),
        "runtime_resilience_status": payloads.get("runtime_resilience_status"),
        "pyramid_governance_status": payloads.get("pyramid_governance_status"),
        "weekend_research_mode_status": payloads.get("weekend_research_mode_status"),
        "scanner_status": payloads.get("scanner_status"),
        "live_price_monitor_status": payloads.get("live_price_monitor_status"),
        "master_brain_status": payloads.get("master_brain_status"),
        "paper_engine_status": payloads.get("paper_engine_status"),
    }
    for target_key, payload in mapping.items():
        if isinstance(payload, dict):
            data[target_key] = payload
    return data if data else None


def get_supabase_scanner_status_payload():
    # Scanner status is the dashboard truth surface; keep this uncached so
    # Streamlit cannot pin filter counts across auto-refresh cycles.
    if supabase is None:
        return {}
    try:
        result = (
            supabase.table(RUNTIME_STATUS_TABLE)
            .select("payload,timestamp_ist")
            .eq("status_key", "scanner_status")
            .limit(1)
            .execute()
        )
    except Exception:
        return {}

    rows = result.data if isinstance(result.data, list) else []
    if not rows or not isinstance(rows[0], dict):
        return {}

    payload = rows[0].get("payload")
    if not isinstance(payload, dict):
        return {}

    payload = dict(payload)
    if rows[0].get("timestamp_ist") and not payload.get("timestamp_ist"):
        payload["timestamp_ist"] = rows[0].get("timestamp_ist")
    return payload


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
    if is_market_open_now():
        return "MARKET OPEN"
    mode = current_bot_mode()
    return "WEEKEND MODE" if mode == "WEEKEND_MODE" else "RESEARCH MODE"


def normalize_runtime_mode(mode):
    text = str(mode or "").strip().upper()
    if text in {"", "UNKNOWN", "NONE", "NULL"}:
        text = ""
    if text in {"INTELLIGENCE_MODE", "CONTINUOUS_WORKERS", "HEALTH_ONLY"}:
        text = "RESEARCH_MODE" if not is_market_open_now() else "MARKET_MODE"
    return text or ("MARKET_MODE" if is_market_open_now() else "RESEARCH_MODE")


def scanner_fresh_seconds_for_mode(mode):
    mode = normalize_runtime_mode(mode)
    return SCANNER_FRESH_SECONDS_BY_MODE.get(mode, RUNTIME_FRESH_SECONDS)


def runtime_mode_from_payloads(*payloads):
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        nested_runtime_mode = payload.get("runtime_mode")
        mode = payload.get("mode") or (
            nested_runtime_mode.get("current_mode")
            if isinstance(nested_runtime_mode, dict)
            else nested_runtime_mode
        )
        if mode:
            return normalize_runtime_mode(mode)
    return normalize_runtime_mode(None)


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


def get_learning_evolution_truth_data():
    memory = safe_read_json(EVOLUTION_MEMORY_PATH, {})
    weight_log = safe_read_json(STRATEGY_WEIGHT_CHANGE_LOG_PATH, {})
    rl_status = safe_read_json(REINFORCEMENT_LEARNING_STATUS_PATH, {})
    meta_status = safe_read_json(META_LEARNING_STATUS_PATH, {})
    top_setup = memory.get("top_performing_setup_type") if isinstance(memory.get("top_performing_setup_type"), dict) else {}
    weak_setup = memory.get("weakest_setup_type") if isinstance(memory.get("weakest_setup_type"), dict) else {}
    best_symbols = memory.get("best_symbols") if isinstance(memory.get("best_symbols"), list) else []
    weak_symbols = memory.get("weakest_symbols") if isinstance(memory.get("weakest_symbols"), list) else []

    def item_name(item, default="INSUFFICIENT_OUTCOMES"):
        return str((item or {}).get("name") or default)

    def symbol_list(items):
        names = [str(item.get("name")) for item in items[:3] if isinstance(item, dict) and item.get("name")]
        return ", ".join(names) if names else "INSUFFICIENT_OUTCOMES"

    confidence = first_number(memory.get("learning_confidence"), default=0.0)
    closed_count = int(first_number(memory.get("closed_outcome_count"), default=0))
    return {
        "top_setup_type": item_name(top_setup),
        "weakest_setup_type": item_name(weak_setup),
        "best_symbols": symbol_list(best_symbols),
        "weakest_symbols": symbol_list(weak_symbols),
        "learning_confidence": confidence,
        "learning_confidence_display": f"{confidence * 100:.1f}%",
        "evolution_changes_today": int(first_number(weight_log.get("changes_today"), default=0)),
        "closed_outcome_count": closed_count,
        "status": "OUTCOME_BACKED" if closed_count > 0 else "WAITING_FOR_OUTCOMES",
        "reinforcement_runtime_status": rl_status.get("status") or "MISSING",
        "reinforcement_runtime_source": rl_status.get("source") or REINFORCEMENT_LEARNING_STATUS_PATH,
        "reinforcement_last_run": rl_status.get("last_run") if isinstance(rl_status.get("last_run"), dict) else {},
        "reinforcement_status_path": REINFORCEMENT_LEARNING_STATUS_PATH,
        "meta_learning_runtime_status": meta_status.get("status") or "MISSING",
        "meta_learning_runtime_source": meta_status.get("source") or META_LEARNING_STATUS_PATH,
        "meta_learning_last_run": meta_status.get("last_run") if isinstance(meta_status.get("last_run"), dict) else {},
        "meta_learning_status_path": META_LEARNING_STATUS_PATH,
    }


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


def read_outcome_tracker_result_rows():
    rows = []
    df = read_csv_safe(["data/journals/trade_outcomes.csv"])
    if not df.empty:
        rows.extend(df.to_dict("records"))
    rows.extend(read_jsonl_rows("data/journals/trade_outcomes.jsonl"))
    return rows


def get_trade_results_dataset():
    """
    Trading Performance is display-only and must be sourced from
    journal.outcome_tracker outputs, not stale dashboard fallbacks.
    """
    return build_trade_results_stats_from_rows(
        read_outcome_tracker_result_rows(),
        "OUTCOME_TRACKER_OUTPUT",
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
    local_news_status = safe_read_json("/".join(["data", "runtime", "news_pulse_status.json"]), {})
    local_news_time = parse_dt(local_news_status.get("latest_news_timestamp_ist") or local_news_status.get("timestamp_ist"))
    if local_news_time and (latest_time is None or local_news_time > latest_time):
        latest_time = local_news_time

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
    elif info["count"] > 0 or local_news_status:
        info["status"] = "ACTIVE"

    return info


def get_master_brain_status(github_time=None, scan_time=None, outcome_time=None):
    """
    Shows whether Master Brain / continuous evolution cycle is active.
    Uses local files produced by TITAN.
    """
    active_df = get_canonical_active_trades_df()

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
    local_stats = get_trade_results_dataset()

    # Status logic
    if latest_activity_time:
        age_seconds = (datetime.now(IST) - latest_activity_time).total_seconds()
        runtime_mode = runtime_mode_from_payloads(
            safe_read_json("/".join(["data", "runtime", "titan_runtime_status.json"]), {}),
            safe_read_json("/".join(["data", "runtime", "daemon_health.json"]), {}),
            safe_read_json("/".join(["data", "runtime", "titan_heartbeat.json"]), {}),
        )

        if age_seconds <= 900:
            master_status = "ACTIVE"
        elif not is_market_open_now() and age_seconds <= scanner_fresh_seconds_for_mode(runtime_mode):
            master_status = market_mode_label()
        elif age_seconds <= 3600:
            master_status = "DELAYED"
        else:
            master_status = "STANDBY" if not is_market_open_now() else "WAITING"
    else:
        master_status = "STANDBY" if not is_market_open_now() else "WAITING"

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


def truthy_scan_value(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    text = str(value or "").strip().upper()
    return text in {"1", "TRUE", "YES", "Y", "PASS", "PASSED", "SUCCESS", "VALID", "OK"}


def latest_scan_symbols_rows():
    if supabase is None:
        return []

    rows = []
    for col in ["created_at", "updated_at", "timestamp", "scan_time", "time", "datetime"]:
        try:
            result = (
                supabase.table("scan_symbols")
                .select("*")
                .order(col, desc=True)
                .limit(1000)
                .execute()
            )
            rows = [row for row in (result.data or []) if isinstance(row, dict)]
            if rows:
                break
        except Exception:
            continue

    if not rows:
        return []

    latest = rows[0]
    for group_key in ["scan_id", "scan_uuid", "run_id", "batch_id", "cycle_id"]:
        group_value = latest.get(group_key)
        if group_value not in [None, ""]:
            grouped = [row for row in rows if row.get(group_key) == group_value]
            if grouped:
                return grouped

    latest_time = row_time(latest)
    if not latest_time:
        return [latest]

    return [
        row for row in rows
        if row_time(row) and abs((latest_time - row_time(row)).total_seconds()) <= RUNTIME_FRESH_SECONDS
    ]


def count_scan_symbol_passes(rows, keys):
    count = 0
    for row in rows:
        value = first_present(row, keys)
        if truthy_scan_value(value):
            count += 1
    return count


def get_latest_scan_symbols_breakdown():
    rows = latest_scan_symbols_rows()
    if not rows:
        return None

    latest_time = latest_dt(*[row_time(row) for row in rows])
    if not dt_is_fresh(latest_time):
        return None

    checked = len(rows)
    trend = count_scan_symbol_passes(rows, ["trend_passed", "trend_ok", "trend_valid", "passed_trend"])
    momentum = count_scan_symbol_passes(rows, ["momentum_passed", "momentum_ok", "momentum_valid", "passed_momentum"])
    structure = count_scan_symbol_passes(rows, ["structure_passed", "structure_ok", "structure_valid", "passed_structure"])
    entry = count_scan_symbol_passes(rows, ["entry_passed", "entry_ok", "entry_valid", "breakout_ready", "passed_entry"])
    final = count_scan_symbol_passes(rows, ["final_passed", "final_ok", "quality_passed", "passed_final", "is_signal"])

    return {
        "stocks_checked": checked,
        "trend_passed": trend,
        "momentum_passed": momentum,
        "structure_passed": structure,
        "entry_passed": entry,
        "raw_breakout_ready_count": entry,
        "qualified_breakout_ready_count": entry,
        "breakout_ready_count": entry,
        "entry_stage_available": True,
        "final_passed": final,
        "alerts_this_scan": count_scan_symbol_passes(rows, ["alert_sent", "alerts_sent", "telegram_sent"]),
        "source": "SUPABASE_SCAN_SYMBOLS",
        "timestamp": latest_time,
        "is_fresh": True,
        "has_data": checked > 0,
        "scanner_cycle_id": None,
        "scan_finished_at_ist": None,
        "scan_duration_seconds": None,
        "scan_only": False,
        "partial_stale_tolerated": False,
        "stale_symbol_ratio": None,
        "stale_policy": None,
        "pipeline_health": {},
        "fallback_reason": None,
        "final_count_source": "supabase_scan_symbols",
        "dashboard_status_message": "Full runtime pipeline active" if final > 0 else "No setups found",
        "repeated_data_signature": False,
        "repeated_data_warning": None,
    }


SCAN_BREAKDOWN_GATE_KEYS = ["trend_passed", "momentum_passed", "structure_passed", "breakout_ready_count", "entry_passed", "final_passed"]


def scanner_payload_has_gate_breakdown(data):
    return isinstance(data, dict) and any(data.get(key) not in [None, ""] for key in SCAN_BREAKDOWN_GATE_KEYS)


def optional_int_number(*values):
    for value in values:
        if value is None or value == "":
            continue
        try:
            return int(float(value))
        except Exception:
            continue
    return None


def final_validated_setups_count(scanner_payload=None):
    scanner_final = {}
    if isinstance(scanner_payload, dict) and isinstance(scanner_payload.get("final_validated_setups"), dict):
        scanner_final = scanner_payload.get("final_validated_setups") or {}
    count = optional_int_number(scanner_final.get("validated_setup_count"))
    if count is not None:
        return count, "scanner_status.final_validated_setups"

    payload = safe_read_json(FINAL_VALIDATED_SETUPS_PATH, {})
    if not isinstance(payload, dict):
        return None, "final_validated_setups_unavailable"
    setups = payload.get("setups")
    if isinstance(setups, list):
        return len(setups), "data/runtime/final_validated_setups.json"
    count = optional_int_number(payload.get("validated_setup_count"))
    if count is not None:
        return count, "data/runtime/final_validated_setups.json"
    return None, "final_validated_setups_unavailable"


def scanner_breakout_counts(payload):
    payload = payload if isinstance(payload, dict) else {}
    qualified = optional_int_number(
        payload.get("qualified_breakout_ready_count"),
        payload.get("breakout_ready_count"),
        payload.get("breakout_ready"),
    )
    qualified = int(qualified or 0)
    raw = optional_int_number(
        payload.get("raw_breakout_ready_count"),
        payload.get("raw_breakout_ready"),
    )
    raw_missing = raw is None
    if raw_missing:
        # Legacy scanner_status rows did not publish raw breakout. Do not let
        # the dashboard show raw=0 with qualified>0; qualified implies raw.
        raw = qualified
    raw = int(raw or 0)
    return {
        "raw_breakout_ready_count": raw,
        "qualified_breakout_ready_count": qualified,
        "breakout_ready_count": qualified,
        "breakout_integrity_valid": qualified <= raw,
        "raw_breakout_missing_from_payload": raw_missing,
    }


def get_latest_scan_breakdown(scanner_runtime_data, master_runtime_data, scan_health):
    zero = {
        "stocks_checked": 0,
        "trend_passed": 0,
        "strict_trend_passed": 0,
        "adaptive_trend_passed": 0,
        "momentum_passed": 0,
        "structure_passed": 0,
        "entry_passed": 0,
        "raw_breakout_ready_count": 0,
        "qualified_breakout_ready_count": 0,
        "breakout_ready_count": 0,
        "entry_stage_available": False,
        "final_passed": None,
        "alerts_this_scan": 0,
        "source": "FALLBACK_AWAITING_VPS_SCANNER",
        "timestamp": None,
        "is_fresh": False,
        "has_data": False,
        "limited_runtime": False,
        "scanner_cycle_id": None,
        "scan_finished_at_ist": None,
        "scan_duration_seconds": None,
        "scan_only": False,
        "partial_stale_tolerated": False,
        "stale_symbol_ratio": None,
        "stale_policy": None,
        "pipeline_health": {},
        "fallback_reason": None,
        "final_count_source": "unavailable",
        "dashboard_status_message": "Final count unavailable from current runtime output",
        "repeated_data_signature": False,
        "repeated_data_warning": None,
        "data_signature": None,
        "scanner_truth_status": "WAITING",
        "scanner_truth_statuses": [],
        "age_seconds": None,
        "repeat_count": 0,
        "ohlc_stale": False,
    }

    preferred_payload, preferred_source = get_preferred_scanner_status_payload()
    if isinstance(preferred_payload, dict) and preferred_payload:
        flags = scanner_truth_flags(preferred_payload)
        final_count, final_count_source = final_validated_setups_count(preferred_payload)
        master_payload = master_runtime_data if isinstance(master_runtime_data, dict) else {}
        alerts = first_number(
            preferred_payload.get("alerts_sent"),
            preferred_payload.get("alerts_this_scan"),
            master_payload.get("alerts_sent"),
            master_payload.get("alerts_this_scan"),
            default=0,
        )
        breakout_counts = scanner_breakout_counts(preferred_payload)
        return {
            "stocks_checked": int(first_number(preferred_payload.get("stocks_checked"), default=0)),
            "trend_passed": int(first_number(preferred_payload.get("trend_passed"), preferred_payload.get("trend_passed_count"), default=0)),
            "strict_trend_passed": int(first_number(preferred_payload.get("strict_trend_passed"), preferred_payload.get("trend_passed"), default=0)),
            "adaptive_trend_passed": int(first_number(preferred_payload.get("adaptive_trend_passed"), default=0)),
            "momentum_passed": int(first_number(preferred_payload.get("momentum_passed"), preferred_payload.get("momentum_passed_count"), default=0)),
            "structure_passed": int(first_number(preferred_payload.get("structure_passed"), preferred_payload.get("structure_passed_count"), default=0)),
            "entry_passed": int(first_number(preferred_payload.get("entry_passed"), preferred_payload.get("entry_passed_count"), default=0)),
            "raw_breakout_ready_count": breakout_counts["raw_breakout_ready_count"],
            "qualified_breakout_ready_count": breakout_counts["qualified_breakout_ready_count"],
            "breakout_ready_count": breakout_counts["breakout_ready_count"],
            "breakout_integrity_valid": breakout_counts["breakout_integrity_valid"],
            "raw_breakout_missing_from_payload": breakout_counts["raw_breakout_missing_from_payload"],
            "entry_stage_available": bool(preferred_payload.get("entry_stage_available")),
            "final_passed": final_count,
            "alerts_this_scan": int(alerts),
            "source": preferred_source,
            "timestamp": runtime_payload_dt(preferred_payload),
            "is_fresh": not flags["stale"],
            "has_data": int(first_number(preferred_payload.get("stocks_checked"), default=0)) > 0,
            "limited_runtime": not scanner_payload_has_gate_breakdown(preferred_payload),
            "scanner_cycle_id": preferred_payload.get("scanner_cycle_id"),
            "scan_finished_at_ist": preferred_payload.get("scan_finished_at_ist") or preferred_payload.get("scanner_timestamp") or preferred_payload.get("timestamp_ist"),
            "scan_duration_seconds": preferred_payload.get("scan_duration_seconds"),
            "scan_only": bool(preferred_payload.get("scan_only")),
            "partial_stale_tolerated": bool(preferred_payload.get("partial_stale_tolerated")),
            "stale_symbol_ratio": preferred_payload.get("stale_symbol_ratio"),
            "stale_policy": preferred_payload.get("stale_policy"),
            "pipeline_health": preferred_payload.get("pipeline_health") if isinstance(preferred_payload.get("pipeline_health"), dict) else {},
            "fallback_reason": preferred_payload.get("fallback_reason"),
            "final_count_source": final_count_source,
            "dashboard_status_message": preferred_payload.get("dashboard_status_message"),
            "repeated_data_signature": flags["repeated_signature_warning"],
            "repeated_data_warning": "INPUT_UNCHANGED_WARNING" if flags["repeated_signature_warning"] else preferred_payload.get("repeated_data_warning"),
            "data_signature": preferred_payload.get("data_signature"),
            "scanner_truth_status": flags["display_status"],
            "scanner_truth_statuses": flags["display_statuses"],
            "age_seconds": flags["age_seconds"],
            "repeat_count": flags["repeat_count"],
            "ohlc_stale": flags["ohlc_stale"],
            "counter_confidence": preferred_payload.get("counter_confidence"),
        }

    scanner_truth = safe_read_json(SCANNER_FILTER_TRUTH_STATUS_PATH, {})
    if isinstance(scanner_truth, dict) and scanner_truth.get("dashboard_scan_sync_status") == "SCAN_PIPELINE_UNAVAILABLE":
        unavailable = dict(zero)
        unavailable.update(
            {
                "source": "SCANNER_STATUS_JSON_UNAVAILABLE",
                "dashboard_status_message": "SCAN_PIPELINE_UNAVAILABLE",
                "counter_confidence": scanner_truth.get("counter_confidence") or "UNKNOWN",
                "recommended_dashboard_display_mode": "SCAN_PIPELINE_UNAVAILABLE",
                "dashboard_scan_sync_status": scanner_truth.get("dashboard_scan_sync_status"),
                "scanner_publication_health": scanner_truth.get("scanner_publication_health"),
            }
        )
        return unavailable

    return zero


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


def scanner_cycle_age_text(dt):
    if not dt:
        return "No scanner cycle timestamp"

    seconds = int((datetime.now(IST) - dt).total_seconds())
    if seconds < 0:
        seconds = 0

    if seconds < 60:
        unit = "second" if seconds == 1 else "seconds"
        return f"{seconds} {unit} ago"

    minutes = seconds // 60
    unit = "minute" if minutes == 1 else "minutes"
    return f"{minutes} {unit} ago"


def scan_duration_text(value):
    if value in [None, ""]:
        return "Not reported"
    try:
        seconds = float(value)
    except Exception:
        return "Not reported"
    if seconds < 0:
        seconds = 0
    if seconds == int(seconds):
        return f"{int(seconds)} seconds"
    return f"{seconds:.1f} seconds"


def scanner_cycle_suffix(value):
    text = str(value or "").strip()
    if not text:
        return ""
    return text[-8:]


def format_runtime_timestamp(value):
    dt = parse_dt(value)
    if dt:
        return dt.strftime("%d %b %Y %I:%M:%S %p IST")
    return str(value or "No heartbeat yet")


def get_runtime_payload(runtime_key, local_path=None, authoritative_local=False):
    local_payload = None
    if local_path:
        data = safe_read_json(local_path, {})
        if isinstance(data, dict):
            local_payload = data
    if isinstance(local_payload, dict):
        return local_payload, "LOCAL_RUNTIME_JSON_AUTHORITATIVE"
    return {}, "UNAVAILABLE"


def runtime_payload_dt(payload):
    if not isinstance(payload, dict):
        return None
    return parse_dt(
        payload.get("timestamp_ist")
        or payload.get("scanner_timestamp")
        or payload.get("scan_finished_at_ist")
        or payload.get("generated_at")
        or payload.get("last_runtime_update")
        or payload.get("updated_at")
        or payload.get("created_at")
        or payload.get("timestamp")
    )


def get_preferred_scanner_status_payload():
    local_payload = safe_read_json(SCANNER_STATUS_PATH, {})
    if isinstance(local_payload, dict) and local_payload:
        return local_payload, "SCANNER_STATUS_JSON"

    return {}, "UNAVAILABLE"


def scanner_age_seconds(timestamp):
    if not timestamp:
        return None
    return max((datetime.now(IST) - timestamp).total_seconds(), 0)


def scanner_off_hours(runtime_mode=None):
    mode = normalize_runtime_mode(runtime_mode)
    return (not is_market_open_now()) or mode in {"RESEARCH_MODE", "WEEKEND_MODE"}


def scanner_ohlc_stale(payload):
    if not isinstance(payload, dict):
        return False
    authoritative = safe_read_json(OHLC_HEALTH_STATUS_PATH, {})
    authoritative_status = str(authoritative.get("status") or "").upper() if isinstance(authoritative, dict) else ""
    if authoritative_status == "PASS":
        return False
    if authoritative_status == "FAIL":
        return True
    pipeline_health = payload.get("pipeline_health") if isinstance(payload.get("pipeline_health"), dict) else {}
    data_health = payload.get("scanner_data_health") if isinstance(payload.get("scanner_data_health"), dict) else {}
    return bool(
        payload.get("ohlc_fallback_required")
        or payload.get("stale_data_warning")
        or pipeline_health.get("ohlc_stale")
        or data_health.get("ohlc_stale")
        or str(data_health.get("stale_policy") or payload.get("stale_policy") or "").upper().startswith("STALE")
    )


def scanner_signature_repeat_count(payload):
    if not isinstance(payload, dict):
        return 0
    for key in [
        "repeated_data_signature_count",
        "same_data_signature_cycles",
        "data_signature_repeat_count",
        "signature_repeat_count",
    ]:
        value = optional_int_number(payload.get(key))
        if value is not None:
            return max(int(value), 0)

    signature = str(payload.get("data_signature") or "").strip()
    cycle = str(payload.get("scanner_cycle_id") or "").strip()
    if not signature:
        return 0

    try:
        state = st.session_state.setdefault("scanner_signature_repeat_tracker", {})
        if state.get("signature") == signature:
            if cycle and state.get("cycle") != cycle:
                state["count"] = int(state.get("count") or 1) + 1
                state["cycle"] = cycle
        else:
            state.clear()
            state.update({"signature": signature, "cycle": cycle, "count": 1})
        return int(state.get("count") or 1)
    except Exception:
        return 1 if payload.get("repeated_data_signature") else 0


def scanner_truth_flags(payload, timestamp=None, runtime_mode=None):
    timestamp = timestamp or runtime_payload_dt(payload)
    age_seconds = scanner_age_seconds(timestamp)
    off_hours = scanner_off_hours(runtime_mode)
    repeat_count = scanner_signature_repeat_count(payload)
    stale = bool(age_seconds is None or age_seconds > SCANNER_STALE_SECONDS)
    ohlc_stale = scanner_ohlc_stale(payload)
    if off_hours:
        stale = False
        ohlc_stale = False
    repeated = repeat_count >= SCANNER_SIGNATURE_REPEAT_WARNING_CYCLES
    statuses = []
    if stale:
        statuses.append("SCAN_STALE")
    if repeated:
        statuses.append("INPUT_UNCHANGED_WARNING")
    if ohlc_stale:
        statuses.append("SCAN_ONLY_STALE_OHLC")
    if stale:
        display_status = "SCAN_STALE"
    elif repeated:
        display_status = "INPUT_UNCHANGED_WARNING"
    elif ohlc_stale:
        display_status = "SCAN_ONLY_STALE_OHLC"
    else:
        display_status = "ACTIVE"
    return {
        "age_seconds": age_seconds,
        "off_hours": off_hours,
        "stale": stale,
        "ohlc_stale": ohlc_stale,
        "repeat_count": repeat_count,
        "repeated_signature_warning": repeated,
        "display_status": display_status,
        "display_statuses": statuses,
    }


def runtime_payload_is_fresh(payload, fresh_seconds=RUNTIME_FRESH_SECONDS):
    dt = runtime_payload_dt(payload)
    if not dt:
        return False
    return (datetime.now(IST) - dt).total_seconds() <= fresh_seconds


def dt_is_fresh(dt, fresh_seconds=RUNTIME_FRESH_SECONDS):
    if not dt:
        return False
    return (datetime.now(IST) - dt).total_seconds() <= fresh_seconds


def runtime_payload_status(payload):
    if not isinstance(payload, dict):
        return ""
    return str(
        payload.get("status")
        or payload.get("readiness_status")
        or payload.get("health_check_status")
        or ""
    ).upper()


def runtime_payload_active(payload):
    status = runtime_payload_status(payload)
    if not status:
        return False
    inactive_markers = ("STOPPED", "FAILED", "ERROR", "INACTIVE", "STALE")
    return not any(marker in status for marker in inactive_markers)


def runtime_status_with_freshness(payload, active_status="ACTIVE", waiting_status="WAITING"):
    if not isinstance(payload, dict) or not payload:
        return waiting_status
    if not runtime_payload_is_fresh(payload):
        return "STALE"
    if runtime_payload_active(payload):
        return active_status
    return runtime_payload_status(payload) or waiting_status


def get_dashboard_runtime_status():
    authoritative_truth = safe_read_json("/".join(["data", "runtime", "authoritative_runtime_truth.json"]), {})
    journal_truth = safe_read_json(JOURNAL_TRUTH_UNIFICATION_PATH, {})
    dashboard_truth = build_dashboard_truth_consolidation(
        authoritative_truth,
        journal_truth,
        write=True,
    )
    component_truth = authoritative_truth.get("components") if isinstance(authoritative_truth, dict) else {}
    component_truth = component_truth if isinstance(component_truth, dict) else {}

    def component_status(name):
        record = component_truth.get(name)
        if isinstance(record, dict):
            return str(record.get("status") or "UNKNOWN").upper()
        return ""

    daemon_health, _ = get_runtime_payload("daemon_health", "/".join(["data", "runtime", "daemon_health.json"]))
    heartbeat, _ = get_runtime_payload("heartbeat", "/".join(["data", "runtime", "titan_heartbeat.json"]))
    runtime_status, _ = get_runtime_payload("runtime_status", TITAN_RUNTIME_STATUS_PATH)
    resilience_status, _ = get_runtime_payload("runtime_resilience_status", RUNTIME_RESILIENCE_STATUS_PATH)
    governance_status, _ = get_runtime_payload("pyramid_governance_status", PYRAMID_GOVERNANCE_STATUS_PATH)
    weekend_research_status, _ = get_runtime_payload("weekend_research_mode_status", WEEKEND_RESEARCH_MODE_STATUS_PATH)
    scanner_status, _ = get_runtime_payload("scanner_status", SCANNER_STATUS_PATH, authoritative_local=True)
    scanner_truth = safe_read_json(SCANNER_FILTER_TRUTH_STATUS_PATH, {})
    master_brain_status, _ = get_runtime_payload("master_brain_status", "/".join(["data", "runtime", "master_brain_status.json"]))
    paper_engine_status, _ = get_runtime_payload("paper_engine_status", PAPER_ENGINE_STATUS_PATH)
    live_price_monitor_status, _ = get_runtime_payload("live_price_monitor_status", LIVE_PRICE_MONITOR_STATUS_PATH)

    normalized_runtime_mode = runtime_mode_from_payloads(runtime_status, daemon_health, heartbeat)
    runtime_fresh_seconds = scanner_fresh_seconds_for_mode(normalized_runtime_mode)
    daemon_fresh = runtime_payload_is_fresh(daemon_health, runtime_fresh_seconds)
    heartbeat_fresh = runtime_payload_is_fresh(heartbeat, runtime_fresh_seconds)
    runtime_fresh = runtime_payload_is_fresh(runtime_status, runtime_fresh_seconds)
    classified_daemon_status = component_status("daemon")
    daemon_alive = classified_daemon_status == "LIVE" or (
        daemon_fresh
        and runtime_payload_status(daemon_health) == "RUNNING"
        and not classified_daemon_status
    ) or (
        heartbeat_fresh
        and runtime_payload_status(heartbeat) == "ALIVE"
        and not classified_daemon_status
    )

    if classified_daemon_status:
        daemon_status = classified_daemon_status
    elif daemon_alive:
        daemon_status = runtime_payload_status(daemon_health) or runtime_payload_status(heartbeat)
    elif daemon_health or heartbeat or runtime_status:
        daemon_status = "STALE" if not (daemon_fresh or heartbeat_fresh or runtime_fresh) else "WAITING"
    else:
        daemon_status = "WAITING"

    runtime_mode = str(
        runtime_status.get("mode")
        or daemon_health.get("mode")
        or heartbeat.get("mode")
        or "UNKNOWN"
    )
    market_workers_allowed_idle = normalized_runtime_mode in {"RESEARCH_MODE", "WEEKEND_MODE"}
    scanner_fresh = runtime_payload_is_fresh(
        scanner_status,
        scanner_fresh_seconds_for_mode(normalized_runtime_mode),
    )
    heartbeat_dt = runtime_payload_dt(heartbeat)
    heartbeat_timestamp = heartbeat.get("timestamp_ist") or daemon_health.get("timestamp_ist") or runtime_status.get("timestamp_ist")
    heartbeat_age = f"Latest beat: {age_text_from_dt(heartbeat_dt)}" if heartbeat_dt else "No heartbeat yet"
    ticks_completed = daemon_health.get("ticks_completed")
    ticks_text = f"{int(ticks_completed):,}" if isinstance(ticks_completed, (int, float)) else str(ticks_completed or "0")

    open_paper_positions = int(first_number(paper_engine_status.get("open_positions_count"), default=0)) if isinstance(paper_engine_status, dict) else 0
    governance = governance_status.get("governance") if isinstance(governance_status.get("governance"), dict) else {}
    block_reasons = safe_list(governance.get("block_reasons") or governance_status.get("block_reasons"))
    dashboard_ready_status = (
        resilience_status.get("dashboard_ready_status")
        if isinstance(resilience_status.get("dashboard_ready_status"), dict)
        else {}
    )
    governance_decision = str(
        governance.get("decision")
        or governance.get("governance_decision")
        or governance_status.get("governance_decision")
        or weekend_research_status.get("governance_decision")
        or dashboard_ready_status.get("governance_decision")
        or ""
    ).upper()
    worker_degraded_count = int(first_number(
        resilience_status.get("worker_health_summary", {}).get("degraded_count")
        if isinstance(resilience_status.get("worker_health_summary"), dict)
        else None,
        governance_status.get("runtime_resilience_status", {}).get("worker_degraded_count")
        if isinstance(governance_status.get("runtime_resilience_status"), dict)
        else None,
        default=0,
    ))
    standby_runtime_healthy = (
        market_workers_allowed_idle
        and not block_reasons
        and worker_degraded_count == 0
        and daemon_alive
        and open_paper_positions == 0
    )
    defensive_runtime_healthy = governance_decision == "ALLOW" and worker_degraded_count == 0
    paper_engine_required = is_market_open_now() or open_paper_positions > 0
    scanner_live = component_status("scanner") == "LIVE"
    master_brain_live = component_status("master_brain") == "LIVE"
    paper_engine_live = component_status("paper_engine") == "LIVE"
    live_price_monitor_live = (
        runtime_payload_is_fresh(live_price_monitor_status) and runtime_payload_active(live_price_monitor_status)
    )
    runtime_checks = {
        "daemon_not_alive": daemon_alive,
        "runtime_status_stale": runtime_fresh,
        "scanner_stale": scanner_live if component_status("scanner") else scanner_fresh and runtime_payload_active(scanner_status),
        "master_brain_stale": master_brain_live if component_status("master_brain") else runtime_payload_is_fresh(master_brain_status) and runtime_payload_active(master_brain_status),
        "paper_engine_stale": paper_engine_live if component_status("paper_engine") else runtime_payload_is_fresh(paper_engine_status) and runtime_payload_active(paper_engine_status),
        "live_price_monitor_stale": (
            live_price_monitor_live
            if market_workers_allowed_idle
            else live_price_monitor_live
        ),
    }
    attention_reasons = [reason for reason, ok in runtime_checks.items() if not ok]
    if standby_runtime_healthy or defensive_runtime_healthy:
        attention_reasons = []
    if standby_runtime_healthy and not attention_reasons:
        autonomous_status = "STANDBY" if normalized_runtime_mode == "WEEKEND_MODE" else "HEALTHY"
        autonomous_sub = "Weekend / research standby"
    else:
        autonomous_status = "NEEDS ATTENTION" if attention_reasons else "HEALTHY"
        autonomous_sub = ", ".join(attention_reasons) if attention_reasons else "Runtime attention checks clear"

    truth_components = dashboard_truth.get("components_rendered_from_authoritative_truth", {})
    daemon_display = (truth_components.get("daemon") or {}).get("status") or daemon_status
    return {
        "daemon_status": daemon_display,
        "runtime_mode": normalized_runtime_mode,
        "normalized_runtime_mode": normalized_runtime_mode,
        "canonical_runtime_timestamp": runtime_status.get("canonical_runtime_timestamp") or heartbeat_timestamp,
        "canonical_scan_cycle": runtime_status.get("canonical_scan_cycle") or scanner_truth.get("authoritative_scan_cycle_id") or scanner_truth.get("scan_cycle_id"),
        "dashboard_runtime_sync_health": runtime_status.get("dashboard_runtime_sync_health") or scanner_truth.get("dashboard_scan_sync_status") or "UNKNOWN",
        "market_hours_runtime_sync": runtime_status.get("market_hours_runtime_sync") or scanner_truth.get("market_hours_runtime_sync"),
        "scanner_publication_health": runtime_status.get("scanner_publication_health") or scanner_truth.get("scanner_publication_health"),
        "dashboard_trade_sync_health": runtime_status.get("dashboard_trade_sync_health"),
        "lifecycle_sync_status": runtime_status.get("lifecycle_sync_status"),
        "performance_sync_status": runtime_status.get("performance_sync_status"),
        "heartbeat_age": heartbeat_age,
        "heartbeat_timestamp": format_runtime_timestamp(heartbeat_timestamp),
        "ticks_completed": ticks_text,
        "autonomous_runtime_status": dashboard_truth.get("dashboard_overall_status") or autonomous_status,
        "autonomous_runtime_sub": (
            "Authoritative runtime truth"
            if dashboard_truth.get("dashboard_overall_status")
            else autonomous_sub
        ),
        "autonomous_runtime_needs_attention": not bool(dashboard_truth.get("restart_allowed")),
        "autonomous_runtime_attention_reasons": dashboard_truth.get("restart_blockers") or attention_reasons,
        "governance_decision": governance_decision,
        "block_reasons": block_reasons,
        "worker_degraded_count": worker_degraded_count,
        "authoritative_runtime_truth": authoritative_truth,
        "dashboard_truth_consolidation": dashboard_truth,
        "journal_truth_unification": journal_truth if isinstance(journal_truth, dict) else {},
        "canonical_active_trade_count": int(first_number(
            journal_truth.get("canonical_open_trade_count") if isinstance(journal_truth, dict) else None,
            default=get_live_trades_count(),
        )),
        "legacy_quarantined_file_count": int(first_number(
            journal_truth.get("legacy_quarantined_file_count") if isinstance(journal_truth, dict) else None,
            default=0,
        )),
        "legacy_open_rows_by_file": (
            journal_truth.get("legacy_open_rows_by_file")
            if isinstance(journal_truth, dict) and isinstance(journal_truth.get("legacy_open_rows_by_file"), dict)
            else {}
        ),
        "component_truth_statuses": {
            name: record.get("status")
            for name, record in component_truth.items()
            if isinstance(record, dict)
        },
    }


def get_scanner_runtime_status():
    data, source = get_preferred_scanner_status_payload()
    scanner_truth = safe_read_json(SCANNER_FILTER_TRUTH_STATUS_PATH, {})
    daemon_health, _ = get_runtime_payload("daemon_health", "/".join(["data", "runtime", "daemon_health.json"]))
    heartbeat, _ = get_runtime_payload("heartbeat", "/".join(["data", "runtime", "titan_heartbeat.json"]))
    runtime_status, _ = get_runtime_payload("runtime_status", "/".join(["data", "runtime", "titan_runtime_status.json"]))
    runtime_mode = runtime_mode_from_payloads(runtime_status, daemon_health, heartbeat)
    payload = data if isinstance(data, dict) else {}
    timestamp = runtime_payload_dt(data)
    truth_flags = scanner_truth_flags(payload, timestamp, runtime_mode)
    breakout_counts = scanner_breakout_counts(payload)
    scanner_fresh = not truth_flags["stale"]
    status = runtime_status_with_freshness(
        data,
        active_status="ACTIVE",
        waiting_status="WAITING",
    )
    if runtime_mode in {"RESEARCH_MODE", "WEEKEND_MODE"}:
        status = "MARKET CLOSED / STANDBY"
    elif truth_flags["display_status"] != "ACTIVE":
        status = truth_flags["display_status"]
    elif scanner_truth.get("dashboard_scan_sync_status") == "SCAN_PIPELINE_UNAVAILABLE":
        status = "SCAN_PIPELINE_UNAVAILABLE"
    elif scanner_fresh and runtime_payload_active(data):
        status = "ACTIVE"
    return {
        "payload": payload,
        "source": source,
        "timestamp": timestamp,
        "timestamp_ist": payload.get("timestamp_ist") or payload.get("timestamp"),
        "age": age_text_from_dt(timestamp),
        "status": status,
        "is_fresh": scanner_fresh,
        "runtime_mode": runtime_mode,
        "data_signature": payload.get("data_signature"),
        "scanner_truth_status": truth_flags["display_status"],
        "age_seconds": truth_flags["age_seconds"],
        "repeat_count": truth_flags["repeat_count"],
        "ohlc_stale": truth_flags["ohlc_stale"],
        "canonical_scan_cycle": scanner_truth.get("authoritative_scan_cycle_id") or scanner_truth.get("scan_cycle_id"),
        "canonical_runtime_timestamp": scanner_truth.get("authoritative_scan_timestamp"),
        "dashboard_scan_sync_status": scanner_truth.get("dashboard_scan_sync_status"),
        "scanner_publication_health": scanner_truth.get("scanner_publication_health"),
        "stocks_checked": int(first_number(payload.get("stocks_checked"), default=0)),
        "trend_passed": int(first_number(payload.get("trend_passed"), default=0)),
        "momentum_passed": int(first_number(payload.get("momentum_passed"), default=0)),
        "structure_passed": int(first_number(payload.get("structure_passed"), default=0)),
        "entry_passed": int(first_number(payload.get("entry_passed"), default=0)),
        "raw_breakout_ready_count": breakout_counts["raw_breakout_ready_count"],
        "qualified_breakout_ready_count": breakout_counts["qualified_breakout_ready_count"],
        "breakout_ready_count": breakout_counts["breakout_ready_count"],
        "breakout_integrity_valid": breakout_counts["breakout_integrity_valid"],
        "final_passed": optional_int_number(payload.get("final_passed")),
        "alerts_sent": int(first_number(payload.get("alerts_sent"), default=0)),
    }


def get_live_price_monitor_runtime_status():
    data, source = get_runtime_payload("live_price_monitor_status", LIVE_PRICE_MONITOR_STATUS_PATH)
    timestamp = runtime_payload_dt(data)
    status = runtime_status_with_freshness(data, active_status="ACTIVE")
    if not market_open:
        status = "MARKET CLOSED / STANDBY"
    return {
        "payload": data if isinstance(data, dict) else {},
        "source": source,
        "timestamp": timestamp,
        "age": age_text_from_dt(timestamp),
        "status": status,
    }


def get_paper_engine_runtime_status():
    runtime_data = build_runtime_status_from_supabase()
    data = (
        runtime_data.get("paper_engine_status")
        if isinstance(runtime_data, dict) and isinstance(runtime_data.get("paper_engine_status"), dict)
        else None
    )
    if not isinstance(data, dict):
        data = safe_read_json(PAPER_ENGINE_STATUS_PATH, {})
    if not isinstance(data, dict):
        data = {}

    summary = data.get("paper_performance_summary")
    account_summary = data.get("paper_account_summary")
    if not isinstance(account_summary, dict):
        account_summary = {}

    equity = first_number(account_summary.get("equity"), account_summary.get("current_balance"), default=0.0)
    realized_pnl = first_number(account_summary.get("realized_pnl"), default=0.0)

    runtime_mode = runtime_mode_from_payloads(
        safe_read_json("/".join(["data", "runtime", "titan_runtime_status.json"]), {}),
        safe_read_json("/".join(["data", "runtime", "daemon_health.json"]), {}),
        safe_read_json("/".join(["data", "runtime", "titan_heartbeat.json"]), {}),
    )
    if not isinstance(summary, dict):
        return {
            "status": "STANDBY" if runtime_mode in {"RESEARCH_MODE", "WEEKEND_MODE"} else "WAITING",
            "message": "Paper engine idle outside market window" if runtime_mode in {"RESEARCH_MODE", "WEEKEND_MODE"} else "No paper engine runtime summary yet",
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
        "status": (
            "STANDBY"
            if runtime_mode in {"RESEARCH_MODE", "WEEKEND_MODE"} and int(first_number(summary.get("open_positions_count"), default=0)) == 0
            else "ACTIVE"
        ),
        "message": (
            "Idle outside market window; no open paper trades require monitoring"
            if runtime_mode in {"RESEARCH_MODE", "WEEKEND_MODE"} and int(first_number(summary.get("open_positions_count"), default=0)) == 0
            else "Source: data/runtime/paper_engine_status.json"
        ),
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
        return "MARKET CLOSED / STANDBY"

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
    supabase_healthy = supabase_status == "CONNECTED"

    if master_activity_time:
        age_seconds = (datetime.now(IST) - master_activity_time).total_seconds()
        if age_seconds <= 6 * 3600:
            return "ONLINE" if market_open else market_mode_label()
        if age_seconds <= 24 * 3600 and supabase_healthy:
            return "DELAYED" if market_open else market_mode_label()

    if not market_open and supabase_healthy:
        return market_mode_label()
    if supabase_healthy:
        return "DELAYED"
    return "OFFLINE"


def derive_scan_status(scan_time=None, master_activity_time=None, market_open=None):
    market_open = is_market_open_now() if market_open is None else market_open
    if not market_open:
        return "MARKET CLOSED / STANDBY"
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
        return market_mode_label()
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
        return "MARKET CLOSED / STANDBY"
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
    closed_status = market_mode_label() if closed_status == "RESEARCH MODE" else closed_status
    if text in {"OFFLINE", "ERROR", "FAILED", "INACTIVE", "UNKNOWN", "STALE", "DELAYED"}:
        return closed_status
    return text


def status_html(status):
    status = str(status).upper()

    if status in ["ONLINE", "CONNECTED", "SUCCESS", "RUNNING", "ACTIVE", "LEARNING", "OBSERVING", "OK"]:
        css = "pill-green"
    elif status in ["DELAYED", "UNKNOWN", "WAITING", "STANDBY", "IDLE_RESEARCH_MODE", "NOT CONFIGURED", "BUILDING", "STALE", "RESEARCH MODE", "WEEKEND MODE", "WEEKEND_MODE", "RESEARCH_MODE", "MARKET CLOSED", "MARKET CLOSED / RESEARCH MODE", "MARKET CLOSED / STANDBY", "REVIEW"]:
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


def _dashboard_debug(message):
    try:
        print(f"[Dashboard LiveCount] {message}")
    except Exception:
        pass


def _has_value(value):
    return str(value or "").strip() != ""


def _is_current_day_trade_row(row):
    opened = parse_dt(row.get("opened_at") or row.get("created_at") or row.get("timestamp"))
    return bool(opened and opened.astimezone(IST).date() == datetime.now(IST).date())


def _is_learning_or_paper_trade_row(row):
    if str(row.get("is_paper_trade") or "").strip().lower() in {"1", "true", "yes", "y"}:
        return True
    if str(row.get("paper_trade_id") or "").strip():
        return True
    if str(row.get("alert_sent") or row.get("telegram_alerted") or "").strip().upper() == "NO":
        return True
    return str(row.get("status") or "").strip().upper() in {"WATCHLIST", "LEARNING", "PAPER_OPEN"}


def _is_live_trade_row(row):
    if not isinstance(row, dict):
        return False

    if _is_test_symbol(row.get("symbol")):
        return False

    status = str(
        row.get("status")
        or row.get("trade_status")
        or row.get("state")
        or ""
    ).strip().upper()
    outcome = normalize_outcome(row.get("outcome"))
    result = normalize_outcome(row.get("result"))

    if status in {"CLOSED", "EOD_UNRESOLVED", "STALE_OPEN", "CLOSED_MANUAL_RECONCILIATION_REQUIRED"}:
        return False
    if _has_value(row.get("closed_at")):
        return False
    if outcome in {"WIN", "LOSS"} or str(row.get("outcome") or "").strip().upper() in {"TP", "SL"}:
        return False
    if result in {"WIN", "LOSS"}:
        return False
    if _is_learning_or_paper_trade_row(row):
        return False
    if not _is_current_day_trade_row(row):
        return False

    return status in {"OPEN", "ACTIVE", "LIVE"}


def _local_active_trades_count(paths):
    for path in paths:
        try:
            if not os.path.exists(path):
                continue

            df = pd.read_csv(path, on_bad_lines="skip")

            if df.empty:
                _dashboard_debug(f"source=LOCAL path={path} live_count=0 fallback_reason=empty_file")
                return 0, path, None

            rows = df.to_dict("records")
            live_count = sum(1 for row in rows if _is_live_trade_row(row))
            _dashboard_debug(f"source=LOCAL path={path} live_count={live_count} fallback_reason=not_used")
            return int(live_count), path, None

        except Exception as exc:
            _dashboard_debug(f"source=LOCAL path={path} live_count=0 fallback_reason=read_error:{exc}")
            continue

    return None, None, "local_active_trades_unavailable"


def get_runtime_paper_open_positions_count():
    data, _ = get_runtime_payload("paper_engine_status", PAPER_ENGINE_STATUS_PATH)
    if not isinstance(data, dict) or not runtime_payload_is_fresh(data):
        return 0

    summary = data.get("paper_performance_summary")
    if not isinstance(summary, dict):
        summary = {}

    return int(first_number(
        summary.get("open_positions_count"),
        data.get("open_positions_count"),
        data.get("open_trades_count"),
        default=0,
    ))


def get_canonical_active_trade_rows():
    try:
        from data.active_trade_store import load_canonical_open_trades

        return [row for row in load_canonical_open_trades() if isinstance(row, dict)]
    except Exception as exc:
        _dashboard_debug(f"source=CANONICAL_ACTIVE_TRADE_STORE rows=0 fallback_reason=read_error:{exc}")
        return []


def get_canonical_active_trades_df():
    rows = get_canonical_active_trade_rows()
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def get_live_trades_count():
    """
    FINAL CANONICAL LIVE TRADE FIX:
    Live trades should come from data.active_trade_store, not trade_results
    or lifecycle diagnostic artifacts.

    NOTE:
    trade_results is for CLOSED TP/SL performance only.
    """
    try:
        from data.active_trade_store import load_canonical_open_trades

        return len([row for row in load_canonical_open_trades() if isinstance(row, dict)])
    except Exception as exc:
        _dashboard_debug(f"source=ACTIVE_TRADE_STORE live_count=0 fallback_reason=read_error:{exc}")
        return 0


def get_trade_lifecycle_reconciliation():
    reconciliation = safe_read_json(TRADE_LIFECYCLE_RECONCILIATION_PATH, {})
    if isinstance(reconciliation, dict) and reconciliation:
        return reconciliation
    lifecycle = safe_read_json(TRADE_LIFECYCLE_HEALTH_PATH, {})
    if not isinstance(lifecycle, dict):
        lifecycle = {}
    return {
        "active_live_trades": {"count": int(first_number(lifecycle.get("active_live_trades_count"), default=0))},
        "learning_open_trades": {"count": int(first_number(lifecycle.get("learning_open_trades_count"), default=0))},
        "stale_open_trades": {"count": int(first_number(lifecycle.get("stale_open_trades_count"), default=0))},
        "eod_unresolved_trades": {"count": int(first_number(lifecycle.get("unresolved_eod_trades_count"), default=0))},
        "closed_tp_sl_trades": {"count": int(first_number(lifecycle.get("closed_tp_sl_trades_count"), default=0))},
    }


def _reconciliation_count(reconciliation, key):
    value = reconciliation.get(key) if isinstance(reconciliation, dict) else None
    if isinstance(value, dict):
        return int(first_number(value.get("count"), default=0))
    return int(first_number(value, default=0))



def get_supabase_live_trades_count(fallback_reason="local_active_trades_unavailable"):
    """
    Deprecated diagnostic reader for Supabase trades visibility checks.

    Dashboard live/open trade metrics must use data.active_trade_store via
    get_live_trades_count(); this helper is intentionally not part of the
    active display path.
    """
    if supabase is None:
        _dashboard_debug(f"source=SUPABASE_TRADES live_count=0 fallback_reason={fallback_reason}; supabase_unavailable")
        return 0

    try:
        result = (
            supabase.table("trades")
            .select("symbol,status,trade_status,state,outcome,result,closed_at,opened_at,created_at,is_paper_trade,paper_trade_id,alert_sent")
            .limit(5000)
            .execute()
        )

        rows = result.data or []

        if not rows:
            _dashboard_debug(f"source=SUPABASE_TRADES live_count=0 fallback_reason={fallback_reason}; no_rows")
            return 0

        live_count = sum(1 for row in rows if _is_live_trade_row(row))
        _dashboard_debug(f"source=SUPABASE_TRADES live_count={live_count} fallback_reason={fallback_reason}")
        return int(live_count)

    except Exception as exc:
        _dashboard_debug(f"source=SUPABASE_TRADES live_count=0 fallback_reason={fallback_reason}; error:{exc}")
        return 0



def get_trade_results_stats():
    """
    Deprecated diagnostic reader for Supabase trade_results visibility checks.

    Dashboard performance metrics must use get_trade_results_dataset(), which
    reads journal.outcome_tracker output only.
    """
    stats = {
        "wins": 0,
        "losses": 0,
        "closed_total": 0,
        "accuracy": 0,
        "open_total": 0,
        "source": "DIAGNOSTIC_SUPABASE_TRADE_RESULTS_DEPRECATED",
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
# DASHBOARD V3 FOUNDATION
# =========================================================

V3_RUNTIME_DIR = Path("data") / "runtime"
V3_DATA_DIR = Path("data")
V3_ECHO_DIR = V3_RUNTIME_DIR / "echo"
V3_HFT_DIR = V3_DATA_DIR / "hft_mode"
V3_ALPHA_MATH_DIR = V3_RUNTIME_DIR / "alpha_math"
V3_ALPHA_INPUT_DIR = V3_RUNTIME_DIR / "alpha_inputs"
V3_ACTIVITY_DIR = V3_RUNTIME_DIR / "activity"
V3_LAB_DIR = V3_RUNTIME_DIR / "lab"
V3_TRUTH_SOURCES = {
    "authoritative_runtime_truth": V3_RUNTIME_DIR / "authoritative_runtime_truth.json",
    "dashboard_truth_consolidation": V3_RUNTIME_DIR / "dashboard_truth_consolidation.json",
    "dashboard_runtime_integrity": V3_RUNTIME_DIR / "dashboard_runtime_integrity.json",
    "dashboard_truth_registry": V3_RUNTIME_DIR / "dashboard_truth_registry.json",
    "canonical_metric_ownership": V3_RUNTIME_DIR / "canonical_metric_ownership.json",
    "metric_dependency_graph": V3_RUNTIME_DIR / "metric_dependency_graph.json",
    "component_freshness_summary": V3_RUNTIME_DIR / "component_freshness_summary.json",
    "execution_mode": V3_RUNTIME_DIR / "execution_mode.json",
    "dashboard_live_metrics": V3_RUNTIME_DIR / "dashboard_live_metrics.json",
    "titan_body_map_live": V3_RUNTIME_DIR / "titan_body_map_live.json",
    "git_cleanliness": V3_RUNTIME_DIR / "git_cleanliness.json",
    "activity_directory": V3_ACTIVITY_DIR,
    "lab_activity": V3_LAB_DIR / "lab_activity.json",
    "strategy_experiments": V3_LAB_DIR / "strategy_experiments.json",
    "runtime_error_summary": V3_RUNTIME_DIR / "runtime_error_summary.json",
    "runtime_warning_resolution": V3_RUNTIME_DIR / "runtime_warning_resolution_status.json",
    "runtime_reconciliation": V3_RUNTIME_DIR / "runtime_reconciliation_status.json",
    "titan_runtime_status": V3_RUNTIME_DIR / "titan_runtime_status.json",
    "canonical_runtime_mode": V3_RUNTIME_DIR / "canonical_runtime_mode.json",
    "daemon_health": V3_RUNTIME_DIR / "daemon_health.json",
    "titan_heartbeat": V3_RUNTIME_DIR / "titan_heartbeat.json",
    "worker_health": V3_RUNTIME_DIR / "worker_health.json",
    "scanner_scheduler": V3_RUNTIME_DIR / "scanner_scheduler_status.json",
    "scanner_status": V3_RUNTIME_DIR / "scanner_status.json",
    "journal_truth_unification": V3_RUNTIME_DIR / "journal_truth_unification.json",
    "daemon_errors": V3_RUNTIME_DIR / "daemon_errors.jsonl",
    "master_brain_status": V3_RUNTIME_DIR / "master_brain_status.json",
    "master_brain_runtime_health": V3_RUNTIME_DIR / "master_brain_runtime_health.json",
    "scanner_filter_truth": V3_RUNTIME_DIR / "scanner_filter_truth_status.json",
    "setup_engine_status": V3_RUNTIME_DIR / "setup_engine_status.json",
    "setup_engine_runtime_health": V3_RUNTIME_DIR / "setup_engine_runtime_health.json",
    "signal_path_diagnostics": V3_RUNTIME_DIR / "signal_path_diagnostics.json",
    "trend_diagnostics": V3_RUNTIME_DIR / "trend_diagnostics.json",
    "market_regime_update": V3_RUNTIME_DIR / "market_regime_update_status.json",
    "market_regime_accuracy": V3_RUNTIME_DIR / "market_regime_accuracy.json",
    "news_intelligence": V3_RUNTIME_DIR / "news_intelligence_status.json",
    "news_pulse": V3_RUNTIME_DIR / "news_pulse_status.json",
    "advisory_intelligence": V3_RUNTIME_DIR / "advisory_intelligence_status.json",
    "historical_replay": V3_RUNTIME_DIR / "historical_replay_status.json",
    "backtesting_status": V3_RUNTIME_DIR / "backtesting_status.json",
    "paper_account": V3_DATA_DIR / "paper_trading" / "paper_account.json",
    "paper_trade_registry": V3_RUNTIME_DIR / "paper_trade_registry.json",
    "active_trades": V3_DATA_DIR / "journals" / "active_trades.csv",
    "trade_outcomes": V3_DATA_DIR / "journals" / "trade_outcomes.csv",
    "trade_lifecycle_health": V3_RUNTIME_DIR / "trade_lifecycle_health.json",
    "trade_lifecycle_reconciliation": V3_RUNTIME_DIR / "trade_lifecycle_reconciliation.json",
    "broker_health_check": V3_RUNTIME_DIR / "broker_health_check_status.json",
    "risk_watchdog": V3_RUNTIME_DIR / "risk_watchdog_status.json",
    "live_price_monitor": V3_RUNTIME_DIR / "live_price_monitor_status.json",
    "pnl_refresh": V3_RUNTIME_DIR / "pnl_refresh_status.json",
    "evolution_engine": V3_RUNTIME_DIR / "evolution_engine_status.json",
    "evolution_memory": V3_RUNTIME_DIR / "evolution_memory.json",
    "reinforcement_learning": V3_RUNTIME_DIR / "reinforcement_learning_status.json",
    "meta_learning": V3_RUNTIME_DIR / "meta_learning_status.json",
    "outcome_tracker": V3_RUNTIME_DIR / "outcome_tracker_status.json",
    "outcome_tracker_diagnostics": V3_RUNTIME_DIR / "outcome_tracker_diagnostics.json",
    "memory_health": V3_RUNTIME_DIR / "titan_memory_health.json",
    "memory_lineage": V3_RUNTIME_DIR / "memory_lineage_graph.json",
    "memory_contribution": V3_RUNTIME_DIR / "memory_contribution_status.json",
    "strategy_rejection_analysis": V3_RUNTIME_DIR / "strategy_rejection_analysis.json",
    "setup_performance_history": V3_RUNTIME_DIR / "setup_performance_history.json",
    "echo_mission": V3_ECHO_DIR / "codex_runner_request.json",
    "echo_mission_queue": V3_ECHO_DIR / "approval_queue.json",
    "echo_recent_report": V3_ECHO_DIR / "auto_report.json",
    "echo_files_reviewed": V3_ECHO_DIR / "decision_trace_audit.json",
    "echo_recommendations": V3_ECHO_DIR / "recommendation_log.json",
    "echo_diagnostics": V3_ECHO_DIR / "codex_runner_status.json",
    "restart_readiness": V3_RUNTIME_DIR / "restart_readiness.json",
    "restart_readiness_gate": V3_RUNTIME_DIR / "restart_readiness_gate.json",
    "runtime_permissions": V3_RUNTIME_DIR / "runtime_recovery_policy.json",
    "runtime_visibility_audit": V3_RUNTIME_DIR / "runtime_visibility_audit.json",
    "truth_gate": V3_RUNTIME_DIR / "truth_gate_status.json",
    "runtime_dependency_graph": V3_RUNTIME_DIR / "runtime_dependency_graph.json",
    "runtime_topology": V3_RUNTIME_DIR / "titan_runtime_topology.json",
    "echo_architecture_map": V3_ECHO_DIR / "architecture_map.json",
    "echo_permission_matrix": V3_ECHO_DIR / "permission_matrix.json",
    "echo_ownership_map": V3_ECHO_DIR / "ownership_map.json",
    "hft_health": V3_HFT_DIR / "hft_health.json",
    "hft_runtime_state": V3_HFT_DIR / "hft_runtime_state.json",
    "hft_safety_proof": V3_HFT_DIR / "hft_safety_proof.json",
    "hft_stats": V3_HFT_DIR / "hft_stats.json",
    "hft_outcomes": V3_HFT_DIR / "hft_outcomes.json",
    "hft_active_trades": V3_HFT_DIR / "hft_active_trades.json",
    "hft_closed_summary": V3_HFT_DIR / "hft_closed_summary.json",
    "hft_rejected_count": V3_HFT_DIR / "hft_rejected_count.json",
    "hft_daily_pnl": V3_HFT_DIR / "hft_daily_pnl.json",
    "alpha_health": V3_ALPHA_MATH_DIR / "alpha_health.json",
    "alpha_input_manifest": V3_ALPHA_INPUT_DIR / "upstox_alpha_input_manifest.json",
    "alpha_input_health": V3_ALPHA_INPUT_DIR / "upstox_alpha_input_health.json",
    "alpha_upstox_readiness": V3_ALPHA_MATH_DIR / "upstox_input_readiness_report.json",
    "alpha_wiring_report": V3_ALPHA_MATH_DIR / "upstox_alpha_wiring_report.json",
    "alpha_pending_outcomes": V3_ALPHA_MATH_DIR / "alpha_pending_outcomes.json",
    "alpha_shadow_outcome_report": V3_ALPHA_MATH_DIR / "alpha_shadow_outcome_report.json",
    "alpha_memory_summary": V3_ALPHA_MATH_DIR / "alpha_memory_summary.json",
    "alpha_lane_candidates": V3_ALPHA_MATH_DIR / "lane_candidates.json",
    "alpha_latest_scores": V3_ALPHA_MATH_DIR / "latest_scores.json",
    "alpha_rerun_readiness": V3_ALPHA_MATH_DIR / "alpha_rerun_readiness.json",
    "alpha_shadow_lab_final_status": V3_ALPHA_MATH_DIR / "alpha_shadow_lab_final_status.json",
    "alpha_shadow_journal": V3_ALPHA_MATH_DIR / "alpha_shadow_journal.csv",
}

V3_D03_LAYER_SOURCES = {
    "Runtime Layer": ["authoritative_runtime_truth", "titan_runtime_status", "daemon_health", "titan_heartbeat", "worker_health", "scanner_scheduler", "runtime_dependency_graph", "runtime_topology"],
    "Scanner Layer": ["scanner_status", "scanner_filter_truth", "market_regime_update", "market_regime_accuracy"],
    "Setup Layer": ["setup_engine_status", "setup_engine_runtime_health", "signal_path_diagnostics", "trend_diagnostics"],
    "Master Brain Layer": ["master_brain_status", "master_brain_runtime_health"],
    "Trading Layer": ["journal_truth_unification", "paper_account", "paper_trade_registry", "active_trades", "trade_outcomes", "trade_lifecycle_health", "trade_lifecycle_reconciliation", "risk_watchdog"],
    "Learning Layer": ["evolution_engine", "evolution_memory", "reinforcement_learning", "meta_learning", "outcome_tracker", "outcome_tracker_diagnostics", "memory_health", "memory_lineage", "memory_contribution", "strategy_rejection_analysis"],
    "ECHO Layer": ["echo_mission", "echo_mission_queue", "echo_recent_report", "echo_files_reviewed", "echo_recommendations", "echo_diagnostics"],
    "Diagnostics Layer": ["dashboard_runtime_integrity", "dashboard_truth_registry", "canonical_metric_ownership", "metric_dependency_graph", "component_freshness_summary", "runtime_error_summary", "runtime_warning_resolution", "runtime_reconciliation", "truth_gate"],
    "Dashboard Layer": ["dashboard_truth_consolidation", "runtime_visibility_audit", "echo_architecture_map", "echo_permission_matrix", "echo_ownership_map"],
    "HFT Layer": ["hft_health", "hft_runtime_state", "hft_safety_proof", "hft_stats", "hft_outcomes", "hft_active_trades", "hft_closed_summary", "hft_rejected_count", "hft_daily_pnl"],
    "Alpha/TOIF Layer": ["alpha_health", "alpha_input_manifest", "alpha_input_health", "alpha_upstox_readiness", "alpha_wiring_report", "alpha_pending_outcomes", "alpha_shadow_outcome_report", "alpha_memory_summary", "alpha_lane_candidates", "alpha_latest_scores", "alpha_rerun_readiness", "alpha_shadow_lab_final_status", "alpha_shadow_journal"],
}

V3_DASHBOARD_SOURCE_CONSUMERS = {
    "authoritative_runtime_truth": ["Command Center", "Runtime Department", "Diagnostics Department", "Incident Room", "Control Room", "System Mindmap", "Architecture Department"],
    "dashboard_truth_consolidation": ["Command Center", "Trading Department", "Truth Explorer"],
    "dashboard_runtime_integrity": ["Command Center", "Diagnostics Department", "Incident Room", "Control Room"],
    "dashboard_truth_registry": ["Control Room", "Truth Explorer", "Flow Visualizer"],
    "canonical_metric_ownership": ["Diagnostics Layer", "Truth Explorer", "Architecture Department"],
    "metric_dependency_graph": ["System Mindmap", "Flow Visualizer", "Truth Explorer", "Architecture Department"],
    "component_freshness_summary": ["Freshness Explorer"],
    "runtime_error_summary": ["Diagnostics Department", "Flow Visualizer"],
    "runtime_warning_resolution": ["Diagnostics Department", "Incident Room"],
    "runtime_reconciliation": ["Diagnostics Layer", "Architecture Department"],
    "titan_runtime_status": ["Global Header", "Runtime Department", "Control Room"],
    "canonical_runtime_mode": ["Global Header", "Runtime Department", "Control Room"],
    "daemon_health": ["Runtime Department", "System Mindmap"],
    "titan_heartbeat": ["Runtime Department", "System Mindmap"],
    "worker_health": ["Runtime Department", "System Mindmap"],
    "scanner_scheduler": ["Runtime Department", "System Mindmap"],
    "scanner_status": ["Intelligence Department", "Runtime Department", "System Mindmap"],
    "journal_truth_unification": ["Command Center", "Trading Department", "Flow Visualizer"],
    "daemon_errors": ["Diagnostics Department", "Incident Room"],
    "master_brain_status": ["Intelligence Department", "System Mindmap"],
    "master_brain_runtime_health": ["Intelligence Department", "System Mindmap"],
    "scanner_filter_truth": ["Intelligence Department", "System Mindmap"],
    "setup_engine_status": ["Intelligence Department", "System Mindmap"],
    "setup_engine_runtime_health": ["Intelligence Department", "System Mindmap"],
    "signal_path_diagnostics": ["Intelligence Department", "System Mindmap"],
    "trend_diagnostics": ["Intelligence Department", "System Mindmap"],
    "market_regime_update": ["Intelligence Department", "System Mindmap"],
    "market_regime_accuracy": ["Intelligence Department", "System Mindmap"],
    "news_intelligence": ["Intelligence Department"],
    "news_pulse": ["Intelligence Department"],
    "advisory_intelligence": ["Intelligence Department"],
    "historical_replay": ["Intelligence Department"],
    "backtesting_status": ["Intelligence Department"],
    "paper_account": ["Trading Department"],
    "paper_trade_registry": ["Trading Department"],
    "active_trades": ["Trading Department"],
    "trade_outcomes": ["Trading Department"],
    "trade_lifecycle_health": ["Trading Department", "System Mindmap"],
    "trade_lifecycle_reconciliation": ["Trading Department"],
    "broker_health_check": ["Trading Department"],
    "risk_watchdog": ["Trading Department"],
    "live_price_monitor": ["Trading Department"],
    "pnl_refresh": ["Trading Department"],
    "evolution_engine": ["Learning Department", "System Mindmap"],
    "evolution_memory": ["Learning Department"],
    "reinforcement_learning": ["Learning Department"],
    "meta_learning": ["Learning Department"],
    "outcome_tracker": ["Learning Department"],
    "outcome_tracker_diagnostics": ["Learning Department"],
    "memory_health": ["Learning Department", "System Mindmap"],
    "memory_lineage": ["Learning Department"],
    "memory_contribution": ["Learning Department"],
    "strategy_rejection_analysis": ["Learning Department"],
    "setup_performance_history": ["Learning Department"],
    "echo_mission": ["ECHO Department"],
    "echo_mission_queue": ["ECHO Department"],
    "echo_recent_report": ["ECHO Department"],
    "echo_files_reviewed": ["ECHO Department"],
    "echo_recommendations": ["ECHO Department"],
    "echo_diagnostics": ["ECHO Department"],
    "restart_readiness": ["Control Room"],
    "restart_readiness_gate": ["Control Room"],
    "runtime_permissions": ["Control Room", "Architecture Department"],
    "runtime_visibility_audit": ["Control Room", "Architecture Department"],
    "truth_gate": ["Control Room"],
    "runtime_dependency_graph": ["System Mindmap", "Flow Visualizer", "Architecture Department"],
    "runtime_topology": ["System Mindmap", "Architecture Department"],
    "echo_architecture_map": ["Architecture Department"],
    "echo_permission_matrix": ["Architecture Department"],
    "echo_ownership_map": ["Architecture Department"],
    "hft_health": ["System Mindmap", "Architecture Department", "HFT Department"],
    "hft_runtime_state": ["System Mindmap", "Architecture Department", "HFT Department"],
    "hft_safety_proof": ["System Mindmap", "Architecture Department", "HFT Department"],
    "hft_stats": ["HFT Department"],
    "hft_outcomes": ["HFT Department"],
    "hft_active_trades": ["HFT Department"],
    "hft_closed_summary": ["HFT Department"],
    "hft_rejected_count": ["HFT Department"],
    "hft_daily_pnl": ["HFT Department"],
    "alpha_health": ["System Mindmap", "Architecture Department", "Alpha Lab"],
    "alpha_input_manifest": ["System Mindmap", "Architecture Department", "Alpha Lab"],
    "alpha_input_health": ["System Mindmap", "Architecture Department", "Alpha Lab"],
    "alpha_upstox_readiness": ["System Mindmap", "Architecture Department", "Alpha Lab"],
    "alpha_wiring_report": ["System Mindmap", "Architecture Department", "Alpha Lab"],
    "alpha_pending_outcomes": ["Alpha Lab"],
    "alpha_shadow_outcome_report": ["Alpha Lab"],
    "alpha_memory_summary": ["Alpha Lab"],
    "alpha_lane_candidates": ["Alpha Lab"],
    "alpha_latest_scores": ["Alpha Lab"],
    "alpha_rerun_readiness": ["Alpha Lab"],
    "alpha_shadow_lab_final_status": ["Alpha Lab"],
    "alpha_shadow_journal": ["Alpha Lab"],
}

V3_WIDGET_INVENTORY = {
    "Global Header": [
        "Date",
        "Time / Seconds",
        "Market Clock",
        "VPS Clock",
        "Active Mode",
        "Last Verified",
        "Auto Refresh Status",
    ],
    "Command Center": [
        "System State",
        "Trust Score",
        "Runtime Overview",
        "Trading Overview",
        "Active Incidents",
        "Evidence Freshness Summary",
        "Quick Status Grid",
        "Mini System Map",
    ],
    "Runtime Department": [
        "Daemon",
        "Lock Ownership",
        "Runtime Mode",
        "Heartbeat",
        "Workers",
        "Scheduler",
        "Runtime Truth",
    ],
    "Diagnostics Department": [
        "Runtime Errors",
        "Error Trends",
        "Truth Conflicts",
        "Stale Evidence",
        "Freshness Problems",
        "Validation Results",
    ],
    "Incident Room": [
        "Active Incidents",
        "Historical Incidents",
        "Open Warnings",
        "Resolved Warnings",
        "Conflict Tracker",
    ],
    "Intelligence Department": [
        "Master Brain",
        "Scanner",
        "Setup Engine",
        "Contradiction Engine",
        "Market Regime",
        "News Intelligence",
        "Research Intelligence",
    ],
    "Trading Department": [
        "Account Status",
        "Open Trades",
        "Closed Trades",
        "PnL",
        "Exposure",
        "Risk Summary",
        "Execution Ownership",
        "Active Trade Monitor",
    ],
    "Learning Department": [
        "Evolution Engine",
        "Learning Queue",
        "Outcome Analysis",
        "Memory Status",
        "Pattern Discovery",
        "Knowledge Growth",
    ],
    "ECHO Department": [
        "Current Mission",
        "Mission Queue",
        "Recent Reports",
        "Files Reviewed",
        "Recommendations",
        "Diagnostics Activity",
    ],
    "Control Room": [
        "Runtime Mode",
        "Execution Ownership",
        "Safety Gates",
        "Activation Readiness",
        "Runtime Permissions",
        "Department Summary",
        "Truth Health",
    ],
    "System Mindmap": [
        "Runtime Layer",
        "Scanner Layer",
        "Setup Layer",
        "Master Brain Layer",
        "Trading Layer",
        "Learning Layer",
        "ECHO Layer",
        "Diagnostics Layer",
        "Dashboard Layer",
        "HFT Layer",
        "Alpha/TOIF Layer",
    ],
    "Flow Visualizer": [
        "Dashboard Evidence Flows",
        "Dependency Graph Flows",
        "Runtime Truth Flow",
        "Diagnostics Flow",
        "Journal Flow",
    ],
    "Truth Explorer": [
        "Truth Source Navigator",
        "Consumer Navigator",
        "Dependency Detail",
        "Last Read Evidence",
    ],
    "Freshness Explorer": [
        "Fresh Sources",
        "Warning Sources",
        "Stale Sources",
        "Unknown Sources",
        "Consumer Impact",
    ],
    "Architecture Department": [
        "Runtime Boundaries",
        "Ownership Boundaries",
        "Trust Boundaries",
        "Read-Only Boundaries",
        "Dashboard Boundaries",
        "Classic/HFT Separation",
        "Alpha Isolation",
        "Classic TITAN Domain",
        "HFT TITAN Domain",
        "Alpha Lab Domain",
    ],
    "HFT Department": [
        "HFT Status",
        "Build Status",
        "Runtime Status",
        "Scheduler Status",
        "Ownership Status",
        "Memory Isolation",
        "Journal Isolation",
        "Dashboard Isolation",
        "Master Brain Isolation",
        "Evolution Isolation",
        "Dependency Map",
        "Read Boundaries",
        "Write Boundaries",
    ],
    "Alpha Lab": [
        "Alpha Status",
        "Alpha Health",
        "Shadow Mode Status",
        "Outcome Resolver Status",
        "Pending Outcome Tracker",
        "Memory Readiness",
        "Lane Overview",
        "Elite Lane",
        "Strong Lane",
        "Micro Lane",
        "Prediction Count",
        "Outcome Count",
        "Unresolved Count",
        "Similar Wins",
        "Similar Losses",
        "Outcome Resolution Health",
    ],
}

FLOW_STAGES = [
    "INPUT",
    "INTELLIGENCE",
    "DECISION",
    "RISK",
    "EXECUTION",
    "FEEDBACK",
]

ENGINE_FLOW_STAGE = {
    "command_center": "DECISION",
    "trading": "EXECUTION",
    "runtime": "INPUT",
    "intelligence": "INTELLIGENCE",
    "learning": "FEEDBACK",
    "diagnostics": "RISK",
    "echo": "FEEDBACK",
    "control": "RISK",
    "hft": "EXECUTION",
    "alpha": "INTELLIGENCE",
}

TITAN_STATE = {
    "meta": {
        "last_updated": None,
        "system_mode": "CLASSIC",
    },
    "engines": {
        "command_center": {},
        "trading": {},
        "runtime": {},
        "intelligence": {},
        "learning": {},
        "diagnostics": {},
    },
    "events": [],
    "flow": {
        "stages": FLOW_STAGES,
        "active": "INPUT",
        "status": "UNKNOWN",
        "timestamp": None,
    },
    "evidence_index": {},
}

if "_TITAN_STATE" not in st.session_state:
    st.session_state["_TITAN_STATE"] = TITAN_STATE
else:
    TITAN_STATE = st.session_state["_TITAN_STATE"]


def titan_now():
    return datetime.utcnow()


def titan_now_iso():
    return titan_now().isoformat()


def compute_age_seconds(last_timestamp):
    parsed = parse_dt(last_timestamp) if isinstance(last_timestamp, str) else last_timestamp
    if parsed is None:
        return None
    if getattr(parsed, "tzinfo", None) is not None:
        return max(0, (datetime.now(parsed.tzinfo) - parsed).total_seconds())
    return max(0, (titan_now() - parsed).total_seconds())


def compute_freshness(last_timestamp):
    age_seconds = compute_age_seconds(last_timestamp)
    if age_seconds is None:
        return "UNKNOWN"
    if age_seconds < 1:
        return "FRESH"
    if age_seconds < 60:
        return "STALE"
    return "UNKNOWN"


def update_flow(active_stage, status="ACTIVE"):
    active_stage = str(active_stage or "INPUT").upper()
    if active_stage not in FLOW_STAGES:
        active_stage = "INPUT"
    TITAN_STATE["flow"] = {
        "stages": FLOW_STAGES,
        "active": active_stage,
        "status": str(status or "ACTIVE").upper(),
        "timestamp": titan_now_iso(),
    }


def emit_event(engine, action, status, payload=None):
    event = {
        "timestamp": titan_now_iso(),
        "engine": engine,
        "action": action,
        "status": status,
        "payload": payload or {},
    }
    TITAN_STATE["events"].append(event)
    TITAN_STATE["events"] = TITAN_STATE["events"][-500:]
    update_flow(ENGINE_FLOW_STAGE.get(engine, "INPUT"), status=status)
    return event


def update_engine(engine, key, value):
    if engine not in TITAN_STATE["engines"]:
        TITAN_STATE["engines"][engine] = {}
    now_value = titan_now()
    freshness = compute_freshness(now_value)
    age_seconds = compute_age_seconds(now_value)
    TITAN_STATE["engines"][engine][key] = value
    TITAN_STATE["engines"][engine]["last_updated"] = now_value.isoformat()
    TITAN_STATE["engines"][engine]["freshness"] = freshness
    TITAN_STATE["engines"][engine]["age_seconds"] = age_seconds
    TITAN_STATE["engines"][engine]["confidence"] = _engine_confidence(value)
    TITAN_STATE["meta"]["last_updated"] = now_value.isoformat()
    emit_event(engine, "UPDATE", "SUCCESS", {"key": key})


def update_evidence_index(source_name, record):
    safe_record = dict(record or {})
    timestamp = safe_record.get("timestamp")
    if timestamp is not None:
        safe_record["timestamp"] = timestamp
    TITAN_STATE["evidence_index"][source_name] = safe_record
    emit_event("diagnostics", "EVIDENCE_INDEX", safe_record.get("freshness") or "UNKNOWN", {"source": source_name})


def get_activity_stream():
    return TITAN_STATE["events"][-10:]


def _engine_confidence(value):
    if isinstance(value, dict) and value:
        records = value.values()
        total = len(value)
        known = len([record for record in records if isinstance(record, dict) and record.get("exists")])
        return round(known / total, 3) if total else 0.0
    if value in (None, "", [], {}):
        return 0.0
    return 1.0


def _record_payload_status(record):
    payload = record.get("payload") if isinstance(record, dict) else {}
    if isinstance(payload, dict):
        return (
            payload.get("status")
            or payload.get("overall_status")
            or payload.get("dashboard_overall_status")
            or payload.get("status_reason")
            or record.get("status")
            or "UNKNOWN"
        )
    return record.get("status") if isinstance(record, dict) else "UNKNOWN"


def _engine_for_source(source_name):
    if source_name in {"dashboard_truth_consolidation", "authoritative_runtime_truth"}:
        return "command_center"
    if source_name in {"journal_truth_unification", "paper_account", "active_trades", "trade_outcomes", "risk_watchdog", "trade_lifecycle_health"}:
        return "trading"
    if source_name in {"daemon_health", "titan_runtime_status", "titan_heartbeat", "worker_health", "scanner_scheduler", "canonical_runtime_mode"}:
        return "runtime"
    if source_name in {"scanner_status", "master_brain_status", "setup_engine_status", "signal_path_diagnostics", "market_regime_update", "alpha_health", "alpha_lane_candidates"}:
        return "intelligence"
    if source_name in {"evolution_engine", "reinforcement_learning", "outcome_tracker", "memory_health", "memory_lineage", "memory_contribution"}:
        return "learning"
    return "diagnostics"


def hydrate_titan_state(records):
    TITAN_STATE["meta"]["system_mode"] = v3_active_mode(records)
    TITAN_STATE["evidence_index"] = {}
    engine_records = {}
    for source_name, record in records.items():
        update_evidence_index(source_name, record)
        engine = _engine_for_source(source_name)
        engine_records.setdefault(engine, {})[source_name] = record
    for engine, values in engine_records.items():
        update_engine(engine, "data", values)
        update_engine(engine, "latest_status", v3_compact_value({name: _record_payload_status(record) for name, record in values.items()}))
    return TITAN_STATE


def v3_read_json(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"_read_error": "json_root_not_object"}
    except Exception as exc:
        return {"_read_error": str(exc)}


def v3_read_jsonl_tail(path, limit=25):
    rows = []
    try:
        path = Path(path)
        if not path.exists():
            return rows
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-limit:]:
            try:
                parsed = json.loads(line)
                rows.append(parsed if isinstance(parsed, dict) else {"message": line})
            except Exception:
                rows.append({"message": line})
    except Exception as exc:
        rows.append({"read_error": str(exc)})
    return rows


def v3_payload_timestamp(payload):
    if not isinstance(payload, dict):
        return None
    for key in (
        "generated_at",
        "generated_at_ist",
        "timestamp",
        "timestamp_ist",
        "last_updated",
        "last_updated_ist",
        "updated_at",
        "heartbeat_timestamp",
        "source_timestamp",
    ):
        parsed = parse_dt(payload.get(key))
        if parsed:
            return parsed
    return None


def v3_artifact_record(name, path, *, ttl_seconds=900):
    path = Path(path)
    payload = v3_read_json(path) if path.suffix.lower() == ".json" else {}
    exists = path.exists()
    parsed_ts = v3_payload_timestamp(payload)
    file_ts = None
    if exists:
        try:
            file_ts = datetime.fromtimestamp(path.stat().st_mtime, tz=IST)
        except Exception:
            file_ts = None
    evidence_ts = parsed_ts or file_ts
    age_seconds = None
    freshness = "UNKNOWN"
    if evidence_ts:
        age_seconds = max(0, (datetime.now(IST) - evidence_ts).total_seconds())
        freshness = "FRESH" if age_seconds <= ttl_seconds else "STALE"
    elif not exists:
        freshness = "UNKNOWN"
    status = str(
        payload.get("status")
        or payload.get("overall_status")
        or payload.get("dashboard_overall_status")
        or payload.get("dashboard_runtime_integrity_status")
        or payload.get("dashboard_truth_registry_status")
        or payload.get("canonical_metric_ownership_status")
        or payload.get("metric_dependency_graph_status")
        or "UNKNOWN"
    ).upper()
    if not exists:
        status = "UNKNOWN"
    return {
        "name": name,
        "path": str(path).replace("\\", "/"),
        "exists": exists,
        "payload": payload,
        "timestamp": evidence_ts,
        "age_seconds": age_seconds,
        "freshness": freshness,
        "status": status,
        "read_error": payload.get("_read_error") if isinstance(payload, dict) else None,
    }


def v3_load_evidence():
    records = {name: v3_artifact_record(name, path) for name, path in V3_TRUTH_SOURCES.items()}
    authoritative = records["authoritative_runtime_truth"]["payload"]
    journal = records["journal_truth_unification"]["payload"]
    consolidation = build_dashboard_truth_consolidation(authoritative, journal, write=False)
    records["dashboard_truth_consolidation"]["payload"] = consolidation
    records["dashboard_truth_consolidation"]["status"] = str(consolidation.get("dashboard_overall_status") or "UNKNOWN").upper()
    records["dashboard_truth_consolidation"]["timestamp"] = parse_dt(consolidation.get("generated_at"))
    if records["dashboard_truth_consolidation"]["timestamp"]:
        records["dashboard_truth_consolidation"]["age_seconds"] = max(
            0,
            (datetime.now(IST) - records["dashboard_truth_consolidation"]["timestamp"]).total_seconds(),
        )
        records["dashboard_truth_consolidation"]["freshness"] = "FRESH"
    records["daemon_errors"]["rows"] = v3_read_jsonl_tail(V3_TRUTH_SOURCES["daemon_errors"])
    hydrate_titan_state(records)
    return TITAN_STATE["evidence_index"]


def v3_component(records, name):
    authoritative = records.get("authoritative_runtime_truth", {}).get("payload", {})
    components = authoritative.get("components") if isinstance(authoritative, dict) else {}
    record = components.get(name) if isinstance(components, dict) else None
    if not isinstance(record, dict):
        return {
            "component": name,
            "status": "UNKNOWN",
            "reason": "component_missing_from_authoritative_runtime_truth",
            "source_file": "data/runtime/authoritative_runtime_truth.json",
            "source_timestamp": None,
            "age_seconds": None,
        }
    return record


def v3_status_line(record):
    source = record.get("source_file") or record.get("path") or "UNKNOWN"
    reason = record.get("reason") or record.get("read_error") or "evidence loaded"
    age = record.get("age_seconds")
    age_text = "age UNKNOWN" if age is None else f"age {int(float(age))}s"
    return f"Source: {source} | {age_text} | {reason}"


def v3_latest_verified(records):
    timestamps = [record.get("timestamp") for record in records.values() if record.get("timestamp")]
    if not timestamps:
        return "UNKNOWN"
    return max(timestamps).strftime("%d %b %Y %H:%M:%S IST")


def v3_active_mode(records):
    for name in ("canonical_runtime_mode", "titan_runtime_status"):
        payload = records.get(name, {}).get("payload", {})
        if isinstance(payload, dict):
            mode = payload.get("mode") or payload.get("runtime_mode") or payload.get("active_mode")
            if mode:
                return str(mode).upper()
    return "UNKNOWN"


def v3_market_clock():
    try:
        return "OPEN" if is_trade_window(datetime.now(IST)) else "CLOSED"
    except Exception:
        return "UNKNOWN"


def v3_trust_score(records):
    components = (
        records.get("authoritative_runtime_truth", {})
        .get("payload", {})
        .get("components", {})
    )
    if not isinstance(components, dict) or not components:
        return "UNKNOWN", "No authoritative component evidence"
    known = 0
    good = 0
    problem = 0
    for record in components.values():
        status = str((record or {}).get("status") or "UNKNOWN").upper()
        if status not in {"UNKNOWN", ""}:
            known += 1
        if status in {"LIVE", "ACTIVE", "CLEAN", "PASS"}:
            good += 1
        if status in {"STALE", "STOPPED", "DEGRADED", "FAIL", "CONFLICT"}:
            problem += 1
    return f"{good}/{len(components)}", f"Known: {known} | Problem: {problem} | Source: authoritative_runtime_truth"


def v3_incident_lists(records):
    authoritative = records.get("authoritative_runtime_truth", {}).get("payload", {})
    summary = authoritative.get("summary") if isinstance(authoritative, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    integrity = records.get("dashboard_runtime_integrity", {}).get("payload", {})
    warning_resolution = records.get("runtime_warning_resolution", {}).get("payload", {})
    active = []
    for key in ("restart_blockers", "stopped_components", "stale_components", "degraded_components", "conflict_components"):
        for item in summary.get(key) or []:
            active.append({"type": key, "item": item, "source": "authoritative_runtime_truth"})
    for item in integrity.get("warnings") or []:
        active.append({"type": "dashboard_integrity_warning", "item": item, "source": "dashboard_runtime_integrity"})
    open_warnings = []
    resolved_warnings = []
    if isinstance(warning_resolution, dict):
        for item in warning_resolution.get("open_warnings") or warning_resolution.get("warnings") or []:
            open_warnings.append({"warning": item, "source": "runtime_warning_resolution_status"})
        for item in warning_resolution.get("resolved_warnings") or warning_resolution.get("resolved") or []:
            resolved_warnings.append({"warning": item, "source": "runtime_warning_resolution_status"})
    historical = records.get("daemon_errors", {}).get("rows", [])
    conflicts = [{"component": item, "source": "authoritative_runtime_truth"} for item in summary.get("conflict_components") or []]
    return active, historical, open_warnings, resolved_warnings, conflicts


def v3_card(title, value, sub="", status=None):
    if status is None:
        metric_card(title, value, sub)
    else:
        status_card(title, status, sub)


def v3_first_present(payload, keys, default="UNKNOWN"):
    if not isinstance(payload, dict):
        return default
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def v3_compact_value(value):
    if value in (None, "", [], {}):
        return "UNKNOWN"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value[:5]) or "UNKNOWN"
    if isinstance(value, dict):
        parts = []
        for key, item in list(value.items())[:5]:
            if item not in (None, "", [], {}):
                parts.append(f"{key}={item}")
        return " | ".join(parts) or "UNKNOWN"
    return str(value)


def v3_source_row(records, label, source_name, *, component_name=None, purpose=""):
    record = records.get(source_name, {})
    payload = record.get("payload", {})
    component = v3_component(records, component_name) if component_name else None
    status = (
        component.get("status")
        if isinstance(component, dict) and component.get("status")
        else record.get("status")
        or "UNKNOWN"
    )
    activity = v3_first_present(
        payload,
        ("current_activity", "activity", "message", "reason", "phase", "mode", "runtime_mode", "state"),
    )
    if activity == "UNKNOWN" and isinstance(component, dict):
        activity = component.get("reason") or component.get("source_status") or "UNKNOWN"
    inputs = v3_first_present(
        payload,
        ("current_inputs", "inputs", "input_source", "read_source", "source_files_used", "dependencies"),
    )
    outputs = v3_first_present(
        payload,
        ("current_outputs", "outputs", "write_target", "output_path", "artifacts", "result", "summary"),
    )
    return {
        "Card": label,
        "Purpose": purpose or label,
        "Current State": str(status).upper(),
        "Current Activity": v3_compact_value(activity),
        "Current Inputs": v3_compact_value(inputs),
        "Current Outputs": v3_compact_value(outputs),
        "Source": record.get("path") or "UNKNOWN",
        "Evidence Source": record.get("path") or "UNKNOWN",
        "Freshness": record.get("freshness") or "UNKNOWN",
        "Freshness Rule": "Runtime-critical evidence: 900s; source TTL overrides when published",
        "Unknown Rule": "Missing file, unreadable JSON, absent component, or absent required field displays UNKNOWN",
        "Failure Rule": "Do not infer healthy state; show read error, UNKNOWN, or STALE from evidence",
    }


def v3_render_department_table(rows):
    if not rows:
        rows = [{"Card": "UNKNOWN", "Current State": "UNKNOWN", "Evidence Source": "UNKNOWN", "Freshness": "UNKNOWN"}]
    normalized = []
    for row in rows:
        item = dict(row)
        if "Card" not in item:
            item["Card"] = item.pop("Section", item.pop("Widget", "UNKNOWN"))
        item.setdefault("Purpose", item.get("Card", "UNKNOWN"))
        item.setdefault("Current State", "UNKNOWN")
        item.setdefault("Current Activity", item.get("Value", "UNKNOWN"))
        item.setdefault("Current Inputs", item.get("Evidence Source", "UNKNOWN"))
        item.setdefault("Current Outputs", item.get("Value", "UNKNOWN"))
        item.setdefault("Source", item.get("Evidence Source", "UNKNOWN"))
        item.setdefault("Evidence Source", "UNKNOWN")
        item.setdefault("Freshness", "UNKNOWN")
        item.setdefault("Freshness Rule", "Runtime-critical evidence: 900s; source TTL overrides when published")
        item.setdefault("Unknown Rule", "Missing source, missing field, or unreadable evidence displays UNKNOWN")
        item.setdefault("Failure Rule", "Never fabricate state; stale evidence displays STALE and missing evidence displays UNKNOWN")
        normalized.append(item)
    st.dataframe(normalized, use_container_width=True, hide_index=True)


def v3_read_csv_rows(path):
    try:
        path = Path(path)
        if not path.exists():
            return None
        df = pd.read_csv(path)
        return df.to_dict("records")
    except Exception:
        return None


def v3_trade_status(row):
    if not isinstance(row, dict):
        return ""
    for key in ("status", "trade_status", "state", "position_status", "outcome"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value).upper()
    return ""


def v3_open_trade_rows():
    rows = v3_read_csv_rows(V3_TRUTH_SOURCES["active_trades"])
    if rows is None:
        return None
    open_statuses = {"OPEN", "ACTIVE", "LIVE", "OPEN_PENDING", "PENDING", "IN_TRADE"}
    return [row for row in rows if v3_trade_status(row) in open_statuses]


def v3_closed_trade_rows():
    rows = v3_read_csv_rows(V3_TRUTH_SOURCES["trade_outcomes"])
    if rows is None:
        return None
    closed_statuses = {"TP", "SL", "WIN", "LOSS", "CLOSED", "EXITED"}
    return [row for row in rows if v3_trade_status(row) in closed_statuses or row.get("exit_price") not in (None, "")]


def v3_number_from_row(row, keys):
    for key in keys:
        try:
            value = row.get(key)
            if value not in (None, ""):
                return float(value)
        except Exception:
            continue
    return None


def v3_open_exposure(open_rows):
    if open_rows is None:
        return "UNKNOWN"
    if not open_rows:
        return "0"
    total = 0.0
    saw_value = False
    for row in open_rows:
        qty = v3_number_from_row(row, ("qty", "quantity", "shares", "size"))
        price = v3_number_from_row(row, ("entry_price", "price", "avg_price", "buy_price"))
        if qty is not None and price is not None:
            total += abs(qty * price)
            saw_value = True
    return format_inr(total) if saw_value else "UNKNOWN"


def v3_account_value(records, key_options):
    payload = records.get("paper_account", {}).get("payload", {})
    value = v3_first_present(payload, key_options, default=None)
    if value is None:
        return "UNKNOWN"
    try:
        return format_inr(float(value))
    except Exception:
        return str(value)


def v3_render_intelligence(records):
    rows = [
        v3_source_row(records, "Master Brain", "master_brain_status", component_name="master_brain", purpose="Brain runtime visibility"),
        v3_source_row(records, "Scanner", "scanner_status", component_name="scanner", purpose="Scanner activity and publication evidence"),
        v3_source_row(records, "Setup Engine", "setup_engine_status", component_name="setup_engine", purpose="Setup generation evidence"),
        v3_source_row(records, "Contradiction Engine", "signal_path_diagnostics", purpose="Signal/path contradiction diagnostics"),
        v3_source_row(records, "Market Regime", "market_regime_update", purpose="Market regime state"),
        v3_source_row(records, "News Intelligence", "news_intelligence", component_name="news_intelligence", purpose="News intelligence state"),
        v3_source_row(records, "Research Intelligence", "historical_replay", purpose="Research and replay visibility"),
    ]
    st.markdown("### Intelligence Department")
    v3_render_department_table(rows)
    cols = st.columns(4)
    for index, row in enumerate(rows):
        with cols[index % 4]:
            status_card(row["Card"], row["Current State"], f"{row['Freshness']} | {row['Evidence Source']}")


def v3_render_trading(records):
    open_rows = v3_open_trade_rows()
    closed_rows = v3_closed_trade_rows()
    consolidation = records["dashboard_truth_consolidation"]["payload"]
    open_count = "UNKNOWN" if open_rows is None else len(open_rows)
    if isinstance(consolidation, dict) and consolidation.get("active_trade_count") is not None:
        open_count = int(consolidation.get("active_trade_count"))
    closed_count = "UNKNOWN" if closed_rows is None else len(closed_rows)
    pnl_value = v3_account_value(records, ("daily_pnl", "pnl", "realized_pnl", "closed_pnl"))
    account_value = v3_account_value(records, ("account_balance", "balance", "equity"))
    exposure = v3_open_exposure(open_rows)
    rows = [
        {"Widget": "Account Status", "Current State": records["paper_account"].get("status"), "Value": account_value, "Evidence Source": records["paper_account"].get("path"), "Freshness": records["paper_account"].get("freshness")},
        {"Widget": "Open Trades", "Current State": "EVIDENCE_READ", "Value": open_count, "Evidence Source": "journal_truth_unification + active_trades.csv", "Freshness": records["journal_truth_unification"].get("freshness")},
        {"Widget": "Closed Trades", "Current State": "EVIDENCE_READ", "Value": closed_count, "Evidence Source": records["trade_outcomes"].get("path"), "Freshness": records["trade_outcomes"].get("freshness")},
        {"Widget": "PnL", "Current State": "UNKNOWN" if pnl_value == "UNKNOWN" else "EVIDENCE_READ", "Value": pnl_value, "Evidence Source": records["paper_account"].get("path"), "Freshness": records["paper_account"].get("freshness")},
        {"Widget": "Exposure", "Current State": "UNKNOWN" if exposure == "UNKNOWN" else "EVIDENCE_READ", "Value": exposure, "Evidence Source": records["active_trades"].get("path"), "Freshness": records["active_trades"].get("freshness")},
        {"Widget": "Risk Summary", "Current State": records["risk_watchdog"].get("status"), "Value": v3_compact_value(records["risk_watchdog"].get("payload", {}).get("summary")), "Evidence Source": records["risk_watchdog"].get("path"), "Freshness": records["risk_watchdog"].get("freshness")},
        {"Widget": "Execution Ownership", "Current State": v3_component(records, "paper_engine").get("status", "UNKNOWN"), "Value": v3_component(records, "paper_engine").get("reason", "UNKNOWN"), "Evidence Source": "authoritative_runtime_truth.components.paper_engine", "Freshness": records["authoritative_runtime_truth"].get("freshness")},
        {"Widget": "Active Trade Monitor", "Current State": records["trade_lifecycle_health"].get("status"), "Value": v3_compact_value(records["trade_lifecycle_health"].get("payload", {}).get("summary")), "Evidence Source": records["trade_lifecycle_health"].get("path"), "Freshness": records["trade_lifecycle_health"].get("freshness")},
    ]
    st.markdown("### Trading Department")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Open Trades", str(open_count), "Canonical active trade evidence")
    with c2:
        metric_card("Closed Trades", str(closed_count), "Closed outcomes only")
    with c3:
        metric_card("PnL", pnl_value, "No placeholder PnL")
    with c4:
        metric_card("Exposure", exposure, "Computed only from open trade rows with qty and price")
    v3_render_department_table(rows)


def v3_render_learning(records):
    rows = [
        v3_source_row(records, "Evolution Engine", "evolution_engine", purpose="Evolution engine activity"),
        v3_source_row(records, "Learning Queue", "reinforcement_learning", purpose="Learning queue and read/write state"),
        v3_source_row(records, "Outcome Analysis", "outcome_tracker", purpose="Outcome tracker evidence"),
        v3_source_row(records, "Memory Status", "memory_health", purpose="Memory health and write targets"),
        v3_source_row(records, "Pattern Discovery", "strategy_rejection_analysis", purpose="Pattern and rejection discovery"),
        v3_source_row(records, "Knowledge Growth", "memory_contribution", purpose="Knowledge contribution evidence"),
    ]
    st.markdown("### Learning Department")
    v3_render_department_table(rows)
    cols = st.columns(3)
    for index, row in enumerate(rows):
        with cols[index % 3]:
            status_card(row["Card"], row["Current State"], f"{row['Freshness']} | {row['Evidence Source']}")


def v3_render_echo(records):
    rows = [
        v3_source_row(records, "Current Mission", "echo_mission", purpose="Current ECHO/Codex request evidence"),
        v3_source_row(records, "Mission Queue", "echo_mission_queue", purpose="Queued approvals and missions"),
        v3_source_row(records, "Recent Reports", "echo_recent_report", purpose="Recent ECHO report evidence"),
        v3_source_row(records, "Files Reviewed", "echo_files_reviewed", purpose="Files reviewed or decision trace evidence"),
        v3_source_row(records, "Recommendations", "echo_recommendations", purpose="Recommendation evidence"),
        v3_source_row(records, "Diagnostics Activity", "echo_diagnostics", purpose="ECHO diagnostics activity"),
    ]
    st.markdown("### ECHO Department")
    v3_render_department_table(rows)
    cols = st.columns(3)
    for index, row in enumerate(rows):
        with cols[index % 3]:
            status_card(row["Card"], row["Current State"], f"{row['Freshness']} | {row['Evidence Source']}")


def v3_render_control_room(records):
    active, historical, open_warnings, resolved_warnings, conflicts = v3_incident_lists(records)
    safety_payload = records["authoritative_runtime_truth"].get("payload", {}).get("safety", {})
    safety_state = "UNKNOWN"
    if isinstance(safety_payload, dict) and safety_payload:
        unsafe = [key for key, value in safety_payload.items() if value is True and key not in {"diagnostic_status_write_only"}]
        safety_state = "BLOCKED" if unsafe else "READ_ONLY"
    truth_value, truth_sub = v3_trust_score(records)
    rows = [
        {"Widget": "Runtime Mode", "Current State": v3_active_mode(records), "Value": "Read-only display", "Evidence Source": "canonical_runtime_mode or titan_runtime_status", "Freshness": records["titan_runtime_status"].get("freshness")},
        {"Widget": "Execution Ownership", "Current State": v3_component(records, "daemon").get("runtime_owner", "UNKNOWN"), "Value": v3_component(records, "daemon").get("reason", "UNKNOWN"), "Evidence Source": "authoritative_runtime_truth.components.daemon", "Freshness": records["authoritative_runtime_truth"].get("freshness")},
        {"Widget": "Safety Gates", "Current State": safety_state, "Value": v3_compact_value(safety_payload), "Evidence Source": records["authoritative_runtime_truth"].get("path"), "Freshness": records["authoritative_runtime_truth"].get("freshness")},
        {"Widget": "Activation Readiness", "Current State": records["restart_readiness_gate"].get("status"), "Value": v3_compact_value(records["restart_readiness_gate"].get("payload", {}).get("summary")), "Evidence Source": records["restart_readiness_gate"].get("path"), "Freshness": records["restart_readiness_gate"].get("freshness")},
        {"Widget": "Runtime Permissions", "Current State": records["runtime_permissions"].get("status"), "Value": v3_compact_value(records["runtime_permissions"].get("payload")), "Evidence Source": records["runtime_permissions"].get("path"), "Freshness": records["runtime_permissions"].get("freshness")},
        {"Widget": "Department Summary", "Current State": "EVIDENCE_READ", "Value": f"Incidents={len(active)} | Open warnings={len(open_warnings)} | Conflicts={len(conflicts)}", "Evidence Source": "authoritative_runtime_truth + dashboard_runtime_integrity", "Freshness": records["authoritative_runtime_truth"].get("freshness")},
        {"Widget": "Truth Health", "Current State": records["truth_gate"].get("status"), "Value": f"{truth_value} | {truth_sub}", "Evidence Source": records["truth_gate"].get("path"), "Freshness": records["truth_gate"].get("freshness")},
    ]
    st.markdown("### Control Room")
    st.caption("Read-only visibility only. No dashboard controls are available for daemon, workers, scanner, HFT, TOIF, trades, broker, Upstox, or Telegram.")
    v3_render_department_table(rows)


def v3_join(values):
    values = [str(value) for value in values if value not in (None, "", [], {})]
    return ", ".join(values) if values else "UNKNOWN"


def v3_age_label(record):
    age = record.get("age_seconds")
    if age is None:
        return "UNKNOWN"
    try:
        age = float(age)
    except Exception:
        return "UNKNOWN"
    if age < 60:
        return f"{int(age)}s"
    if age < 3600:
        return f"{int(age // 60)}m"
    return f"{round(age / 3600, 1)}h"


def v3_dependency_edges(records):
    payload = records.get("metric_dependency_graph", {}).get("payload", {})
    edges = payload.get("dependencies") if isinstance(payload, dict) else None
    if not isinstance(edges, list):
        return []
    normalized = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = edge.get("from")
        target = edge.get("to")
        if not source or not target:
            continue
        normalized.append({
            "Widget": "Dependency Graph Flows",
            "Source": str(source),
            "Consumer": str(target),
            "Flow Direction": f"{source} -> {target}",
            "Dependency Type": str(edge.get("type") or "UNKNOWN"),
            "Evidence Path": records.get("metric_dependency_graph", {}).get("path", "UNKNOWN"),
            "Freshness": records.get("metric_dependency_graph", {}).get("freshness", "UNKNOWN"),
            "Purpose": "Show published metric dependency edge",
            "Freshness Rule": "Uses metric_dependency_graph freshness; stale graph keeps edges visible as STALE",
            "Unknown Rule": "Missing dependency graph or malformed edges display UNKNOWN/no rows",
            "Failure Rule": "Do not infer unpublished edges",
        })
    return normalized


def v3_source_consumers(source_name):
    return V3_DASHBOARD_SOURCE_CONSUMERS.get(source_name, ["UNKNOWN"])


def v3_dashboard_flow_rows(records):
    rows = []
    for source_name, consumers in sorted(V3_DASHBOARD_SOURCE_CONSUMERS.items()):
        record = records.get(source_name, {})
        for consumer in consumers:
            rows.append({
                "Widget": "Dashboard Evidence Flows",
                "Source": source_name,
                "Consumer": consumer,
                "Flow Direction": f"{source_name} -> {consumer}",
                "Evidence Path": record.get("path") or str(V3_TRUTH_SOURCES.get(source_name, "UNKNOWN")).replace("\\", "/"),
                "Freshness": record.get("freshness") or "UNKNOWN",
                "Purpose": "Show actual dashboard evidence consumption",
                "Freshness Rule": "Per-source V3 truth source freshness",
                "Unknown Rule": "If source is missing or consumer mapping is absent, display UNKNOWN",
                "Failure Rule": "Do not show activity beyond read-only dashboard consumption",
            })
    return rows


def v3_layer_status(records, source_names):
    source_records = [records.get(name, {}) for name in source_names]
    if any(record.get("freshness") == "STALE" for record in source_records):
        return "STALE"
    if any(record.get("freshness") == "UNKNOWN" for record in source_records):
        return "UNKNOWN"
    statuses = {str(record.get("status") or "UNKNOWN").upper() for record in source_records}
    problem_statuses = {"FAIL", "FAILED", "CONFLICT", "STOPPED", "DEGRADED", "BLOCKED"}
    if statuses & problem_statuses:
        return v3_join(sorted(statuses & problem_statuses))
    return "EVIDENCE_READ" if source_records else "UNKNOWN"


def v3_layer_dependencies(records, source_names):
    edges = v3_dependency_edges(records)
    matched = []
    source_set = set(source_names)
    for edge in edges:
        if edge["Source"] in source_set or edge["Consumer"] in source_set:
            matched.append(edge["Flow Direction"])
    return v3_join(matched[:12])


def v3_render_system_mindmap(records):
    rows = []
    for layer, source_names in V3_D03_LAYER_SOURCES.items():
        layer_records = [records.get(name, {}) for name in source_names]
        rows.append({
            "Component": layer,
            "State": v3_layer_status(records, source_names),
            "Dependencies": v3_layer_dependencies(records, source_names),
            "Inputs": v3_join(source_names),
            "Outputs": v3_join(sorted({consumer for name in source_names for consumer in v3_source_consumers(name)})),
            "Freshness": v3_join(sorted({record.get("freshness") or "UNKNOWN" for record in layer_records})),
            "Purpose": "Provide live structural map of TITAN layer evidence",
            "Source": v3_join(record.get("path") for record in layer_records),
            "Consumer": v3_join(sorted({consumer for name in source_names for consumer in v3_source_consumers(name)})),
            "Freshness Rule": "Layer freshness is derived from member truth sources; stale member keeps layer STALE",
            "Unknown Rule": "Missing layer evidence, missing dependency edge, or missing component displays UNKNOWN",
            "Failure Rule": "No decorative or inferred dependencies; dependency column only uses published graph edges",
        })
    st.markdown("### System Mindmap")
    v3_render_department_table(rows)


def v3_render_flow_visualizer(records):
    dashboard_rows = v3_dashboard_flow_rows(records)
    dependency_rows = v3_dependency_edges(records)
    example_rows = [
        row for row in dashboard_rows
        if row["Source"] in {"authoritative_runtime_truth", "runtime_error_summary", "journal_truth_unification"}
    ]
    st.markdown("### Dashboard Evidence Flows")
    v3_render_department_table(example_rows or dashboard_rows[:25])
    st.markdown("### Published Dependency Graph Flows")
    v3_render_department_table(dependency_rows or [{
        "Widget": "Dependency Graph Flows",
        "Source": records.get("metric_dependency_graph", {}).get("path", "UNKNOWN"),
        "Consumer": "UNKNOWN",
        "Flow Direction": "UNKNOWN",
        "Evidence Path": records.get("metric_dependency_graph", {}).get("path", "UNKNOWN"),
        "Freshness": records.get("metric_dependency_graph", {}).get("freshness", "UNKNOWN"),
        "Purpose": "Show published dependency edges",
        "Freshness Rule": "metric_dependency_graph freshness",
        "Unknown Rule": "No graph edges means UNKNOWN",
        "Failure Rule": "Do not fabricate flows",
    }])


def v3_render_truth_explorer(records):
    dependency_edges = v3_dependency_edges(records)
    dependency_count_by_source = {}
    for edge in dependency_edges:
        dependency_count_by_source[edge["Source"]] = dependency_count_by_source.get(edge["Source"], 0) + 1
    rows = []
    for name, record in sorted(records.items()):
        rows.append({
            "Source Name": name,
            "File Path": record.get("path") or "UNKNOWN",
            "Status": record.get("status") or "UNKNOWN",
            "Freshness": record.get("freshness") or "UNKNOWN",
            "Consumers": v3_join(v3_source_consumers(name)),
            "Last Read": datetime.now(IST).strftime("%d %b %Y %H:%M:%S IST"),
            "Dependency Count": dependency_count_by_source.get(name, 0),
            "Purpose": "Inspect dashboard truth source and consumers",
            "Source": record.get("path") or "UNKNOWN",
            "Consumer": v3_join(v3_source_consumers(name)),
            "Freshness Rule": "Per-source V3 truth source freshness",
            "Unknown Rule": "Missing file, timestamp, consumer, or dependency count displays UNKNOWN/0 as applicable",
            "Failure Rule": "Read-only navigator only; no source mutation",
        })
    st.markdown("### Truth Source Navigator")
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.markdown("### Dependency Detail")
    v3_render_department_table(dependency_edges)


def v3_freshness_class(record):
    freshness = str(record.get("freshness") or "UNKNOWN").upper()
    if freshness == "FRESH":
        return "Fresh"
    if freshness == "STALE":
        return "Stale"
    age = record.get("age_seconds")
    if age is not None:
        try:
            return "Warning" if float(age) > 600 else "Fresh"
        except Exception:
            pass
    return "Unknown"


def v3_render_freshness_explorer(records):
    rows = []
    for name, record in sorted(records.items()):
        rows.append({
            "Source Name": name,
            "Evidence Age": v3_age_label(record),
            "Freshness Classification": v3_freshness_class(record),
            "Consumer Impact": v3_join(v3_source_consumers(name)),
            "Freshness": record.get("freshness") or "UNKNOWN",
            "Status": record.get("status") or "UNKNOWN",
            "Purpose": "Monitor evidence freshness and dashboard impact",
            "Source": record.get("path") or "UNKNOWN",
            "Consumer": v3_join(v3_source_consumers(name)),
            "Freshness Rule": "Runtime/external sources default to 900s; advisory sources default to 86400s when documented",
            "Unknown Rule": "Missing source or timestamp displays Unknown",
            "Failure Rule": "Stale evidence stays visible and is never converted to healthy state",
        })
    counts = {label: len([row for row in rows if row["Freshness Classification"] == label]) for label in ("Fresh", "Warning", "Stale", "Unknown")}
    cols = st.columns(4)
    for index, label in enumerate(("Fresh", "Warning", "Stale", "Unknown")):
        with cols[index]:
            status_card(f"{label} Sources", str(counts[label]), "Freshness Explorer classification")
    st.markdown("### Freshness Impact")
    st.dataframe(rows, use_container_width=True, hide_index=True)


def v3_architecture_rows(records):
    return [
        {
            "Boundary": "Runtime Boundaries",
            "May Read": "Dashboard may read local runtime evidence artifacts",
            "May Write": "Nothing from dashboard render path",
            "Forbidden": "Daemon/worker/scanner/scheduler start, stop, restart, or mutation",
            "Source": v3_join([records.get("runtime_visibility_audit", {}).get("path"), records.get("runtime_permissions", {}).get("path")]),
            "Consumer": "Architecture Department",
        },
        {
            "Boundary": "Ownership Boundaries",
            "May Read": "Published ownership maps and canonical metric ownership",
            "May Write": "Nothing",
            "Forbidden": "Changing metric owners or runtime owners",
            "Source": v3_join([records.get("canonical_metric_ownership", {}).get("path"), records.get("echo_ownership_map", {}).get("path")]),
            "Consumer": "Architecture Department",
        },
        {
            "Boundary": "Trust Boundaries",
            "May Read": "Truth registry, truth gate, authoritative runtime truth",
            "May Write": "Nothing",
            "Forbidden": "Promoting stale or missing evidence to healthy state",
            "Source": v3_join([records.get("dashboard_truth_registry", {}).get("path"), records.get("truth_gate", {}).get("path"), records.get("authoritative_runtime_truth", {}).get("path")]),
            "Consumer": "Architecture Department",
        },
        {
            "Boundary": "Read-Only Boundaries",
            "May Read": "Local JSON, JSONL, and CSV evidence",
            "May Write": "Nothing",
            "Forbidden": "Broker, Upstox, Telegram, scanner, worker, HFT, TOIF, learning, evolution, or trading runtime calls",
            "Source": records.get("dashboard_truth_registry", {}).get("path") or "UNKNOWN",
            "Consumer": "All V3 pages",
        },
        {
            "Boundary": "Dashboard Boundaries",
            "May Read": "V3_TRUTH_SOURCES inventory",
            "May Write": "In-memory dashboard_truth_consolidation only with write=False",
            "Forbidden": "Dashboard-controlled runtime actions",
            "Source": "dashboard.py V3_TRUTH_SOURCES",
            "Consumer": "Dashboard V3",
        },
        {
            "Boundary": "Classic/HFT Separation",
            "May Read": "HFT local visibility artifacts only",
            "May Write": "Nothing",
            "Forbidden": "HFT activation or execution integration from dashboard",
            "Source": v3_join([records.get("hft_health", {}).get("path"), records.get("hft_runtime_state", {}).get("path"), records.get("hft_safety_proof", {}).get("path")]),
            "Consumer": "System Mindmap, Architecture Department",
        },
        {
            "Boundary": "Alpha Isolation",
            "May Read": "Alpha/TOIF local visibility artifacts only",
            "May Write": "Nothing",
            "Forbidden": "TOIF integration, Upstox calls, or alpha runtime activation",
            "Source": v3_join([records.get("alpha_health", {}).get("path"), records.get("alpha_input_manifest", {}).get("path"), records.get("alpha_wiring_report", {}).get("path")]),
            "Consumer": "System Mindmap, Architecture Department",
        },
        {
            "Boundary": "Classic TITAN Domain",
            "May Read": "Classic runtime, scanner, trading, learning, memory, journal, and dashboard truth artifacts",
            "May Write": "Classic runtime writers only; Dashboard V3 writes nothing",
            "Forbidden": "HFT/Alpha writes into Classic memory, journal, evolution, Master Brain, scheduler, broker, or execution systems",
            "Source": v3_join([records.get("authoritative_runtime_truth", {}).get("path"), records.get("journal_truth_unification", {}).get("path"), records.get("dashboard_truth_registry", {}).get("path")]),
            "Consumer": "Architecture Department",
        },
        {
            "Boundary": "HFT TITAN Domain",
            "May Read": "Local HFT visibility artifacts under data/hft_mode",
            "May Write": "HFT data root only when HFT runtime writes its own artifacts; Dashboard V3 writes nothing",
            "Forbidden": "Classic memory, Classic journal, Classic evolution, Master Brain, broker, Telegram, scanner, worker, scheduler, daemon, or execution writes",
            "Source": v3_join([records.get("hft_safety_proof", {}).get("path"), records.get("hft_runtime_state", {}).get("path")]),
            "Consumer": "Architecture Department, HFT Department",
        },
        {
            "Boundary": "Alpha Lab Domain",
            "May Read": "Local Alpha/TOIF shadow artifacts under data/runtime/alpha_math and data/runtime/alpha_inputs",
            "May Write": "Alpha shadow artifacts only when Alpha tools run outside dashboard; Dashboard V3 writes nothing",
            "Forbidden": "Classic execution, broker, Upstox calls from dashboard, TOIF runtime activation, Master Brain writes, Classic journal/memory/evolution writes",
            "Source": v3_join([records.get("alpha_health", {}).get("path"), records.get("alpha_shadow_outcome_report", {}).get("path"), records.get("alpha_pending_outcomes", {}).get("path")]),
            "Consumer": "Architecture Department, Alpha Lab",
        },
    ]


def v3_render_architecture_department(records):
    rows = []
    for row in v3_architecture_rows(records):
        row.update({
            "Purpose": "Expose TITAN architecture boundary",
            "Freshness": "EVIDENCE_POLICY",
            "Freshness Rule": "Boundary rows are dashboard policy backed by listed evidence when present",
            "Unknown Rule": "Missing boundary evidence paths remain UNKNOWN",
            "Failure Rule": "Forbidden actions are never represented as available controls",
        })
        rows.append(row)
    st.markdown("### Architecture Boundaries")
    st.dataframe(rows, use_container_width=True, hide_index=True)


def v3_bool_state(value, true_state="TRUE", false_state="FALSE"):
    if value is True:
        return true_state
    if value is False:
        return false_state
    return "UNKNOWN"


def v3_record_sources(records, source_names):
    return v3_join(records.get(name, {}).get("path") for name in source_names)


def v3_record_freshness(records, source_names):
    return v3_join(sorted({records.get(name, {}).get("freshness") or "UNKNOWN" for name in source_names}))


def v3_visibility_row(widget, purpose, source_names, state, evidence, dependencies="UNKNOWN"):
    return {
        "Widget": widget,
        "Purpose": purpose,
        "Current State": v3_compact_value(state),
        "Evidence": v3_compact_value(evidence),
        "Freshness": "UNKNOWN",
        "Dependencies": v3_compact_value(dependencies),
        "Source": "UNKNOWN",
        "Consumer": "Dashboard V3 visibility page",
        "Freshness Rule": "Per-source V3 truth source freshness; stale evidence stays visible as STALE",
        "Unknown Rule": "Missing file, missing field, unreadable JSON, or absent metric displays UNKNOWN",
        "Failure Rule": "No activation, no runtime control, no execution control, and no fabricated health/readiness",
        "_source_names": source_names,
    }


def v3_finalize_visibility_rows(records, rows):
    finalized = []
    for row in rows:
        source_names = row.pop("_source_names", [])
        row["Source"] = v3_record_sources(records, source_names)
        row["Evidence Source"] = row["Source"]
        row["Freshness"] = v3_record_freshness(records, source_names)
        finalized.append(row)
    return finalized


def v3_render_hft_department(records):
    health = records.get("hft_health", {}).get("payload", {})
    runtime = records.get("hft_runtime_state", {}).get("payload", {})
    safety = records.get("hft_safety_proof", {}).get("payload", {})
    stats = records.get("hft_stats", {}).get("payload", {})
    rows = [
        v3_visibility_row("HFT Status", "Expose HFT current status", ["hft_health", "hft_safety_proof"], safety.get("final_status") or health.get("status"), {"health_status": health.get("status"), "final_status": safety.get("final_status")}, "hft_health + hft_safety_proof"),
        v3_visibility_row("Build Status", "Show HFT build and disconnected proof", ["hft_safety_proof"], safety.get("final_status"), {"hft_off_by_default": safety.get("hft_off_by_default"), "forbidden_imports_found": safety.get("forbidden_imports_found")}, "hft_safety_proof"),
        v3_visibility_row("Runtime Status", "Prove HFT is not running or connected to Classic runtime", ["hft_runtime_state", "hft_safety_proof"], "DISCONNECTED" if runtime.get("connected_to_runtime") is False and runtime.get("worker_started") is False else "UNKNOWN", {"connected_to_runtime": runtime.get("connected_to_runtime"), "worker_started": runtime.get("worker_started"), "hft_enabled": runtime.get("hft_enabled")}, "hft_runtime_state"),
        v3_visibility_row("Scheduler Status", "Show no runtime scheduler integration", ["hft_safety_proof"], v3_bool_state(safety.get("runtime_scheduler_integration_present"), "INTEGRATED", "DISCONNECTED"), {"runtime_scheduler_integration_present": safety.get("runtime_scheduler_integration_present"), "worker_auto_started": safety.get("worker_auto_started")}, "hft_safety_proof"),
        v3_visibility_row("Ownership Status", "Show HFT does not own execution or broker behavior", ["hft_health", "hft_safety_proof", "hft_stats"], "NO_EXECUTION_CONTROL" if safety.get("broker_allowed") is False and stats.get("live_orders") == 0 else "UNKNOWN", {"broker_allowed": safety.get("broker_allowed"), "live_orders": stats.get("live_orders"), "live_order_methods_found": safety.get("live_order_methods_found")}, "hft_health + hft_stats"),
        v3_visibility_row("Memory Isolation", "Prove HFT does not write Classic memory", ["hft_safety_proof"], v3_bool_state(safety.get("classic_memory_write_allowed"), "WRITE_ALLOWED", "ISOLATED"), {"classic_memory_write_allowed": safety.get("classic_memory_write_allowed")}, "hft_safety_proof"),
        v3_visibility_row("Journal Isolation", "Prove HFT does not write Classic journal", ["hft_safety_proof"], v3_bool_state(safety.get("classic_journal_write_allowed"), "WRITE_ALLOWED", "ISOLATED"), {"classic_journal_write_allowed": safety.get("classic_journal_write_allowed"), "data_write_root": safety.get("data_write_root")}, "hft_safety_proof"),
        v3_visibility_row("Dashboard Isolation", "Show dashboard has visibility only and no HFT integration control", ["hft_safety_proof"], "READ_ONLY" if safety.get("dashboard_export_read_only") is True else "UNKNOWN", {"dashboard_export_read_only": safety.get("dashboard_export_read_only"), "dashboard_integration_present": safety.get("dashboard_integration_present")}, "hft_safety_proof"),
        v3_visibility_row("Master Brain Isolation", "Prove HFT does not write or control Master Brain", ["hft_safety_proof"], v3_bool_state(safety.get("master_brain_access_allowed"), "ACCESS_ALLOWED", "ISOLATED"), {"master_brain_access_allowed": safety.get("master_brain_access_allowed")}, "hft_safety_proof"),
        v3_visibility_row("Evolution Isolation", "Prove HFT does not write Classic evolution", ["hft_safety_proof"], v3_bool_state(safety.get("titan_evolution_write_allowed"), "WRITE_ALLOWED", "ISOLATED"), {"titan_evolution_write_allowed": safety.get("titan_evolution_write_allowed")}, "hft_safety_proof"),
        v3_visibility_row("Dependency Map", "Expose HFT dependencies without inventing runtime links", ["hft_safety_proof"], "NO_FORBIDDEN_IMPORTS" if not safety.get("forbidden_imports_found") else "FORBIDDEN_IMPORTS_FOUND", {"forbidden_imports_checked": safety.get("forbidden_imports_checked"), "forbidden_imports_found": safety.get("forbidden_imports_found")}, "hft_safety_proof.forbidden_imports_checked"),
        v3_visibility_row("Read Boundaries", "Show HFT read/visibility boundary evidence", ["hft_safety_proof"], "HFT_LOCAL_ONLY", {"allowed_data_files": safety.get("allowed_data_files")}, "data/hft_mode local artifacts"),
        v3_visibility_row("Write Boundaries", "Show HFT write boundary evidence", ["hft_safety_proof"], "CONFINED" if safety.get("write_paths_confined_to_hft_data") is True else "UNKNOWN", {"write_paths_confined_to_hft_data": safety.get("write_paths_confined_to_hft_data"), "data_write_root": safety.get("data_write_root")}, "data/hft_mode"),
    ]
    st.markdown("### HFT Department")
    st.caption("Visibility only. No HFT activation, execution control, broker call, scheduler integration, or ownership transfer is exposed.")
    v3_render_department_table(v3_finalize_visibility_rows(records, rows))


def v3_count_csv_rows(path):
    rows = v3_read_csv_rows(path)
    if rows is None:
        return None
    return len(rows)


def v3_alpha_lane_summary(lane_payload, key):
    items = lane_payload.get(key) if isinstance(lane_payload, dict) else None
    if not isinstance(items, list):
        return {"predictions": "UNKNOWN", "memory_status": "UNKNOWN", "confidence_status": "UNKNOWN"}
    memory_missing = 0
    confidence_values = []
    for item in items:
        if isinstance(item, dict):
            missing_inputs = item.get("missing_inputs") or []
            if "memory" in missing_inputs:
                memory_missing += 1
            if item.get("confidence") is not None:
                confidence_values.append(item.get("confidence"))
    confidence_status = "UNKNOWN"
    if confidence_values:
        try:
            avg = sum(float(value) for value in confidence_values) / len(confidence_values)
            confidence_status = f"avg_confidence={round(avg, 3)}"
        except Exception:
            confidence_status = "UNKNOWN"
    return {
        "predictions": len(items),
        "memory_status": "MISSING" if memory_missing else ("READY" if items else "UNKNOWN"),
        "confidence_status": confidence_status,
    }


def v3_render_alpha_lab(records):
    health = records.get("alpha_health", {}).get("payload", {})
    pending = records.get("alpha_pending_outcomes", {}).get("payload", {})
    outcome = records.get("alpha_shadow_outcome_report", {}).get("payload", {})
    memory = records.get("alpha_memory_summary", {}).get("payload", {})
    lanes = records.get("alpha_lane_candidates", {}).get("payload", {})
    latest = records.get("alpha_latest_scores", {}).get("payload", {})
    rerun = records.get("alpha_rerun_readiness", {}).get("payload", {})
    final_status = records.get("alpha_shadow_lab_final_status", {}).get("payload", {})
    pending_summary = pending.get("summary") if isinstance(pending, dict) else {}
    pending_summary = pending_summary if isinstance(pending_summary, dict) else {}
    scores = latest.get("scores") if isinstance(latest, dict) else None
    prediction_count = health.get("scored_count")
    if prediction_count is None and isinstance(scores, list):
        prediction_count = len(scores)
    outcome_count = None
    if outcome.get("resolved_win_count") is not None or outcome.get("resolved_loss_count") is not None:
        outcome_count = int(outcome.get("resolved_win_count") or 0) + int(outcome.get("resolved_loss_count") or 0)
    unresolved_count = pending_summary.get("total_pending") or outcome.get("unresolved_count") or rerun.get("pending_outcome_count")
    similar_wins = v3_first_present(health.get("source_quality_summary", {}).get("missing_fields_by_name", {}) if isinstance(health.get("source_quality_summary"), dict) else {}, ("similar_wins",), default=None)
    similar_losses = v3_first_present(health.get("source_quality_summary", {}).get("missing_fields_by_name", {}) if isinstance(health.get("source_quality_summary"), dict) else {}, ("similar_losses",), default=None)
    lane_overview = {
        "elite": len(lanes.get("top_elite") or []) if isinstance(lanes, dict) else "UNKNOWN",
        "strong": len(lanes.get("top_strong") or []) if isinstance(lanes, dict) else "UNKNOWN",
        "micro": len(lanes.get("top_micro") or []) if isinstance(lanes, dict) else "UNKNOWN",
    }
    rows = [
        v3_visibility_row("Alpha Status", "Expose TOIF-v4 shadow system status", ["alpha_health", "alpha_shadow_lab_final_status"], health.get("status_reason") or final_status.get("status") or health.get("status"), {"shadow_only": health.get("shadow_only"), "can_execute": health.get("can_execute"), "safe_to_integrate_runtime": health.get("safe_to_integrate_runtime")}, "alpha_health + alpha_shadow_lab_final_status"),
        v3_visibility_row("Alpha Health", "Show Alpha health evidence", ["alpha_health"], health.get("status"), {"safety_status": health.get("safety_status"), "errors": health.get("errors"), "formula_version": health.get("formula_version")}, "alpha_health"),
        v3_visibility_row("Shadow Mode Status", "Show shadow-only and execution prohibition evidence", ["alpha_health", "alpha_pending_outcomes"], "SHADOW_ONLY" if health.get("shadow_only") is True and health.get("can_execute") is False else "UNKNOWN", {"shadow_only": health.get("shadow_only"), "can_execute": health.get("can_execute"), "pending_shadow_only": pending_summary.get("shadow_only")}, "alpha_health + alpha_pending_outcomes"),
        v3_visibility_row("Outcome Resolver Status", "Show outcome resolver state", ["alpha_shadow_outcome_report", "alpha_rerun_readiness"], rerun.get("current_status") or outcome.get("status"), {"rerun_condition": outcome.get("rerun_condition"), "ready_to_resolve_now": rerun.get("ready_to_resolve_now")}, "alpha_shadow_outcome_report + alpha_rerun_readiness"),
        v3_visibility_row("Pending Outcome Tracker", "Show pending outcome evidence", ["alpha_pending_outcomes", "alpha_rerun_readiness"], pending_summary.get("total_pending") or rerun.get("pending_outcome_count"), {"reason": pending_summary.get("main_reasons") or rerun.get("reason_if_not_ready")}, "alpha_pending_outcomes"),
        v3_visibility_row("Memory Readiness", "Show Alpha memory readiness evidence", ["alpha_memory_summary", "alpha_shadow_outcome_report"], v3_bool_state(memory.get("memory_ready") or outcome.get("memory_ready"), "READY", "NOT_READY"), {"memory_ready": memory.get("memory_ready"), "groups": len(memory.get("groups") or []) if isinstance(memory.get("groups"), list) else "UNKNOWN"}, "alpha_memory_summary"),
        v3_visibility_row("Lane Overview", "Show lane counts from Alpha candidate evidence", ["alpha_lane_candidates"], lane_overview, lane_overview, "alpha_lane_candidates"),
        v3_visibility_row("Elite Lane", "Show Elite lane prediction status", ["alpha_lane_candidates", "alpha_shadow_outcome_report"], v3_alpha_lane_summary(lanes, "top_elite").get("predictions"), {**v3_alpha_lane_summary(lanes, "top_elite"), "resolved": outcome_count, "pending": unresolved_count}, "alpha_lane_candidates.top_elite"),
        v3_visibility_row("Strong Lane", "Show Strong lane prediction status", ["alpha_lane_candidates", "alpha_shadow_outcome_report"], v3_alpha_lane_summary(lanes, "top_strong").get("predictions"), {**v3_alpha_lane_summary(lanes, "top_strong"), "resolved": outcome_count, "pending": unresolved_count}, "alpha_lane_candidates.top_strong"),
        v3_visibility_row("Micro Lane", "Show Micro lane prediction status", ["alpha_lane_candidates", "alpha_shadow_outcome_report"], v3_alpha_lane_summary(lanes, "top_micro").get("predictions"), {**v3_alpha_lane_summary(lanes, "top_micro"), "resolved": outcome_count, "pending": unresolved_count}, "alpha_lane_candidates.top_micro"),
        v3_visibility_row("Prediction Count", "Show prediction count from Alpha evidence", ["alpha_health", "alpha_latest_scores", "alpha_shadow_journal"], prediction_count, {"scored_count": health.get("scored_count"), "journal_rows": v3_count_csv_rows(V3_TRUTH_SOURCES["alpha_shadow_journal"])}, "alpha_health + latest_scores + shadow_journal"),
        v3_visibility_row("Outcome Count", "Show resolved outcome count", ["alpha_shadow_outcome_report"], outcome_count, {"resolved_win_count": outcome.get("resolved_win_count"), "resolved_loss_count": outcome.get("resolved_loss_count"), "ambiguous_count": outcome.get("ambiguous_count")}, "alpha_shadow_outcome_report"),
        v3_visibility_row("Unresolved Count", "Show unresolved/pending outcome count", ["alpha_pending_outcomes", "alpha_rerun_readiness"], unresolved_count, {"total_pending": pending_summary.get("total_pending"), "pending_outcome_count": rerun.get("pending_outcome_count")}, "alpha_pending_outcomes + alpha_rerun_readiness"),
        v3_visibility_row("Similar Wins", "Show similar-win memory evidence or missing count", ["alpha_health", "alpha_memory_summary"], similar_wins, {"similar_wins_missing_count": similar_wins, "memory_ready": memory.get("memory_ready")}, "alpha_health.source_quality_summary"),
        v3_visibility_row("Similar Losses", "Show similar-loss memory evidence or missing count", ["alpha_health", "alpha_memory_summary"], similar_losses, {"similar_losses_missing_count": similar_losses, "memory_ready": memory.get("memory_ready")}, "alpha_health.source_quality_summary"),
        v3_visibility_row("Outcome Resolution Health", "Show readiness for outcome resolution", ["alpha_shadow_outcome_report", "alpha_rerun_readiness"], "WAITING_FOR_OUTCOMES" if rerun.get("ready_to_resolve_now") is False else "UNKNOWN", {"current_status": rerun.get("current_status"), "reason_if_not_ready": rerun.get("reason_if_not_ready"), "safe_to_integrate_runtime": outcome.get("safe_to_integrate_runtime")}, "alpha_shadow_outcome_report + alpha_rerun_readiness"),
    ]
    st.markdown("### Alpha Lab")
    st.caption("TOIF-v4 shadow visibility only. No TOIF activation, Upstox call, runtime integration, or execution control is exposed.")
    v3_render_department_table(v3_finalize_visibility_rows(records, rows))


def v3_render_header(records):
    now = datetime.now(IST)
    market = v3_market_clock()
    mode = v3_active_mode(records)
    last_verified = v3_latest_verified(records)
    components.html(
        f"""
        <div style="font-family:Arial,sans-serif;color:#e5e7eb;background:#111827;border:1px solid #334155;border-radius:8px;padding:12px 14px;display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:10px;">
          <div><b>Date</b><br>{now.strftime('%d %b %Y')}</div>
          <div><b>Time</b><br><span id="v3-clock">{now.strftime('%H:%M:%S')}</span></div>
          <div><b>Market Clock</b><br>{market}</div>
          <div><b>VPS Clock</b><br>IST</div>
          <div><b>Active Mode</b><br>{mode}</div>
          <div><b>Last Verified</b><br>{last_verified}</div>
          <div><b>Auto Refresh</b><br>{AUTO_REFRESH_SECONDS}s ON</div>
        </div>
        <script>
          setInterval(function() {{
            const now = new Date();
            const opts = {{hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false, timeZone:'Asia/Kolkata'}};
            const el = document.getElementById('v3-clock');
            if (el) el.textContent = new Intl.DateTimeFormat('en-GB', opts).format(now);
          }}, 1000);
        </script>
        """,
        height=92,
    )


def v3_render_quick_grid(records):
    items = [
        ("Daemon", v3_component(records, "daemon")),
        ("Workers", v3_component(records, "workers")),
        ("Scheduler", v3_component(records, "scheduler")),
        ("Scanner", v3_component(records, "scanner")),
        ("Setup Engine", v3_component(records, "setup_engine")),
        ("OHLC", v3_component(records, "ohlc_health")),
        ("Master Brain", v3_component(records, "master_brain")),
        ("Paper Engine", v3_component(records, "paper_engine")),
    ]
    cols = st.columns(4)
    for index, (label, record) in enumerate(items):
        with cols[index % 4]:
            status_card(label, str(record.get("status") or "UNKNOWN").upper(), v3_status_line(record))


def v3_render_command_center(records):
    active, historical, open_warnings, resolved_warnings, conflicts = v3_incident_lists(records)
    consolidation = records["dashboard_truth_consolidation"]["payload"]
    trust_value, trust_sub = v3_trust_score(records)
    components_map = records["authoritative_runtime_truth"]["payload"].get("components", {})
    components_map = components_map if isinstance(components_map, dict) else {}
    stale_sources = [name for name, record in records.items() if record.get("freshness") == "STALE"]
    unknown_sources = [name for name, record in records.items() if record.get("freshness") == "UNKNOWN"]
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        status_card("System State", consolidation.get("dashboard_overall_status", "UNKNOWN"), "Source: dashboard truth consolidation")
    with c2:
        metric_card("Trust Score", trust_value, trust_sub)
    with c3:
        metric_card("Runtime Overview", f"{len(components_map)} components", "Authoritative runtime truth component count")
    with c4:
        metric_card("Trading Overview", str(consolidation.get("active_trade_count", "UNKNOWN")), consolidation.get("active_trade_count_source", "UNKNOWN"))
    c5, c6 = st.columns(2)
    with c5:
        status_card("Active Incidents", "UNKNOWN" if not active else "WARNING", f"{len(active)} active evidence-backed items")
    with c6:
        status_card("Evidence Freshness Summary", "STALE" if stale_sources else ("UNKNOWN" if unknown_sources else "FRESH"), f"Stale: {len(stale_sources)} | Unknown: {len(unknown_sources)}")
    st.markdown("### Quick Status Grid")
    v3_render_quick_grid(records)
    st.markdown("### Mini System Map")
    map_rows = [
        {
            "Component": name,
            "State": str((record or {}).get("status") or "UNKNOWN").upper(),
            "Evidence": (record or {}).get("source_file") or "UNKNOWN",
            "Reason": (record or {}).get("reason") or "UNKNOWN",
        }
        for name, record in sorted(components_map.items())
    ]
    st.dataframe(map_rows, use_container_width=True, hide_index=True)


def v3_render_runtime(records):
    runtime_items = [
        ("Daemon", "daemon"),
        ("Lock Ownership", "daemon"),
        ("Runtime Mode", None),
        ("Heartbeat", "daemon"),
        ("Workers", "workers"),
        ("Scheduler", "scheduler"),
        ("Runtime Truth", None),
    ]
    cols = st.columns(3)
    for index, (title, component_name) in enumerate(runtime_items):
        with cols[index % 3]:
            if title == "Runtime Mode":
                status_card(title, v3_active_mode(records), "Source: canonical_runtime_mode or titan_runtime_status")
            elif title == "Runtime Truth":
                record = records["authoritative_runtime_truth"]
                status_card(title, record.get("status", "UNKNOWN"), v3_status_line(record))
            elif title == "Lock Ownership":
                record = v3_component(records, component_name)
                owner = record.get("runtime_owner") or record.get("lock_pid") or "UNKNOWN"
                status_card(title, str(owner).upper(), v3_status_line(record))
            elif title == "Heartbeat":
                record = v3_component(records, component_name)
                heartbeat = record.get("heartbeat_status") or record.get("status") or "UNKNOWN"
                status_card(title, str(heartbeat).upper(), v3_status_line(record))
            else:
                record = v3_component(records, component_name)
                status_card(title, str(record.get("status") or "UNKNOWN").upper(), v3_status_line(record))
    st.markdown("### Current Evidence")
    rows = []
    for name in ("authoritative_runtime_truth", "titan_runtime_status", "daemon_health", "titan_heartbeat", "worker_health", "scanner_scheduler"):
        record = records[name]
        rows.append({
            "Source": name,
            "Status": record.get("status"),
            "Freshness": record.get("freshness"),
            "AgeSeconds": record.get("age_seconds"),
            "Path": record.get("path"),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)


def v3_render_diagnostics(records):
    active, historical, open_warnings, resolved_warnings, conflicts = v3_incident_lists(records)
    integrity = records["dashboard_runtime_integrity"]["payload"]
    error_summary = records["runtime_error_summary"]["payload"]
    stale_sources = [name for name, record in records.items() if record.get("freshness") == "STALE"]
    unknown_sources = [name for name, record in records.items() if record.get("freshness") == "UNKNOWN"]
    d1, d2, d3 = st.columns(3)
    with d1:
        metric_card("Runtime Errors", str(error_summary.get("error_count", len(historical)) if isinstance(error_summary, dict) else len(historical)), "Source: runtime_error_summary and daemon_errors")
    with d2:
        metric_card("Error Trends", str(error_summary.get("trend", "UNKNOWN") if isinstance(error_summary, dict) else "UNKNOWN"), "No trend if artifact does not publish one")
    with d3:
        status_card("Truth Conflicts", "CONFLICT" if conflicts else "UNKNOWN", f"{len(conflicts)} conflicts from authoritative summary")
    d4, d5, d6 = st.columns(3)
    with d4:
        status_card("Stale Evidence", "STALE" if stale_sources else "UNKNOWN", ", ".join(stale_sources[:6]) or "No stale source list")
    with d5:
        status_card("Freshness Problems", "UNKNOWN" if unknown_sources else "FRESH", f"Unknown evidence sources: {len(unknown_sources)}")
    with d6:
        status_card("Validation Results", integrity.get("dashboard_runtime_integrity_status", "UNKNOWN"), ", ".join(integrity.get("warnings") or []) or "No validation warnings")
    st.markdown("### Diagnostic Evidence")
    st.dataframe(
        [
            {"Type": "active_incident", **row} for row in active
        ] + [
            {"Type": "open_warning", **row} for row in open_warnings
        ],
        use_container_width=True,
        hide_index=True,
    )


def v3_render_incidents(records):
    active, historical, open_warnings, resolved_warnings, conflicts = v3_incident_lists(records)
    i1, i2, i3, i4, i5 = st.columns(5)
    with i1:
        metric_card("Active Incidents", str(len(active)), "Authoritative blockers, stopped, stale, degraded, conflicts")
    with i2:
        metric_card("Historical Incidents", str(len(historical)), "Tail of daemon_errors.jsonl")
    with i3:
        metric_card("Open Warnings", str(len(open_warnings)), "runtime_warning_resolution_status")
    with i4:
        metric_card("Resolved Warnings", str(len(resolved_warnings)), "runtime_warning_resolution_status")
    with i5:
        metric_card("Conflict Tracker", str(len(conflicts)), "authoritative_runtime_truth.summary.conflict_components")
    st.markdown("### Active Incidents")
    st.dataframe(active or [{"status": "UNKNOWN", "reason": "No active incident artifact rows found"}], use_container_width=True, hide_index=True)
    st.markdown("### Historical Incidents")
    st.dataframe(historical or [{"status": "UNKNOWN", "reason": "daemon_errors.jsonl missing or empty"}], use_container_width=True, hide_index=True)
    st.markdown("### Warning Resolution")
    st.dataframe(
        [{"state": "OPEN", **row} for row in open_warnings] + [{"state": "RESOLVED", **row} for row in resolved_warnings]
        or [{"state": "UNKNOWN", "reason": "No warning resolution rows found"}],
        use_container_width=True,
        hide_index=True,
    )


CONTROL_SYSTEM_SECTIONS = [
    "Command Center",
    "Trading Department",
    "Execution Modes - Classic Mode + HFT Mode",
    "Runtime Department",
    "Intelligence Department",
    "Learning Department",
    "Diagnostics Department",
    "Incident Room",
    "ECHO Department",
    "Control Room",
    "Laboratory",
    "Experience & Knowledge Layer",
    "Timeline / Replay Room",
    "Decision Explainer",
    "Data Lineage",
    "Trust / Proof",
    "Flow Visualizer",
    "Resource / Storage / Pressure",
    "Memory / Knowledge Explorer",
    "Freshness Map",
    "Watchtower",
    "Architecture Department",
    "System Mindmap",
]

CONTROL_SYSTEM_NAV_EMOJIS = {
    "Command Center": "🧭",
    "Trading Department": "📈",
    "Execution Modes - Classic Mode + HFT Mode": "⚙",
    "Runtime Department": "🖥",
    "Intelligence Department": "🧠",
    "Learning Department": "📚",
    "Diagnostics Department": "🩺",
    "Incident Room": "🚨",
    "ECHO Department": "📡",
    "Control Room": "🎛",
    "Laboratory": "🧪",
    "Experience & Knowledge Layer": "🗂",
    "Timeline / Replay Room": "⏱",
    "Decision Explainer": "🔎",
    "Data Lineage": "🧬",
    "Trust / Proof": "🛡",
    "Flow Visualizer": "🔀",
    "Resource / Storage / Pressure": "📊",
    "Memory / Knowledge Explorer": "💾",
    "Freshness Map": "🗺",
    "Watchtower": "🛰",
    "Architecture Department": "🏗",
    "System Mindmap": "🕸",
}

CONTROL_SYSTEM_NAV_GROUPS = [
    (
        "CORE SYSTEM",
        [
            "Command Center",
            "Control Room",
            "Architecture Department",
            "System Mindmap",
        ],
    ),
    (
        "⚙ EXECUTION LAYER",
        [
            "Trading Department",
            "Execution Modes - Classic Mode + HFT Mode",
            "Laboratory",
            "Resource / Storage / Pressure",
        ],
    ),
    (
        "INTELLIGENCE LAYER",
        [
            "Intelligence Department",
            "Learning Department",
            "Experience & Knowledge Layer",
            "Decision Explainer",
            "Memory / Knowledge Explorer",
        ],
    ),
    (
        "OBSERVABILITY",
        [
            "Runtime Department",
            "Diagnostics Department",
            "Incident Room",
            "ECHO Department",
            "Timeline / Replay Room",
            "Data Lineage",
            "Trust / Proof",
            "Flow Visualizer",
            "Freshness Map",
            "Watchtower",
        ],
    ),
]


def control_system_nav_label(section, active_module):
    prefix = CONTROL_SYSTEM_NAV_EMOJIS[section] if section == active_module else "⚪"
    return f"{prefix} {section.upper()}"


def control_system_nav_route(label):
    label_text = str(label or "")
    for section in CONTROL_SYSTEM_SECTIONS:
        if label_text.endswith(section.upper()):
            return section
    return None


def render_control_system_sidebar():
    active_module = st.session_state.get("titan_control_section")
    if active_module not in CONTROL_SYSTEM_SECTIONS:
        active_module = CONTROL_SYSTEM_SECTIONS[0]
        st.session_state["titan_control_section"] = active_module

    for group_index, (_, group_sections) in enumerate(CONTROL_SYSTEM_NAV_GROUPS):
        radio_key = f"titan_control_group_{group_index}"
        stored_route = control_system_nav_route(st.session_state.get(radio_key))
        if stored_route in group_sections and stored_route != active_module:
            active_module = stored_route
            st.session_state["titan_control_section"] = active_module

    for group_index, (_, group_sections) in enumerate(CONTROL_SYSTEM_NAV_GROUPS):
        radio_key = f"titan_control_group_{group_index}"
        stored_route = control_system_nav_route(st.session_state.get(radio_key))
        if stored_route == active_module:
            st.session_state[radio_key] = control_system_nav_label(stored_route, active_module)
        elif radio_key in st.session_state:
            del st.session_state[radio_key]

    selected_module = active_module
    for group_index, (group_title, group_sections) in enumerate(CONTROL_SYSTEM_NAV_GROUPS):
        st.markdown(f"### {group_title}")
        options = [
            control_system_nav_label(section, active_module)
            for section in group_sections
        ]
        option_routes = dict(zip(options, group_sections))
        radio_key = f"titan_control_group_{group_index}"
        if radio_key in st.session_state:
            stored_route = option_routes.get(st.session_state[radio_key])
            if stored_route != active_module:
                del st.session_state[radio_key]
        selected_index = group_sections.index(active_module) if active_module in group_sections else None
        selected_nav_label = st.radio(
            group_title,
            options,
            index=selected_index,
            key=radio_key,
            label_visibility="collapsed",
        )
        if selected_nav_label:
            selected_module = option_routes[selected_nav_label]
            if selected_module != active_module:
                st.session_state["titan_control_section"] = selected_module
                active_module = selected_module

    return selected_module

STATUS_MAP = {
    "FRESH": "🟢",
    "STALE": "🟡",
    "UNKNOWN": "⚪",
    "CONFLICT": "🔴",
    "FAILED": "🔴",
    "DEGRADED": "🟠",
    "PAUSED": "⏸",
    "EVIDENCE_READ": "🟢",
    "STOPPED": "🔴",
    "BLOCKED": "🔴",
}


MODULE_SOURCE_MAP = {
    "Command Center": ["dashboard_truth_consolidation", "authoritative_runtime_truth", "journal_truth_unification"],
    "Trading Department": ["journal_truth_unification", "paper_account", "active_trades", "trade_outcomes", "risk_watchdog"],
    "Execution Modes - Classic Mode + HFT Mode": ["execution_mode", "authoritative_runtime_truth", "hft_runtime_state", "hft_safety_proof", "hft_active_trades", "hft_daily_pnl", "alpha_health"],
    "Runtime Department": ["authoritative_runtime_truth", "titan_runtime_status", "daemon_health", "titan_heartbeat", "worker_health", "scanner_scheduler"],
    "Intelligence Department": ["master_brain_status", "scanner_status", "setup_engine_status", "signal_path_diagnostics", "market_regime_update"],
    "Learning Department": ["evolution_engine", "reinforcement_learning", "outcome_tracker", "memory_health", "strategy_rejection_analysis", "hft_safety_proof"],
    "Diagnostics Department": ["dashboard_runtime_integrity", "runtime_error_summary", "component_freshness_summary", "truth_gate"],
    "Incident Room": ["authoritative_runtime_truth", "daemon_errors", "runtime_warning_resolution", "dashboard_runtime_integrity"],
    "ECHO Department": ["echo_mission", "echo_mission_queue", "echo_recent_report", "echo_files_reviewed", "echo_diagnostics"],
    "Control Room": ["restart_readiness_gate", "runtime_permissions", "runtime_visibility_audit", "truth_gate"],
    "Laboratory": ["lab_activity", "strategy_experiments", "alpha_health", "alpha_lane_candidates", "alpha_shadow_outcome_report", "backtesting_status", "historical_replay"],
    "Experience & Knowledge Layer": ["historical_replay", "memory_health", "memory_lineage", "memory_contribution", "evolution_memory", "hft_safety_proof"],
    "Timeline / Replay Room": ["historical_replay", "backtesting_status", "runtime_reconciliation", "dashboard_live_metrics"],
    "Decision Explainer": ["master_brain_status", "setup_engine_status", "signal_path_diagnostics", "trend_diagnostics", "metric_dependency_graph"],
    "Data Lineage": ["metric_dependency_graph", "canonical_metric_ownership", "dashboard_truth_registry", "memory_lineage"],
    "Trust / Proof": ["truth_gate", "dashboard_truth_registry", "dashboard_runtime_integrity", "hft_safety_proof"],
    "Flow Visualizer": ["metric_dependency_graph", "dashboard_truth_registry", "journal_truth_unification"],
    "Resource / Storage / Pressure": ["dashboard_live_metrics", "runtime_reconciliation", "live_price_monitor", "risk_watchdog", "component_freshness_summary"],
    "Memory / Knowledge Explorer": ["memory_health", "memory_lineage", "memory_contribution", "evolution_memory", "strategy_rejection_analysis", "alpha_memory_summary", "hft_safety_proof"],
    "Freshness Map": ["component_freshness_summary", "dashboard_truth_registry", "authoritative_runtime_truth"],
    "Watchtower": ["dashboard_live_metrics", "runtime_error_summary", "runtime_warning_resolution", "runtime_visibility_audit", "restart_readiness_gate"],
    "Architecture Department": ["titan_body_map_live", "runtime_visibility_audit", "runtime_permissions", "runtime_topology", "echo_architecture_map", "hft_safety_proof", "alpha_health"],
    "System Mindmap": ["titan_body_map_live"],
}


def format_status(status):
    status = str(status or "UNKNOWN").upper()
    return f"{STATUS_MAP.get(status, '⚪')} {status}"


def priority_header(title, status):
    status = str(status or "UNKNOWN").upper()
    st.title(title)
    st.markdown(f"STATE: {STATUS_MAP.get(status, '⚪')} {status}")


def compact_kpi_card(label, value=None, meta=None, status=None):
    status_text = str(status or value or "").upper()
    accent = "#00ffc8" if status_text in {"FRESH", "CONNECTED", "ONLINE", "ACTIVE", "SUCCESS", "TRUE", "SAFE"} else "#253044"
    display_value = "" if value in (None, "") else str(value)
    display_meta = "" if meta in (None, "") else str(meta)
    st.markdown(
        f"""
        <div class="terminal-kpi" style="border-left-color: {accent};">
            <div class="terminal-kpi-label">{label}</div>
            <div class="terminal-kpi-value">{display_value}</div>
            <div class="terminal-kpi-meta">{display_meta}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_row(metrics, max_items=6):
    metrics = list(metrics or [])[:max(1, min(max_items, 6))]
    if not metrics:
        return
    cols = st.columns(len(metrics))
    for i, metric in enumerate(metrics):
        with cols[i]:
            value = str(metric.get("state", metric.get("value", "UNKNOWN")) or "UNKNOWN").upper()
            compact_kpi_card(metric["label"], f"{STATUS_MAP.get(value, '⚪')} {value}", metric.get("delta"), value)


def titan_card(title, status=None, value=None, content=None):
    status_text = str(status).upper() if status not in (None, "") else ""
    display_value = f"{STATUS_MAP.get(status_text, '⚪')} {status_text}" if status_text else ("" if value in (None, "") else str(value))
    display_meta = content if content not in (None, "", [], {}) else ""
    compact_kpi_card(title, display_value, display_meta, status_text)


def v3_status_rank(freshness_values):
    values = {str(value or "UNKNOWN").upper() for value in freshness_values}
    if "CONFLICT" in values:
        return "CONFLICT"
    if "STALE" in values:
        return "STALE"
    if "UNKNOWN" in values:
        return "UNKNOWN"
    if "FRESH" in values:
        return "FRESH"
    return "UNKNOWN"


def v3_module_freshness(records, source_names):
    return v3_status_rank(records.get(name, {}).get("freshness") for name in source_names)


def v3_module_status(records, source_names):
    statuses = {str(records.get(name, {}).get("status") or "UNKNOWN").upper() for name in source_names}
    for problem in ("CONFLICT", "FAIL", "FAILED", "BLOCKED", "STOPPED", "DEGRADED"):
        if problem in statuses:
            return problem
    if statuses == {"UNKNOWN"}:
        return "UNKNOWN"
    return "EVIDENCE_READ"


def v3_evidence_panel(records, source_names):
    rows = []
    for name in source_names[:5]:
        record = records.get(name, {})
        if not record or not record.get("exists"):
            continue
        timestamp = record.get("timestamp")
        rows.append({
            "Source": name,
            "Source File": record.get("path"),
            "Timestamp": timestamp.strftime("%d %b %Y %H:%M:%S IST") if timestamp else None,
            "Freshness": record.get("freshness"),
            "Confidence": "EVIDENCE_READ",
        })
    with st.expander("EVIDENCE LAYER (CLICK TO EXPAND)", expanded=False):
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)


def v3_live_activity_panel(records, source_names):
    activity_log = []
    for event in get_activity_stream():
        timestamp = parse_dt(event.get("timestamp"))
        activity_log.append({
            "time": timestamp.strftime("%H:%M:%S") if timestamp else "",
            "engine": event.get("engine") or "",
            "action": event.get("action") or "",
            "status": format_status(event.get("status")) if event.get("status") not in (None, "") else "",
        })
    lines = [
        f"▶ {event['time']} | {event['engine']} | {event['action']} | {event['status']}"
        for event in activity_log[-10:]
    ]
    st.markdown(
        f"""
        <div class="terminal-panel">
            <div class="terminal-panel-title">ACTIVITY STREAM</div>
            <div style="font-size: 11px; line-height: 1.35; font-weight: 700; color: #dbeafe;">
                {"<br>".join(lines)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def system_flow_snapshot():
    flow_state = TITAN_STATE.get("flow", {})
    stages = flow_state.get("stages") if isinstance(flow_state, dict) else []
    active_stage = str(flow_state.get("active") or "").upper() if isinstance(flow_state, dict) else ""
    stages = [stage for stage in stages if stage in FLOW_STAGES]
    labels = {
        "INPUT": "INPUT",
        "INTELLIGENCE": "INTEL",
        "DECISION": "DECISION",
        "RISK": "RISK",
        "EXECUTION": "EXEC",
        "FEEDBACK": "FEEDBACK",
    }
    rendered = []
    for stage in stages[:6]:
        active_class = " active" if stage == active_stage else ""
        rendered.append(f'<span class="flow-chip{active_class}">{labels.get(stage, stage)}</span>')
    st.markdown(
        f"""
        <div class="terminal-panel mini-flow-strip">
            {"<span class='flow-arrow'>→</span>".join(rendered)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def v3_exception_panel(records):
    active, historical, open_warnings, resolved_warnings, conflicts = v3_incident_lists(records)
    critical = [
        item for item in active
        if str(item.get("type", "")).lower() in {"restart_blockers", "conflict_components", "dashboard_integrity_warning"}
    ]
    with st.expander("ACTION OUTPUT", expanded=False):
        if critical:
            st.error(f"{len(critical)} critical evidence-backed exceptions")
            st.dataframe(critical, use_container_width=True, hide_index=True)
        elif open_warnings:
            st.warning(f"{len(open_warnings)} open warning records")
            st.dataframe(open_warnings[:8], use_container_width=True, hide_index=True)
        else:
            st.write(f"STATE: {format_status('UNKNOWN')}")
            st.write("No critical exception rows found in current evidence.")


def v4_text(value, default="UNKNOWN"):
    if value in (None, "", [], {}):
        return default
    return str(value)


def v4_clip(value, limit=110):
    value = v4_text(value)
    return value if len(value) <= limit else f"{value[:limit - 3]}..."


def v4_status_class(status):
    status = str(status or "UNKNOWN").upper()
    if status in {"LIVE", "ACTIVE", "RUNNING", "HEALTHY", "CLEAN", "PASS", "PASSED", "ALLOW", "SAFE", "TRUE", "FRESH", "EVIDENCE_READ", "CONNECTED", "ONLINE", "SUCCESS"}:
        return "good"
    if status in {"STALE", "WAITING", "PAUSED", "WARNING", "WARN", "DEGRADED", "RESEARCH_MODE", "WEEKEND_MODE"}:
        return "warn"
    if status in {"STOPPED", "BLOCKED", "FAIL", "FAILED", "CONFLICT", "FALSE", "UNSAFE", "ERROR", "CRITICAL"}:
        return "bad"
    return "unknown"


def v4_status_text_class(status):
    state_class = v4_status_class(status)
    if state_class == "good":
        return "v4-status-good"
    if state_class == "warn":
        return "v4-status-warn"
    if state_class == "bad":
        return "v4-status-bad"
    return "v4-status-unknown"


def v4_status_pill(status):
    status = v4_text(status)
    return f"<span class='v4-status-pill {v4_status_class(status)}'>{escape(status.upper())}</span>"


def v4_age_label_from_seconds(age_seconds):
    if age_seconds is None:
        return "UNKNOWN"
    try:
        seconds = max(0, int(float(age_seconds)))
    except Exception:
        return "UNKNOWN"
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


def v4_latest_evidence_record(records):
    candidates = [record for record in records.values() if record.get("timestamp")]
    if not candidates:
        return None
    return max(candidates, key=lambda record: record.get("timestamp"))


BLUEPRINT_STATUS_VALUES = {
    "FRESH",
    "STALE",
    "UNKNOWN",
    "CONFLICT",
    "FAILED",
    "DEGRADED",
    "PAUSED",
    "BLOCKED",
}


def blueprint_status(status, freshness=None, exists=True):
    status_text = str(status or "").upper()
    freshness_text = str(freshness or "").upper()
    if status_text in {"CONFLICT"}:
        return "CONFLICT"
    if status_text in {"FAILED", "FAIL", "ERROR", "CRITICAL"}:
        return "FAILED"
    if status_text in {"BLOCKED"}:
        return "BLOCKED"
    if status_text in {"PAUSED"}:
        return "PAUSED"
    if status_text in {"DEGRADED", "WARNING", "WARN"}:
        return "DEGRADED"
    if not exists or status_text in {"", "UNKNOWN", "NONE", "NULL"}:
        return "UNKNOWN"
    if freshness_text == "STALE":
        return "STALE"
    if freshness_text == "UNKNOWN":
        return "UNKNOWN"
    if freshness_text == "FRESH":
        return "FRESH"
    return status_text if status_text in BLUEPRINT_STATUS_VALUES else "UNKNOWN"


def evidence_metadata(record):
    record = record if isinstance(record, dict) else {}
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    timestamp = record.get("timestamp")
    return {
        "source": record.get("path") or payload.get("source_file") or payload.get("source") or "UNKNOWN",
        "writer": payload.get("writer") or payload.get("written_by") or payload.get("owner") or payload.get("producer") or "UNKNOWN",
        "timestamp": timestamp.strftime("%d %b %Y %H:%M:%S IST") if timestamp else "UNKNOWN",
        "age": v4_age_label_from_seconds(record.get("age_seconds")),
        "freshness": record.get("freshness") or "UNKNOWN",
        "confidence": payload.get("confidence") or payload.get("confidence_score") or payload.get("trust_confidence") or "UNKNOWN",
    }


def visible_value(label, value, record=None, *, status=None, source_label=None):
    meta = evidence_metadata(record)
    state = blueprint_status(status or (record or {}).get("status"), meta["freshness"], bool((record or {}).get("exists", True)))
    return {
        "label": label,
        "value": v4_text(value),
        "status": state,
        "source_label": source_label or meta["source"],
        "proof": meta,
    }


def execution_mode_record(records):
    record = records.get("execution_mode", {}) if isinstance(records, dict) else {}
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    mode = str(payload.get("active_execution_mode") or "").upper()
    if mode not in {"CLASSIC", "HFT"}:
        mode = "UNKNOWN"
    status = "UNKNOWN" if mode == "UNKNOWN" else blueprint_status(record.get("status"), record.get("freshness"), record.get("exists"))
    if payload.get("switch_in_progress") is True:
        status = "PAUSED"
    return visible_value(
        "Active Mode",
        mode,
        record,
        status=status,
        source_label="data/runtime/execution_mode.json",
    )


def v4_kpi_html(label, value, meta="", status=None):
    status = status or value
    return f"""
    <div class="v4-kpi-card">
        <div class="v4-kpi-label">{escape(v4_text(label, ""))}</div>
        <div class="v4-kpi-value {v4_status_text_class(status)}">{escape(v4_text(value))}</div>
        <div class="v4-kpi-meta">{v4_status_pill(status)}<span style="margin-left:8px;">{escape(v4_clip(meta, 72))}</span></div>
        <svg class="v4-sparkline" viewBox="0 0 160 28" preserveAspectRatio="none" aria-hidden="true">
            <polyline points="0,22 22,18 44,20 66,11 88,15 110,7 132,12 160,5" fill="none" stroke="rgba(96,165,250,0.78)" stroke-width="2"/>
            <polyline points="0,25 160,25" fill="none" stroke="rgba(148,163,184,0.18)" stroke-width="1"/>
        </svg>
    </div>
    """


def v4_panel_header(title, count=None):
    count_html = "" if count is None else f"<span class='v4-count-pill'>{escape(str(count))}</span>"
    return f"""
    <div class="v4-panel-title-row">
        <div class="v4-panel-title">{escape(title)}</div>
        {count_html}
    </div>
    """


def v4_list_item(name, status, meta):
    return f"""
    <div class="v4-list-item">
        <div class="v4-list-top">
            <div class="v4-list-name">{escape(v4_clip(name, 70))}</div>
            {v4_status_pill(status)}
        </div>
        <div class="v4-list-meta">{escape(v4_clip(meta, 140))}</div>
    </div>
    """


def v4_mini_metric(label, value, status=None):
    return f"""
    <div class="v4-mini-metric">
        <div class="v4-mini-label">{escape(v4_text(label, ""))}</div>
        <div class="v4-mini-value {v4_status_text_class(status or value)}">{escape(v4_clip(value, 44))}</div>
    </div>
    """


def v4_node(label, status, meta):
    state_class = v4_status_class(status)
    return f"""
    <div class="v4-node {state_class}">
        <div class="v4-node-name">{escape(v4_text(label, ""))}</div>
        <div class="v4-node-state {v4_status_text_class(status)}">{escape(v4_text(status).upper())}</div>
        <div class="v4-node-meta">{escape(v4_clip(meta, 96))}</div>
    </div>
    """


def v4_value_cards_html(items):
    cards = [
        v4_kpi_html(item["label"], item["value"], item.get("source_label", ""), item["status"])
        for item in list(items or [])
    ]
    return f"<div class='v4-kpi-grid'>{''.join(cards)}</div>"


def v4_proof_rows(items):
    rows = []
    for item in list(items or []):
        proof = item.get("proof", {}) if isinstance(item, dict) else {}
        rows.append({
            "Label": item.get("label"),
            "Value": item.get("value"),
            "Status": item.get("status"),
            "Source": proof.get("source"),
            "Writer": proof.get("writer"),
            "Timestamp": proof.get("timestamp"),
            "Age": proof.get("age"),
            "Freshness": proof.get("freshness"),
            "Confidence": proof.get("confidence"),
        })
    return rows


def render_v4_proof_drawer(title, items, extra_sections=None):
    with st.expander(title, expanded=False):
        rows = v4_proof_rows(items)
        st.markdown("#### Visible Value Proof")
        st.dataframe(rows or [{"Status": "UNKNOWN", "Reason": "No visible proof rows found"}], use_container_width=True, hide_index=True)
        for section_title, section_rows in list(extra_sections or []):
            st.markdown(f"#### {section_title}")
            st.dataframe(section_rows or [{"Status": "UNKNOWN", "Reason": "No evidence rows found"}], use_container_width=True, hide_index=True)


def record_value(records, source_name, label, value=None, *, status=None, source_label=None):
    record = records.get(source_name, {}) if isinstance(records, dict) else {}
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    if value is None:
        value = (
            payload.get("value")
            or payload.get("status")
            or payload.get("state")
            or record.get("status")
            or "UNKNOWN"
        )
    return visible_value(label, value, record, status=status or record.get("status"), source_label=source_label or source_name)


def component_value(records, component_name, label=None):
    component = v3_component(records, component_name)
    status = component.get("status") or "UNKNOWN"
    return visible_value(
        label or component_name.replace("_", " ").title(),
        status,
        records.get("authoritative_runtime_truth"),
        status=status,
        source_label=f"authoritative_runtime_truth.components.{component_name}",
    )


def payload_first(payload, keys, default="UNKNOWN"):
    payload = payload if isinstance(payload, dict) else {}
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def source_rows(records, source_names):
    rows = []
    for name in list(source_names or []):
        record = records.get(name, {}) if isinstance(records, dict) else {}
        rows.append({
            "Source": name,
            "Path": record.get("path"),
            "Status": record.get("status"),
            "Freshness": record.get("freshness"),
            "Age": v4_age_label_from_seconds(record.get("age_seconds")),
            "Exists": record.get("exists"),
        })
    return rows


def hft_isolation_value(records):
    proof_record = records.get("hft_safety_proof", {}) if isinstance(records, dict) else {}
    payload = proof_record.get("payload") if isinstance(proof_record.get("payload"), dict) else {}
    isolation_keys = (
        "hft_isolated_from_titan_memory",
        "memory_isolated",
        "learning_isolated",
        "evolution_isolated",
        "master_brain_isolated",
        "classic_journal_isolated",
    )
    proven = [payload.get(key) for key in isolation_keys if key in payload]
    if proven and all(value is True for value in proven):
        value = "PROVEN"
        status = proof_record.get("status")
    elif proven and any(value is False for value in proven):
        value = "CONFLICT"
        status = "CONFLICT"
    else:
        value = "UNKNOWN"
        status = "UNKNOWN"
    return visible_value("HFT Learning Isolation", value, proof_record, status=status, source_label="hft_safety_proof")


def dependency_edge_rows(records):
    edges = v3_dependency_edges(records)
    if not edges:
        return []
    rows = []
    for edge in edges:
        rows.append({
            "Source": edge.get("Source"),
            "Consumer": edge.get("Consumer"),
            "Flow Direction": edge.get("Flow Direction"),
            "Dependency Type": edge.get("Dependency Type"),
            "Payload Time": "UNKNOWN",
            "Delay": "UNKNOWN",
            "Events/Sec": "UNKNOWN",
            "Status": records.get("metric_dependency_graph", {}).get("status") or "UNKNOWN",
            "Freshness": records.get("metric_dependency_graph", {}).get("freshness") or "UNKNOWN",
            "Evidence Path": edge.get("Evidence Path"),
        })
    return rows


def freshness_counts(records):
    counts = {"FRESH": 0, "STALE": 0, "UNKNOWN": 0, "CONFLICT": 0}
    for record in records.values():
        state = blueprint_status(record.get("status"), record.get("freshness"), record.get("exists"))
        if state == "CONFLICT":
            counts["CONFLICT"] += 1
        elif state == "STALE":
            counts["STALE"] += 1
        elif state == "FRESH":
            counts["FRESH"] += 1
        else:
            counts["UNKNOWN"] += 1
    return counts


def freshness_detail_rows(records):
    rows = []
    for name, record in sorted(records.items(), key=lambda item: float(item[1].get("age_seconds") or -1), reverse=True):
        rows.append({
            "Source": name,
            "Path": record.get("path"),
            "Status": blueprint_status(record.get("status"), record.get("freshness"), record.get("exists")),
            "Freshness": record.get("freshness") or "UNKNOWN",
            "Age": v4_age_label_from_seconds(record.get("age_seconds")),
            "Exists": record.get("exists"),
        })
    return rows


def watchtower_value(records, label, key_options):
    record = records.get("dashboard_live_metrics", {})
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    value = payload_first(payload, key_options, "UNKNOWN")
    status = "UNKNOWN" if value == "UNKNOWN" else record.get("status")
    return visible_value(label, value, record, status=status, source_label="dashboard_live_metrics")


def live_metric_value(records, label, key_options):
    return watchtower_value(records, label, key_options)


def body_map_payload(records):
    payload = records.get("titan_body_map_live", {}).get("payload", {})
    return payload if isinstance(payload, dict) else {}


def list_count_from_payload(payload, keys):
    payload = payload if isinstance(payload, dict) else {}
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            return len(value)
        if isinstance(value, (int, float)):
            return int(value)
        if value not in (None, "", [], {}):
            return value
    return "UNKNOWN"


def hft_memory_inclusion_value(records):
    proof_record = records.get("hft_safety_proof", {}) if isinstance(records, dict) else {}
    payload = proof_record.get("payload") if isinstance(proof_record.get("payload"), dict) else {}
    allow_keys = (
        "hft_allowed_to_feed_titan_learning",
        "hft_memory_feed_allowed",
        "hft_learning_feed_allowed",
    )
    values = [payload.get(key) for key in allow_keys if key in payload]
    if values and any(value is True for value in values):
        value = "ALLOWED"
        status = proof_record.get("status")
    elif values and all(value is False for value in values):
        value = "ISOLATED"
        status = proof_record.get("status")
    else:
        value = "UNKNOWN"
        status = "UNKNOWN"
    return visible_value("HFT Memory Feed", value, proof_record, status=status, source_label="hft_safety_proof")


def render_tv_pulse():
    st.markdown("<div class='titan-tv-pulse'></div>", unsafe_allow_html=True)


def body_map_nodes(records):
    payload = body_map_payload(records)
    nodes = payload.get("nodes")
    if isinstance(nodes, dict):
        converted = []
        for name, node in nodes.items():
            if isinstance(node, dict):
                item = dict(node)
                item.setdefault("name", name)
                converted.append(item)
            else:
                converted.append({"name": name, "status": node})
        return converted
    if isinstance(nodes, list):
        return [node for node in nodes if isinstance(node, dict)]
    return []


def body_map_edges(records):
    payload = body_map_payload(records)
    edges = payload.get("edges")
    if isinstance(edges, list):
        return [edge for edge in edges if isinstance(edge, dict)]
    return []


def mindmap_status_for_node(node):
    status = str(node.get("status") or node.get("state") or node.get("health") or "UNKNOWN").upper()
    freshness = str(node.get("freshness") or "").upper()
    return blueprint_status(status, freshness, True)


def mindmap_node_html(name, status, meta="", core=False):
    state_class = v4_status_class(status)
    core_class = " core" if core else ""
    return f"""
    <div class="mindmap-node {state_class}{core_class}">
        <div class="mindmap-name">{escape(v4_clip(name, 42))}</div>
        {v4_status_pill(status)}
        <div class="mindmap-meta">{escape(v4_clip(meta, 92))}</div>
    </div>
    """


def render_v4_sidebar(records=None):
    active_module = st.session_state.get("titan_control_section")
    if active_module not in CONTROL_SYSTEM_SECTIONS:
        active_module = CONTROL_SYSTEM_SECTIONS[0]

    st.markdown(
        """
        <div class="v4-sidebar-brand">
            <div class="v4-logo-row">
                <div class="v4-logo-mark">T</div>
                <div>
                    <div class="v4-brand-title">TITAN</div>
                    <div class="v4-brand-sub">Command System</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    options = [f"{index:02d} {section.upper()}" for index, section in enumerate(CONTROL_SYSTEM_SECTIONS, start=1)]
    section_by_option = dict(zip(options, CONTROL_SYSTEM_SECTIONS))
    selected_index = CONTROL_SYSTEM_SECTIONS.index(active_module)
    selected_label = st.radio(
        "Navigation",
        options,
        index=selected_index,
        key="titan_v4_sidebar_nav",
        label_visibility="collapsed",
    )
    selected_module = section_by_option.get(selected_label, active_module)
    st.session_state["titan_control_section"] = selected_module

    latest = v4_latest_evidence_record(records or {}) if isinstance(records, dict) else None
    latest_age = v4_age_label_from_seconds(latest.get("age_seconds")) if latest else "UNKNOWN"
    st.markdown(
        f"""
        <div class="v4-sidebar-block">
            <div class="v4-sidebar-block-title">Quick Actions</div>
            <div class="v4-action-row"><span>Refresh</span><span>{AUTO_REFRESH_SECONDS}s</span></div>
            <div class="v4-action-row"><span>Auto Refresh</span><span>ON</span></div>
            <div class="v4-action-row"><span>Market Clock</span><span>{escape(v3_market_clock())}</span></div>
        </div>
        <div class="v4-sidebar-block">
            <div class="v4-sidebar-block-title">System Version</div>
            <div class="v4-version-row"><span>Dashboard</span><span>V4 UI</span></div>
            <div class="v4-version-row"><span>Truth Sources</span><span>{len(V3_TRUTH_SOURCES)}</span></div>
            <div class="v4-version-row"><span>Last Evidence</span><span>{escape(latest_age)}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return selected_module


def render_v4_topbar(records, selected_module="Command Center"):
    latest = v4_latest_evidence_record(records)
    latest_age = v4_age_label_from_seconds(latest.get("age_seconds")) if latest else "UNKNOWN"
    latest_status = blueprint_status(latest.get("status") if latest else None, latest.get("freshness") if latest else None, bool(latest))
    mode = execution_mode_record(records)
    title = "COMMAND CENTER" if selected_module == "Command Center" else selected_module.upper()
    subtitle = "Live Overview" if selected_module == "Command Center" else "Evidence Overview"
    st.markdown(
        f"""
        <div class="v4-topbar">
            <div>
                <div class="v4-page-title">{escape(title)}</div>
                <div class="v4-page-subtitle">{escape(subtitle)}</div>
            </div>
            <div class="v4-top-stat">
                <div class="v4-top-label">Active Mode</div>
                <div class="v4-top-value">{escape(mode["value"])} {v4_status_pill(mode["status"])}</div>
            </div>
            <div class="v4-top-stat">
                <div class="v4-top-label">Last Verified</div>
                <div class="v4-top-value">{escape(latest_age)} {v4_status_pill(latest_status)}</div>
            </div>
            <div class="v4-top-stat">
                <div class="v4-top-label">Refresh</div>
                <div class="v4-top-value"><span class="v4-refresh-dot"></span>Auto Refresh ON</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_v4_kpi_cards(records):
    consolidation = records["dashboard_truth_consolidation"]["payload"]
    trust_value, trust_sub = v3_trust_score(records)
    restart_record = records.get("restart_readiness_gate", {})
    restart_payload = restart_record.get("payload") if isinstance(restart_record.get("payload"), dict) else {}
    safe_to_start = v3_first_present(
        restart_payload,
        ("safe_to_start", "restart_safe", "can_start", "status", "state", "final_status"),
        default="UNKNOWN",
    )
    system_state = consolidation.get("dashboard_overall_status") if isinstance(consolidation, dict) else "UNKNOWN"
    latest = v4_latest_evidence_record(records)
    evidence_age = v4_age_label_from_seconds(latest.get("age_seconds")) if latest else "UNKNOWN"
    latest_source = latest.get("name") if latest else "UNKNOWN"
    values = [
        visible_value("Trust Score", trust_value, records.get("authoritative_runtime_truth"), status=records.get("authoritative_runtime_truth", {}).get("status"), source_label="authoritative_runtime_truth"),
        visible_value("System State", system_state, records.get("dashboard_truth_consolidation"), status=system_state, source_label="dashboard_truth_consolidation"),
        visible_value("Safe To Start", safe_to_start, restart_record, status=safe_to_start, source_label="restart_readiness_gate"),
        visible_value("Evidence Age", evidence_age, latest, status=latest.get("freshness") if latest else "UNKNOWN", source_label=latest_source),
        visible_value("Data Source", f"{len(V3_TRUTH_SOURCES)} sources", latest, status=latest.get("freshness") if latest else "UNKNOWN", source_label=latest_source),
    ]
    st.session_state["v4_command_center_kpi_proof"] = values
    cards = [v4_kpi_html(item["label"], item["value"], item["source_label"], item["status"]) for item in values]
    st.markdown(f"<div class='v4-kpi-grid'>{''.join(cards)}</div>", unsafe_allow_html=True)


def render_v4_datetime_card():
    components.html(
        """
        <div class="dt-card">
            <div>
                <div class="dt-label">Date & Time</div>
                <div class="dt-date" id="titan-ist-date">--</div>
                <div class="dt-sub">Asia/Kolkata / India</div>
            </div>
            <div class="dt-time" id="titan-ist-time">--:--:--</div>
        </div>
        <style>
            body { margin: 0; background: transparent; font-family: Arial, sans-serif; }
            .dt-card {
                height: 118px;
                box-sizing: border-box;
                border: 1px solid rgba(96,165,250,0.18);
                border-radius: 14px;
                background: linear-gradient(180deg, #0e1a2b 0%, #0a1424 100%);
                padding: 20px 22px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                color: #f8fafc;
                overflow: hidden;
            }
            .dt-label {
                color: #93a4bb;
                font-size: 12px;
                font-weight: 950;
                text-transform: uppercase;
                margin-bottom: 10px;
            }
            .dt-date {
                color: #f8fafc;
                font-size: 24px;
                font-weight: 950;
                line-height: 1.05;
            }
            .dt-sub {
                color: #7f91aa;
                font-size: 12px;
                font-weight: 760;
                margin-top: 9px;
            }
            .dt-time {
                color: #38bdf8;
                font-size: 42px;
                font-weight: 950;
                line-height: 1;
                font-variant-numeric: tabular-nums;
                text-shadow: 0 0 22px rgba(56,189,248,0.22);
            }
        </style>
        <script>
            function updateTitanClock() {
                const now = new Date();
                const dateFmt = new Intl.DateTimeFormat('en-IN', {
                    timeZone: 'Asia/Kolkata',
                    weekday: 'long',
                    year: 'numeric',
                    month: 'long',
                    day: '2-digit'
                });
                const timeFmt = new Intl.DateTimeFormat('en-GB', {
                    timeZone: 'Asia/Kolkata',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: false
                });
                document.getElementById('titan-ist-date').textContent = dateFmt.format(now);
                document.getElementById('titan-ist-time').textContent = timeFmt.format(now);
            }
            updateTitanClock();
            setInterval(updateTitanClock, 1000);
        </script>
        """,
        height=126,
    )


def render_v4_incidents(records):
    active, historical, open_warnings, resolved_warnings, conflicts = v3_incident_lists(records)
    rows = []
    for item in active[:5]:
        rows.append(v4_list_item(item.get("type") or "Incident", "WARNING", f"{item.get('item')} | {item.get('source')}"))
    for item in open_warnings[: max(0, 5 - len(rows))]:
        rows.append(v4_list_item("Open Warning", "WARNING", f"{item.get('warning')} | {item.get('source')}"))
    if not rows:
        rows.append(v4_list_item("No active incidents", "CLEAN", "No active incident rows found in current evidence"))
    st.markdown(
        f"""
        <div class="v4-panel">
            {v4_panel_header("Active Incidents", len(active) + len(open_warnings))}
            <div class="v4-list">{''.join(rows)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_v4_health_summary(records):
    components = [
        ("Daemon", v3_component(records, "daemon")),
        ("Workers", v3_component(records, "workers")),
        ("Scheduler", v3_component(records, "scheduler")),
        ("Scanner", v3_component(records, "scanner")),
        ("Setup Engine", v3_component(records, "setup_engine")),
        ("Master Brain", v3_component(records, "master_brain")),
    ]
    rows = [
        v4_list_item(label, record.get("status"), record.get("reason") or record.get("source_file") or "authoritative_runtime_truth")
        for label, record in components
    ]
    st.markdown(
        f"""
        <div class="v4-panel">
            {v4_panel_header("System Health Summary", len(components))}
            <div class="v4-list">{''.join(rows)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_v4_runtime_overview(records):
    daemon = v3_component(records, "daemon")
    workers = v3_component(records, "workers")
    scheduler = v3_component(records, "scheduler")
    runtime_truth = records.get("authoritative_runtime_truth", {})
    mode = v3_active_mode(records)
    latest = v4_latest_evidence_record(records)
    latest_age = v4_age_label_from_seconds(latest.get("age_seconds")) if latest else "UNKNOWN"
    metrics = [
        v4_mini_metric("Mode", mode, mode),
        v4_mini_metric("Daemon", daemon.get("status"), daemon.get("status")),
        v4_mini_metric("Workers", workers.get("status"), workers.get("status")),
        v4_mini_metric("Scheduler", scheduler.get("status"), scheduler.get("status")),
        v4_mini_metric("Runtime Truth", runtime_truth.get("status"), runtime_truth.get("status")),
        v4_mini_metric("Evidence Age", latest_age, latest.get("freshness") if latest else "UNKNOWN"),
    ]
    st.markdown(
        f"""
        <div class="v4-panel">
            {v4_panel_header("Runtime Overview")}
            <div class="v4-mini-metrics">{''.join(metrics)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_v4_trading_overview(records):
    open_rows = v3_open_trade_rows()
    closed_rows = v3_closed_trade_rows()
    consolidation = records["dashboard_truth_consolidation"]["payload"]
    open_count = "UNKNOWN" if open_rows is None else len(open_rows)
    if isinstance(consolidation, dict) and consolidation.get("active_trade_count") is not None:
        open_count = int(consolidation.get("active_trade_count"))
    closed_count = "UNKNOWN" if closed_rows is None else len(closed_rows)
    pnl_value = v3_account_value(records, ("daily_pnl", "pnl", "realized_pnl", "closed_pnl"))
    account_value = v3_account_value(records, ("account_balance", "balance", "equity"))
    exposure = v3_open_exposure(open_rows)
    risk_record = records.get("risk_watchdog", {})
    metrics = [
        v4_mini_metric("Account", account_value, records.get("paper_account", {}).get("status")),
        v4_mini_metric("Open Trades", open_count, "EVIDENCE_READ" if open_count != "UNKNOWN" else "UNKNOWN"),
        v4_mini_metric("Closed Trades", closed_count, "EVIDENCE_READ" if closed_count != "UNKNOWN" else "UNKNOWN"),
        v4_mini_metric("PnL", pnl_value, "UNKNOWN" if pnl_value == "UNKNOWN" else "EVIDENCE_READ"),
        v4_mini_metric("Exposure", exposure, "UNKNOWN" if exposure == "UNKNOWN" else "EVIDENCE_READ"),
        v4_mini_metric("Risk", risk_record.get("status"), risk_record.get("status")),
    ]
    st.markdown(
        f"""
        <div class="v4-panel">
            {v4_panel_header("Trading Overview")}
            <div class="v4-mini-metrics">{''.join(metrics)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_v4_system_mindmap(records):
    daemon = v3_component(records, "daemon")
    scanner = v3_component(records, "scanner")
    setup_engine = v3_component(records, "setup_engine")
    master_brain = v3_component(records, "master_brain")
    paper_engine = v3_component(records, "paper_engine")
    nodes = {
        "top": [
            ("Command Core", records.get("dashboard_truth_consolidation", {}).get("status"), records.get("dashboard_truth_consolidation", {}).get("path")),
        ],
        "mid": [
            ("Runtime Layer", v3_layer_status(records, V3_D03_LAYER_SOURCES["Runtime Layer"]), v3_layer_dependencies(records, V3_D03_LAYER_SOURCES["Runtime Layer"])),
            ("Intelligence Layer", v3_layer_status(records, V3_D03_LAYER_SOURCES["Scanner Layer"] + V3_D03_LAYER_SOURCES["Setup Layer"] + V3_D03_LAYER_SOURCES["Master Brain Layer"]), "Scanner + setup + Master Brain evidence"),
            ("Trading Layer", v3_layer_status(records, V3_D03_LAYER_SOURCES["Trading Layer"]), v3_layer_dependencies(records, V3_D03_LAYER_SOURCES["Trading Layer"])),
        ],
        "base": [
            ("Daemon", daemon.get("status"), daemon.get("reason") or "authoritative_runtime_truth"),
            ("Scanner", scanner.get("status"), scanner.get("reason") or "authoritative_runtime_truth"),
            ("Setup Engine", setup_engine.get("status"), setup_engine.get("reason") or "authoritative_runtime_truth"),
            ("Master Brain", master_brain.get("status"), master_brain.get("reason") or "authoritative_runtime_truth"),
            ("Paper Engine", paper_engine.get("status"), paper_engine.get("reason") or "authoritative_runtime_truth"),
        ],
    }
    st.markdown(
        f"""
        <div class="v4-mindmap">
            {v4_panel_header("System Mindmap / Pyramid View")}
            <div class="v4-pyramid">
                <div class="v4-pyramid-row top">{''.join(v4_node(*node) for node in nodes["top"])}</div>
                <div class="v4-pyramid-row mid">{''.join(v4_node(*node) for node in nodes["mid"])}</div>
                <div class="v4-pyramid-row base">{''.join(v4_node(*node) for node in nodes["base"])}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_v4_command_center_debug(records):
    active, historical, open_warnings, resolved_warnings, conflicts = v3_incident_lists(records)
    open_rows = v3_open_trade_rows()
    closed_rows = v3_closed_trade_rows()
    consolidation = records["dashboard_truth_consolidation"]["payload"]
    open_count = "UNKNOWN" if open_rows is None else len(open_rows)
    if isinstance(consolidation, dict) and consolidation.get("active_trade_count") is not None:
        open_count = int(consolidation.get("active_trade_count"))
    closed_count = "UNKNOWN" if closed_rows is None else len(closed_rows)
    pnl_value = v3_account_value(records, ("daily_pnl", "pnl", "realized_pnl", "closed_pnl"))
    account_value = v3_account_value(records, ("account_balance", "balance", "equity"))
    exposure = v3_open_exposure(open_rows)
    risk_record = records.get("risk_watchdog", {})

    with st.expander("Proof Details / Raw Debug", expanded=False):
        proof_rows = []
        for item in st.session_state.get("v4_command_center_kpi_proof", []):
            proof = item.get("proof", {})
            proof_rows.append({
                "Label": item.get("label"),
                "Value": item.get("value"),
                "Status": item.get("status"),
                "Source": proof.get("source"),
                "Writer": proof.get("writer"),
                "Timestamp": proof.get("timestamp"),
                "Age": proof.get("age"),
                "Freshness": proof.get("freshness"),
                "Confidence": proof.get("confidence"),
            })
        st.markdown("#### Visible KPI Proof")
        st.dataframe(proof_rows or [{"status": "UNKNOWN", "reason": "No visible KPI proof rows found"}], use_container_width=True, hide_index=True)

        st.markdown("#### Incidents")
        st.dataframe(active or [{"status": "UNKNOWN", "reason": "No active incident artifact rows found"}], use_container_width=True, hide_index=True)
        st.dataframe(
            [{"state": "OPEN", **row} for row in open_warnings] + [{"state": "RESOLVED", **row} for row in resolved_warnings]
            or [{"state": "UNKNOWN", "reason": "No warning resolution rows found"}],
            use_container_width=True,
            hide_index=True,
        )
        st.dataframe(historical or [{"status": "UNKNOWN", "reason": "daemon_errors.jsonl missing or empty"}], use_container_width=True, hide_index=True)
        st.dataframe(conflicts or [{"status": "UNKNOWN", "reason": "No conflict rows found"}], use_container_width=True, hide_index=True)

        st.markdown("#### Runtime")
        runtime_rows = []
        for name in MODULE_SOURCE_MAP["Runtime Department"]:
            record = records.get(name, {})
            runtime_rows.append({
                "Source": name,
                "Status": record.get("status"),
                "Freshness": record.get("freshness"),
                "AgeSeconds": record.get("age_seconds"),
                "Path": record.get("path"),
            })
        st.dataframe(runtime_rows, use_container_width=True, hide_index=True)

        st.markdown("#### Trading")
        trading_rows = [
            {"Widget": "Account Status", "Current State": records["paper_account"].get("status"), "Value": account_value, "Evidence Source": records["paper_account"].get("path"), "Freshness": records["paper_account"].get("freshness")},
            {"Widget": "Open Trades", "Current State": "EVIDENCE_READ", "Value": open_count, "Evidence Source": "journal_truth_unification + active_trades.csv", "Freshness": records["journal_truth_unification"].get("freshness")},
            {"Widget": "Closed Trades", "Current State": "EVIDENCE_READ", "Value": closed_count, "Evidence Source": records["trade_outcomes"].get("path"), "Freshness": records["trade_outcomes"].get("freshness")},
            {"Widget": "PnL", "Current State": "UNKNOWN" if pnl_value == "UNKNOWN" else "EVIDENCE_READ", "Value": pnl_value, "Evidence Source": records["paper_account"].get("path"), "Freshness": records["paper_account"].get("freshness")},
            {"Widget": "Exposure", "Current State": "UNKNOWN" if exposure == "UNKNOWN" else "EVIDENCE_READ", "Value": exposure, "Evidence Source": records["active_trades"].get("path"), "Freshness": records["active_trades"].get("freshness")},
            {"Widget": "Risk Summary", "Current State": risk_record.get("status"), "Value": v3_compact_value(risk_record.get("payload", {}).get("summary")), "Evidence Source": risk_record.get("path"), "Freshness": risk_record.get("freshness")},
        ]
        st.dataframe(trading_rows, use_container_width=True, hide_index=True)

        st.markdown("#### Mindmap")
        mindmap_rows = []
        for layer, source_names in V3_D03_LAYER_SOURCES.items():
            layer_records = [records.get(name, {}) for name in source_names]
            mindmap_rows.append({
                "Component": layer,
                "State": v3_layer_status(records, source_names),
                "Dependencies": v3_layer_dependencies(records, source_names),
                "Inputs": v3_join(source_names),
                "Freshness": v3_join(sorted({record.get("freshness") or "UNKNOWN" for record in layer_records})),
                "Source": v3_join(record.get("path") for record in layer_records),
            })
        st.dataframe(mindmap_rows, use_container_width=True, hide_index=True)

        st.markdown("#### Command Center Sources")
        source_rows = []
        for name in MODULE_SOURCE_MAP["Command Center"]:
            record = records.get(name, {})
            timestamp = record.get("timestamp")
            source_rows.append({
                "Source": name,
                "Source File": record.get("path"),
                "Timestamp": timestamp.strftime("%d %b %Y %H:%M:%S IST") if timestamp else None,
                "Freshness": record.get("freshness"),
                "Status": record.get("status"),
            })
        st.dataframe(source_rows, use_container_width=True, hide_index=True)


def render_module_frame(records, title, source_names, content_renderer, *, purpose="TITAN system module"):
    status = v3_module_status(records, source_names)
    freshness = v3_module_freshness(records, source_names)
    mode = v3_active_mode(records)
    trust_value, trust_sub = v3_trust_score(records)
    priority_header(title, status)
    state_cols = st.columns(4)
    with state_cols[0]:
        compact_kpi_card("State", format_status(status), purpose, status)
    with state_cols[1]:
        compact_kpi_card("Mode", format_status(mode), "runtime mode", mode)
    with state_cols[2]:
        compact_kpi_card("Freshness", format_status(freshness), "evidence age", freshness)
    with state_cols[3]:
        compact_kpi_card("Trust", trust_value if trust_value != "UNKNOWN" else None, trust_sub if trust_value != "UNKNOWN" else None, "FRESH" if trust_value != "UNKNOWN" else None)
    grid_row = st.columns([3, 1])
    with grid_row[0]:
        st.subheader("ACTION OUTPUT")
        with st.container(border=True):
            content_renderer(records)
    with grid_row[1]:
        v3_live_activity_panel(records, source_names)
        v3_evidence_panel(records, source_names)


def render_module_status_table(records, title, source_names, purpose):
    rows = []
    for name in source_names:
        record = records.get(name, {})
        rows.append({
            "Widget": name.replace("_", " ").title(),
            "Purpose": purpose,
            "Current State": record.get("status") or "UNKNOWN",
            "Current Activity": v3_compact_value(record.get("payload", {}).get("status_reason") if isinstance(record.get("payload"), dict) else "UNKNOWN"),
            "Current Inputs": record.get("path") or "UNKNOWN",
            "Current Outputs": v3_join(v3_source_consumers(name)),
            "Source": record.get("path") or "UNKNOWN",
            "Evidence Source": record.get("path") or "UNKNOWN",
            "Freshness": record.get("freshness") or "UNKNOWN",
            "Freshness Rule": "Per-source V3 truth source freshness",
            "Unknown Rule": "Missing source, timestamp, or field displays UNKNOWN",
            "Failure Rule": "No fabricated live state or readiness",
        })
    st.markdown(f"### {title}")
    v3_render_department_table(rows)


def render_command_center(records):
    render_v4_datetime_card()
    render_v4_kpi_cards(records)
    panels = st.columns([1.05, 1.05, 1.05, 1.0])
    with panels[0]:
        render_v4_incidents(records)
    with panels[1]:
        render_v4_health_summary(records)
    with panels[2]:
        render_v4_runtime_overview(records)
    with panels[3]:
        render_v4_trading_overview(records)
    render_v4_system_mindmap(records)
    render_v4_command_center_debug(records)


def render_trading_department(records):
    open_rows = v3_open_trade_rows()
    closed_rows = v3_closed_trade_rows()
    consolidation = records["dashboard_truth_consolidation"]["payload"]
    open_count = "UNKNOWN" if not records.get("active_trades", {}).get("exists") else len(open_rows)
    if isinstance(consolidation, dict) and consolidation.get("active_trade_count") is not None:
        open_count = int(consolidation.get("active_trade_count"))
    closed_count = "UNKNOWN" if not records.get("trade_outcomes", {}).get("exists") else len(closed_rows)
    paper_payload = records.get("paper_account", {}).get("payload", {})
    risk_payload = records.get("risk_watchdog", {}).get("payload", {})
    account_value = v3_account_value(records, ("account_balance", "balance", "equity"))
    available_capital = payload_first(paper_payload, ("available_capital", "available_balance", "cash", "free_cash"))
    daily_pnl = v3_account_value(records, ("daily_pnl", "pnl", "realized_pnl", "closed_pnl"))
    total_pnl = v3_account_value(records, ("total_pnl", "cumulative_pnl", "net_pnl"))
    exposure = v3_open_exposure(open_rows)
    risk_state = payload_first(risk_payload, ("status", "state", "risk_level", "summary"), records.get("risk_watchdog", {}).get("status") or "UNKNOWN")
    items = [
        visible_value("Account Capital", account_value, records.get("paper_account"), status=records.get("paper_account", {}).get("status"), source_label="paper_account"),
        visible_value("Available Capital", available_capital, records.get("paper_account"), status=records.get("paper_account", {}).get("status"), source_label="paper_account"),
        visible_value("Daily PnL", daily_pnl, records.get("paper_account"), status="UNKNOWN" if daily_pnl == "UNKNOWN" else records.get("paper_account", {}).get("status"), source_label="paper_account"),
        visible_value("Total PnL", total_pnl, records.get("paper_account"), status="UNKNOWN" if total_pnl == "UNKNOWN" else records.get("paper_account", {}).get("status"), source_label="paper_account"),
        visible_value("Open Trades", open_count, records.get("active_trades"), status="UNKNOWN" if open_count == "UNKNOWN" else records.get("active_trades", {}).get("freshness"), source_label="active_trades"),
        visible_value("Closed Trades", closed_count, records.get("trade_outcomes"), status="UNKNOWN" if closed_count == "UNKNOWN" else records.get("trade_outcomes", {}).get("freshness"), source_label="trade_outcomes"),
        visible_value("Exposure", exposure, records.get("active_trades"), status="UNKNOWN" if exposure == "UNKNOWN" else records.get("active_trades", {}).get("freshness"), source_label="active_trades"),
        visible_value("Risk", risk_state, records.get("risk_watchdog"), status=records.get("risk_watchdog", {}).get("status"), source_label="risk_watchdog"),
    ]
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer(
        "Proof Details",
        items,
        [
            ("Trading Sources", [
                {"Source": name, "Path": records.get(name, {}).get("path"), "Status": records.get(name, {}).get("status"), "Freshness": records.get(name, {}).get("freshness"), "Age": v4_age_label_from_seconds(records.get(name, {}).get("age_seconds"))}
                for name in MODULE_SOURCE_MAP["Trading Department"]
            ])
        ],
    )


def render_execution_modes(records):
    execution_mode = execution_mode_record(records)
    execution_payload = records.get("execution_mode", {}).get("payload", {})
    hft_payload = records.get("hft_runtime_state", {}).get("payload", {})
    hft_safety = records.get("hft_safety_proof", {}).get("payload", {})
    classic_execution = component_value(records, "paper_engine", "Classic Execution")
    items = [
        execution_mode,
        visible_value("Switch In Progress", payload_first(execution_payload, ("switch_in_progress",), "UNKNOWN"), records.get("execution_mode"), status="PAUSED" if execution_payload.get("switch_in_progress") is True else records.get("execution_mode", {}).get("status"), source_label="execution_mode"),
        visible_value("Capital Owner", payload_first(execution_payload, ("capital_owner",), "UNKNOWN"), records.get("execution_mode"), status=records.get("execution_mode", {}).get("status"), source_label="execution_mode"),
        classic_execution,
        visible_value("HFT Worker", payload_first(hft_payload, ("worker_status", "status", "state"), records.get("hft_runtime_state", {}).get("status") or "UNKNOWN"), records.get("hft_runtime_state"), status=records.get("hft_runtime_state", {}).get("status"), source_label="hft_runtime_state"),
        visible_value("HFT Safety", payload_first(hft_safety, ("final_status", "safety_status", "status"), records.get("hft_safety_proof", {}).get("status") or "UNKNOWN"), records.get("hft_safety_proof"), status=records.get("hft_safety_proof", {}).get("status"), source_label="hft_safety_proof"),
        visible_value("HFT Active Trades", payload_first(records.get("hft_active_trades", {}).get("payload", {}), ("active_trade_count", "open_trade_count", "count"), "UNKNOWN"), records.get("hft_active_trades"), status=records.get("hft_active_trades", {}).get("status"), source_label="hft_active_trades"),
        visible_value("HFT Daily PnL", payload_first(records.get("hft_daily_pnl", {}).get("payload", {}), ("daily_pnl", "pnl", "realized_pnl"), "UNKNOWN"), records.get("hft_daily_pnl"), status=records.get("hft_daily_pnl", {}).get("status"), source_label="hft_daily_pnl"),
    ]
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer(
        "Proof Details",
        items,
        [
            ("Execution Mode Sources", [
                {"Source": name, "Path": records.get(name, {}).get("path"), "Status": records.get(name, {}).get("status"), "Freshness": records.get(name, {}).get("freshness"), "Age": v4_age_label_from_seconds(records.get(name, {}).get("age_seconds"))}
                for name in MODULE_SOURCE_MAP["Execution Modes - Classic Mode + HFT Mode"]
            ])
        ],
    )


def render_runtime_department(records):
    daemon_payload = records.get("daemon_health", {}).get("payload", {})
    heartbeat_payload = records.get("titan_heartbeat", {}).get("payload", {})
    scheduler_payload = records.get("scanner_scheduler", {}).get("payload", {})
    items = [
        component_value(records, "daemon", "Daemon"),
        visible_value("Daemon PID", payload_first(daemon_payload, ("pid", "process_id", "lock_pid"), "UNKNOWN"), records.get("daemon_health"), status=records.get("daemon_health", {}).get("status"), source_label="daemon_health"),
        visible_value("Heartbeat", payload_first(heartbeat_payload, ("status", "heartbeat_status", "state"), records.get("titan_heartbeat", {}).get("status") or "UNKNOWN"), records.get("titan_heartbeat"), status=records.get("titan_heartbeat", {}).get("status"), source_label="titan_heartbeat"),
        visible_value("Runtime Mode", payload_first(records.get("titan_runtime_status", {}).get("payload", {}), ("mode", "runtime_mode", "active_mode"), "UNKNOWN"), records.get("titan_runtime_status"), status=records.get("titan_runtime_status", {}).get("status"), source_label="titan_runtime_status"),
        component_value(records, "workers", "Workers"),
        visible_value("Scheduler", payload_first(scheduler_payload, ("status", "state", "scheduler_status"), records.get("scanner_scheduler", {}).get("status") or "UNKNOWN"), records.get("scanner_scheduler"), status=records.get("scanner_scheduler", {}).get("status"), source_label="scanner_scheduler"),
        record_value(records, "authoritative_runtime_truth", "Runtime Truth", source_label="authoritative_runtime_truth"),
        record_value(records, "component_freshness_summary", "Freshness Summary", source_label="component_freshness_summary"),
    ]
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer(
        "Proof Details",
        items,
        [
            ("Runtime Sources", [
                {"Source": name, "Path": records.get(name, {}).get("path"), "Status": records.get(name, {}).get("status"), "Freshness": records.get(name, {}).get("freshness"), "Age": v4_age_label_from_seconds(records.get(name, {}).get("age_seconds"))}
                for name in MODULE_SOURCE_MAP["Runtime Department"]
            ])
        ],
    )


def render_intelligence_department(records):
    scanner_payload = records.get("scanner_status", {}).get("payload", {})
    setup_payload = records.get("setup_engine_status", {}).get("payload", {})
    brain_payload = records.get("master_brain_status", {}).get("payload", {})
    regime_payload = records.get("market_regime_update", {}).get("payload", {})
    items = [
        component_value(records, "master_brain", "Master Brain"),
        visible_value("Brain Decision", payload_first(brain_payload, ("current_decision", "last_decision", "decision", "status_reason"), "UNKNOWN"), records.get("master_brain_status"), status=records.get("master_brain_status", {}).get("status"), source_label="master_brain_status"),
        component_value(records, "scanner", "Scanner"),
        visible_value("Scanned Count", payload_first(scanner_payload, ("scanned_count", "stocks_checked", "symbols_scanned", "scan_count"), "UNKNOWN"), records.get("scanner_status"), status=records.get("scanner_status", {}).get("status"), source_label="scanner_status"),
        component_value(records, "setup_engine", "Setup Engine"),
        visible_value("Produced Setups", payload_first(setup_payload, ("produced_setups", "final_validated_setups", "setup_count", "count"), "UNKNOWN"), records.get("setup_engine_status"), status=records.get("setup_engine_status", {}).get("status"), source_label="setup_engine_status"),
        visible_value("Market Regime", payload_first(regime_payload, ("regime", "market_regime", "state", "status"), records.get("market_regime_update", {}).get("status") or "UNKNOWN"), records.get("market_regime_update"), status=records.get("market_regime_update", {}).get("status"), source_label="market_regime_update"),
        visible_value("Signal Diagnostics", payload_first(records.get("signal_path_diagnostics", {}).get("payload", {}), ("status", "summary", "state"), records.get("signal_path_diagnostics", {}).get("status") or "UNKNOWN"), records.get("signal_path_diagnostics"), status=records.get("signal_path_diagnostics", {}).get("status"), source_label="signal_path_diagnostics"),
    ]
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer("Proof Details", items, [("Intelligence Sources", source_rows(records, MODULE_SOURCE_MAP["Intelligence Department"]))])


def render_learning_department(records):
    evolution_payload = records.get("evolution_engine", {}).get("payload", {})
    rl_payload = records.get("reinforcement_learning", {}).get("payload", {})
    outcome_payload = records.get("outcome_tracker", {}).get("payload", {})
    memory_payload = records.get("memory_health", {}).get("payload", {})
    rejection_payload = records.get("strategy_rejection_analysis", {}).get("payload", {})
    items = [
        visible_value("Evolution Engine", payload_first(evolution_payload, ("current_action", "status", "state"), records.get("evolution_engine", {}).get("status") or "UNKNOWN"), records.get("evolution_engine"), status=records.get("evolution_engine", {}).get("status"), source_label="evolution_engine"),
        visible_value("Learning Queue", payload_first(rl_payload, ("queue_size", "pending_count", "status", "state"), records.get("reinforcement_learning", {}).get("status") or "UNKNOWN"), records.get("reinforcement_learning"), status=records.get("reinforcement_learning", {}).get("status"), source_label="reinforcement_learning"),
        visible_value("Outcome Tracker", payload_first(outcome_payload, ("status", "state", "pending_outcomes", "last_outcome"), records.get("outcome_tracker", {}).get("status") or "UNKNOWN"), records.get("outcome_tracker"), status=records.get("outcome_tracker", {}).get("status"), source_label="outcome_tracker"),
        visible_value("Memory Health", payload_first(memory_payload, ("status", "state", "memory_size", "summary"), records.get("memory_health", {}).get("status") or "UNKNOWN"), records.get("memory_health"), status=records.get("memory_health", {}).get("status"), source_label="memory_health"),
        visible_value("Pattern Discovery", payload_first(rejection_payload, ("status", "state", "patterns_found", "summary"), records.get("strategy_rejection_analysis", {}).get("status") or "UNKNOWN"), records.get("strategy_rejection_analysis"), status=records.get("strategy_rejection_analysis", {}).get("status"), source_label="strategy_rejection_analysis"),
        hft_isolation_value(records),
    ]
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer("Proof Details", items, [("Learning Sources", source_rows(records, MODULE_SOURCE_MAP["Learning Department"] + ["hft_safety_proof"]))])


def render_diagnostics_department(records):
    active, historical, open_warnings, resolved_warnings, conflicts = v3_incident_lists(records)
    stale_sources = [name for name, record in records.items() if record.get("freshness") == "STALE"]
    unknown_sources = [name for name, record in records.items() if record.get("freshness") == "UNKNOWN"]
    error_payload = records.get("runtime_error_summary", {}).get("payload", {})
    integrity_payload = records.get("dashboard_runtime_integrity", {}).get("payload", {})
    items = [
        visible_value("Truth Gate", records.get("truth_gate", {}).get("status") or "UNKNOWN", records.get("truth_gate"), status=records.get("truth_gate", {}).get("status"), source_label="truth_gate"),
        visible_value("Runtime Errors", payload_first(error_payload, ("error_count", "count", "errors"), len(historical)), records.get("runtime_error_summary"), status=records.get("runtime_error_summary", {}).get("status"), source_label="runtime_error_summary"),
        visible_value("Open Warnings", len(open_warnings), records.get("runtime_warning_resolution"), status=records.get("runtime_warning_resolution", {}).get("status"), source_label="runtime_warning_resolution"),
        visible_value("Conflicts", len(conflicts), records.get("authoritative_runtime_truth"), status="CONFLICT" if conflicts else records.get("authoritative_runtime_truth", {}).get("status"), source_label="authoritative_runtime_truth"),
        visible_value("Stale Sources", len(stale_sources), records.get("component_freshness_summary"), status="STALE" if stale_sources else records.get("component_freshness_summary", {}).get("status"), source_label="component_freshness_summary"),
        visible_value("Unknown Sources", len(unknown_sources), records.get("component_freshness_summary"), status="UNKNOWN" if unknown_sources else records.get("component_freshness_summary", {}).get("status"), source_label="component_freshness_summary"),
        visible_value("Dashboard Integrity", payload_first(integrity_payload, ("dashboard_runtime_integrity_status", "status", "state"), records.get("dashboard_runtime_integrity", {}).get("status") or "UNKNOWN"), records.get("dashboard_runtime_integrity"), status=records.get("dashboard_runtime_integrity", {}).get("status"), source_label="dashboard_runtime_integrity"),
    ]
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer(
        "Proof Details",
        items,
        [
            ("Diagnostics Sources", source_rows(records, MODULE_SOURCE_MAP["Diagnostics Department"])),
            ("Stale Sources", [{"Source": name, "Path": records.get(name, {}).get("path"), "Age": v4_age_label_from_seconds(records.get(name, {}).get("age_seconds")), "Freshness": records.get(name, {}).get("freshness")} for name in stale_sources]),
            ("Unknown Sources", [{"Source": name, "Path": records.get(name, {}).get("path"), "Freshness": records.get(name, {}).get("freshness")} for name in unknown_sources]),
        ],
    )


def render_incident_room(records):
    active, historical, open_warnings, resolved_warnings, conflicts = v3_incident_lists(records)
    authoritative = records.get("authoritative_runtime_truth", {})
    warning_resolution = records.get("runtime_warning_resolution", {})
    integrity = records.get("dashboard_runtime_integrity", {})
    active_status = blueprint_status(authoritative.get("status"), authoritative.get("freshness"), authoritative.get("exists"))
    warning_status = blueprint_status(warning_resolution.get("status"), warning_resolution.get("freshness"), warning_resolution.get("exists"))
    integrity_status = blueprint_status(integrity.get("status"), integrity.get("freshness"), integrity.get("exists"))
    items = [
        visible_value("Active Incidents", len(active), authoritative, status=active_status, source_label="authoritative_runtime_truth"),
        visible_value("Open Warnings", len(open_warnings), warning_resolution, status=warning_status, source_label="runtime_warning_resolution"),
        visible_value("Resolved Warnings", len(resolved_warnings), warning_resolution, status=warning_status, source_label="runtime_warning_resolution"),
        visible_value("Conflicts", len(conflicts), authoritative, status="CONFLICT" if conflicts else active_status, source_label="authoritative_runtime_truth"),
        visible_value("Historical Errors", len(historical), records.get("daemon_errors"), status=records.get("daemon_errors", {}).get("freshness"), source_label="daemon_errors"),
        visible_value("Integrity", integrity.get("status") or "UNKNOWN", integrity, status=integrity_status, source_label="dashboard_runtime_integrity"),
    ]
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    incident_rows = [{"Type": "active", **row} for row in active] + [{"Type": "open_warning", **row} for row in open_warnings] + [{"Type": "conflict", **row} for row in conflicts]
    render_v4_proof_drawer(
        "Proof Details",
        items,
        [
            ("Incident Evidence", incident_rows),
            ("Historical Error Tail", historical),
            ("Incident Sources", [
                {"Source": name, "Path": records.get(name, {}).get("path"), "Status": records.get(name, {}).get("status"), "Freshness": records.get(name, {}).get("freshness"), "Age": v4_age_label_from_seconds(records.get(name, {}).get("age_seconds"))}
                for name in MODULE_SOURCE_MAP["Incident Room"]
            ]),
        ],
    )


def render_echo_department(records):
    mission_payload = records.get("echo_mission", {}).get("payload", {})
    queue_payload = records.get("echo_mission_queue", {}).get("payload", {})
    report_payload = records.get("echo_recent_report", {}).get("payload", {})
    reviewed_payload = records.get("echo_files_reviewed", {}).get("payload", {})
    diagnostics_payload = records.get("echo_diagnostics", {}).get("payload", {})
    items = [
        visible_value("Current Mission", payload_first(mission_payload, ("mission_id", "status", "state", "objective"), records.get("echo_mission", {}).get("status") or "UNKNOWN"), records.get("echo_mission"), status=records.get("echo_mission", {}).get("status"), source_label="echo_mission"),
        visible_value("Mission Queue", payload_first(queue_payload, ("pending_count", "queue_size", "status", "state"), records.get("echo_mission_queue", {}).get("status") or "UNKNOWN"), records.get("echo_mission_queue"), status=records.get("echo_mission_queue", {}).get("status"), source_label="echo_mission_queue"),
        visible_value("Recent Report", payload_first(report_payload, ("status", "state", "report_id", "summary"), records.get("echo_recent_report", {}).get("status") or "UNKNOWN"), records.get("echo_recent_report"), status=records.get("echo_recent_report", {}).get("status"), source_label="echo_recent_report"),
        visible_value("Files Reviewed", payload_first(reviewed_payload, ("files_reviewed", "count", "status"), records.get("echo_files_reviewed", {}).get("status") or "UNKNOWN"), records.get("echo_files_reviewed"), status=records.get("echo_files_reviewed", {}).get("status"), source_label="echo_files_reviewed"),
        visible_value("Diagnostics", payload_first(diagnostics_payload, ("status", "state", "last_action"), records.get("echo_diagnostics", {}).get("status") or "UNKNOWN"), records.get("echo_diagnostics"), status=records.get("echo_diagnostics", {}).get("status"), source_label="echo_diagnostics"),
    ]
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer("Proof Details", items, [("ECHO Sources", source_rows(records, MODULE_SOURCE_MAP["ECHO Department"]))])


def render_control_room(records):
    render_module_frame(records, "Control Room", MODULE_SOURCE_MAP["Control Room"], v3_render_control_room, purpose="Read-only readiness, permission, safety, and trust gates.")


def render_laboratory(records):
    lab_payload = records.get("lab_activity", {}).get("payload", {})
    experiments_payload = records.get("strategy_experiments", {}).get("payload", {})
    alpha_payload = records.get("alpha_health", {}).get("payload", {})
    lane_payload = records.get("alpha_lane_candidates", {}).get("payload", {})
    outcome_payload = records.get("alpha_shadow_outcome_report", {}).get("payload", {})
    items = [
        visible_value("Lab Activity", payload_first(lab_payload, ("current_activity", "status", "state"), records.get("lab_activity", {}).get("status") or "UNKNOWN"), records.get("lab_activity"), status=records.get("lab_activity", {}).get("status"), source_label="lab_activity"),
        visible_value("Strategy Experiments", payload_first(experiments_payload, ("running_count", "experiment_count", "status", "state"), records.get("strategy_experiments", {}).get("status") or "UNKNOWN"), records.get("strategy_experiments"), status=records.get("strategy_experiments", {}).get("status"), source_label="strategy_experiments"),
        visible_value("Alpha Health", payload_first(alpha_payload, ("status_reason", "status", "state"), records.get("alpha_health", {}).get("status") or "UNKNOWN"), records.get("alpha_health"), status=records.get("alpha_health", {}).get("status"), source_label="alpha_health"),
        visible_value("Lane Candidates", payload_first(lane_payload, ("candidate_count", "count", "status"), records.get("alpha_lane_candidates", {}).get("status") or "UNKNOWN"), records.get("alpha_lane_candidates"), status=records.get("alpha_lane_candidates", {}).get("status"), source_label="alpha_lane_candidates"),
        visible_value("Shadow Outcomes", payload_first(outcome_payload, ("outcome_count", "closed_count", "status"), records.get("alpha_shadow_outcome_report", {}).get("status") or "UNKNOWN"), records.get("alpha_shadow_outcome_report"), status=records.get("alpha_shadow_outcome_report", {}).get("status"), source_label="alpha_shadow_outcome_report"),
        record_value(records, "backtesting_status", "Backtesting", source_label="backtesting_status"),
        record_value(records, "historical_replay", "Historical Replay", source_label="historical_replay"),
    ]
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer("Proof Details", items, [("Laboratory Sources", source_rows(records, MODULE_SOURCE_MAP["Laboratory"]))])


def render_experience_knowledge(records):
    replay_payload = records.get("historical_replay", {}).get("payload", {})
    memory_payload = records.get("memory_health", {}).get("payload", {})
    lineage_payload = records.get("memory_lineage", {}).get("payload", {})
    contribution_payload = records.get("memory_contribution", {}).get("payload", {})
    evolution_payload = records.get("evolution_memory", {}).get("payload", {})
    items = [
        visible_value("Historical Replay", payload_first(replay_payload, ("current_window", "current_symbol", "status", "state"), records.get("historical_replay", {}).get("status") or "UNKNOWN"), records.get("historical_replay"), status=records.get("historical_replay", {}).get("status"), source_label="historical_replay"),
        visible_value("Replay Samples", list_count_from_payload(replay_payload, ("samples_processed", "sample_count", "records_processed")), records.get("historical_replay"), status=records.get("historical_replay", {}).get("status"), source_label="historical_replay"),
        visible_value("Memory Health", payload_first(memory_payload, ("status", "state", "summary"), records.get("memory_health", {}).get("status") or "UNKNOWN"), records.get("memory_health"), status=records.get("memory_health", {}).get("status"), source_label="memory_health"),
        visible_value("Lineage Nodes", list_count_from_payload(lineage_payload, ("nodes", "lineage_nodes", "node_count")), records.get("memory_lineage"), status=records.get("memory_lineage", {}).get("status"), source_label="memory_lineage"),
        visible_value("Knowledge Contributions", list_count_from_payload(contribution_payload, ("contributions", "contribution_count", "records_added")), records.get("memory_contribution"), status=records.get("memory_contribution", {}).get("status"), source_label="memory_contribution"),
        visible_value("Evolution Memory", payload_first(evolution_payload, ("status", "state", "summary"), records.get("evolution_memory", {}).get("status") or "UNKNOWN"), records.get("evolution_memory"), status=records.get("evolution_memory", {}).get("status"), source_label="evolution_memory"),
        hft_memory_inclusion_value(records),
    ]
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer("Proof Details", items, [("Experience Sources", source_rows(records, MODULE_SOURCE_MAP["Experience & Knowledge Layer"]))])


def render_timeline_replay(records):
    replay_payload = records.get("historical_replay", {}).get("payload", {})
    backtest_payload = records.get("backtesting_status", {}).get("payload", {})
    reconciliation_payload = records.get("runtime_reconciliation", {}).get("payload", {})
    live_metrics_payload = records.get("dashboard_live_metrics", {}).get("payload", {})
    event_timeline = live_metrics_payload.get("event_timeline") if isinstance(live_metrics_payload, dict) else None
    items = [
        visible_value("Event Timeline", len(event_timeline) if isinstance(event_timeline, list) else "UNKNOWN", records.get("dashboard_live_metrics"), status=records.get("dashboard_live_metrics", {}).get("status") if isinstance(event_timeline, list) else "UNKNOWN", source_label="dashboard_live_metrics"),
        visible_value("Replay Status", payload_first(replay_payload, ("status", "state", "current_window"), records.get("historical_replay", {}).get("status") or "UNKNOWN"), records.get("historical_replay"), status=records.get("historical_replay", {}).get("status"), source_label="historical_replay"),
        visible_value("Replay Progress", payload_first(replay_payload, ("progress", "progress_pct", "samples_processed"), "UNKNOWN"), records.get("historical_replay"), status=records.get("historical_replay", {}).get("status"), source_label="historical_replay"),
        visible_value("Backtesting", payload_first(backtest_payload, ("status", "state", "progress"), records.get("backtesting_status", {}).get("status") or "UNKNOWN"), records.get("backtesting_status"), status=records.get("backtesting_status", {}).get("status"), source_label="backtesting_status"),
        visible_value("Runtime Reconciliation", payload_first(reconciliation_payload, ("status", "state", "summary"), records.get("runtime_reconciliation", {}).get("status") or "UNKNOWN"), records.get("runtime_reconciliation"), status=records.get("runtime_reconciliation", {}).get("status"), source_label="runtime_reconciliation"),
        visible_value("Clickable Event Proof", "UNKNOWN", records.get("dashboard_live_metrics"), status="UNKNOWN", source_label="dashboard_live_metrics"),
    ]
    timeline_rows = event_timeline if isinstance(event_timeline, list) else [{"Status": "UNKNOWN", "Reason": "No canonical event_timeline evidence found"}]
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer("Proof Details", items, [("Timeline Events", timeline_rows), ("Timeline Sources", source_rows(records, MODULE_SOURCE_MAP["Timeline / Replay Room"]))])


def render_decision_explainer(records):
    signal_payload = records.get("signal_path_diagnostics", {}).get("payload", {})
    trend_payload = records.get("trend_diagnostics", {}).get("payload", {})
    graph_payload = records.get("metric_dependency_graph", {}).get("payload", {})
    brain_payload = records.get("master_brain_status", {}).get("payload", {})
    setup_payload = records.get("setup_engine_status", {}).get("payload", {})
    items = [
        visible_value("Latest Decision", payload_first(brain_payload, ("current_decision", "last_decision", "decision"), "UNKNOWN"), records.get("master_brain_status"), status=records.get("master_brain_status", {}).get("status"), source_label="master_brain_status"),
        visible_value("Setup Evidence", payload_first(setup_payload, ("latest_setup", "setup_count", "status"), records.get("setup_engine_status", {}).get("status") or "UNKNOWN"), records.get("setup_engine_status"), status=records.get("setup_engine_status", {}).get("status"), source_label="setup_engine_status"),
        visible_value("Signal Path", payload_first(signal_payload, ("status", "summary", "state"), records.get("signal_path_diagnostics", {}).get("status") or "UNKNOWN"), records.get("signal_path_diagnostics"), status=records.get("signal_path_diagnostics", {}).get("status"), source_label="signal_path_diagnostics"),
        visible_value("Trend Diagnostics", payload_first(trend_payload, ("status", "summary", "state"), records.get("trend_diagnostics", {}).get("status") or "UNKNOWN"), records.get("trend_diagnostics"), status=records.get("trend_diagnostics", {}).get("status"), source_label="trend_diagnostics"),
        visible_value("Dependency Graph", payload_first(graph_payload, ("edge_count", "dependency_count", "status"), records.get("metric_dependency_graph", {}).get("status") or "UNKNOWN"), records.get("metric_dependency_graph"), status=records.get("metric_dependency_graph", {}).get("status"), source_label="metric_dependency_graph"),
        visible_value("Explanation Proof", "UNKNOWN", records.get("signal_path_diagnostics"), status="UNKNOWN", source_label="signal_path_diagnostics"),
    ]
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer("Proof Details", items, [("Decision Sources", source_rows(records, MODULE_SOURCE_MAP["Decision Explainer"] + ["master_brain_status", "setup_engine_status"]))])


def render_data_lineage(records):
    edges = dependency_edge_rows(records)
    source_count = len(records)
    consumer_count = len({consumer for name in records for consumer in v3_source_consumers(name) if consumer != "UNKNOWN"})
    items = [
        visible_value("Truth Sources", source_count, records.get("dashboard_truth_registry"), status=records.get("dashboard_truth_registry", {}).get("status"), source_label="dashboard_truth_registry"),
        visible_value("Dependency Edges", len(edges) if edges else "UNKNOWN", records.get("metric_dependency_graph"), status=records.get("metric_dependency_graph", {}).get("status") if edges else "UNKNOWN", source_label="metric_dependency_graph"),
        visible_value("Metric Ownership", records.get("canonical_metric_ownership", {}).get("status") or "UNKNOWN", records.get("canonical_metric_ownership"), status=records.get("canonical_metric_ownership", {}).get("status"), source_label="canonical_metric_ownership"),
        visible_value("Memory Lineage", records.get("memory_lineage", {}).get("status") or "UNKNOWN", records.get("memory_lineage"), status=records.get("memory_lineage", {}).get("status"), source_label="memory_lineage"),
        visible_value("Consumers", consumer_count if consumer_count else "UNKNOWN", records.get("dashboard_truth_registry"), status=records.get("dashboard_truth_registry", {}).get("status") if consumer_count else "UNKNOWN", source_label="dashboard_truth_registry"),
    ]
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer("Proof Details", items, [("Lineage Sources", source_rows(records, MODULE_SOURCE_MAP["Data Lineage"])), ("Dependency Edges", edges)])


def render_trust_proof(records):
    trust_value, trust_sub = v3_trust_score(records)
    active, historical, open_warnings, resolved_warnings, conflicts = v3_incident_lists(records)
    items = [
        visible_value("Trust Score", trust_value, records.get("authoritative_runtime_truth"), status=records.get("authoritative_runtime_truth", {}).get("status"), source_label="authoritative_runtime_truth"),
        visible_value("Truth Gate", records.get("truth_gate", {}).get("status") or "UNKNOWN", records.get("truth_gate"), status=records.get("truth_gate", {}).get("status"), source_label="truth_gate"),
        visible_value("Truth Registry", records.get("dashboard_truth_registry", {}).get("status") or "UNKNOWN", records.get("dashboard_truth_registry"), status=records.get("dashboard_truth_registry", {}).get("status"), source_label="dashboard_truth_registry"),
        visible_value("Runtime Integrity", records.get("dashboard_runtime_integrity", {}).get("status") or "UNKNOWN", records.get("dashboard_runtime_integrity"), status=records.get("dashboard_runtime_integrity", {}).get("status"), source_label="dashboard_runtime_integrity"),
        visible_value("Conflicts", len(conflicts), records.get("authoritative_runtime_truth"), status="CONFLICT" if conflicts else records.get("authoritative_runtime_truth", {}).get("status"), source_label="authoritative_runtime_truth"),
        visible_value("HFT Proof", records.get("hft_safety_proof", {}).get("status") or "UNKNOWN", records.get("hft_safety_proof"), status=records.get("hft_safety_proof", {}).get("status"), source_label="hft_safety_proof"),
    ]
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer("Proof Details", items, [("Trust Summary", [{"Trust": trust_value, "Detail": trust_sub}]), ("Trust Sources", source_rows(records, MODULE_SOURCE_MAP["Trust / Proof"]))])


def render_flow_visualizer(records):
    edges = dependency_edge_rows(records)
    dashboard_flows = v3_dashboard_flow_rows(records)
    items = [
        visible_value("Published Edges", len(edges) if edges else "UNKNOWN", records.get("metric_dependency_graph"), status=records.get("metric_dependency_graph", {}).get("status") if edges else "UNKNOWN", source_label="metric_dependency_graph"),
        visible_value("Dashboard Flows", len(dashboard_flows), records.get("dashboard_truth_registry"), status=records.get("dashboard_truth_registry", {}).get("status"), source_label="dashboard_truth_registry"),
        visible_value("Payload Time", "UNKNOWN", records.get("metric_dependency_graph"), status="UNKNOWN", source_label="metric_dependency_graph"),
        visible_value("Delay", "UNKNOWN", records.get("metric_dependency_graph"), status="UNKNOWN", source_label="metric_dependency_graph"),
        visible_value("Events/Sec", "UNKNOWN", records.get("metric_dependency_graph"), status="UNKNOWN", source_label="metric_dependency_graph"),
        visible_value("Journal Flow", records.get("journal_truth_unification", {}).get("status") or "UNKNOWN", records.get("journal_truth_unification"), status=records.get("journal_truth_unification", {}).get("status"), source_label="journal_truth_unification"),
    ]
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer("Proof Details", items, [("Published Dependency Edges", edges), ("Dashboard Read Flows", dashboard_flows[:50]), ("Flow Sources", source_rows(records, MODULE_SOURCE_MAP["Flow Visualizer"]))])


def render_resource_pressure(records):
    items = [
        live_metric_value(records, "CPU", ("cpu", "cpu_pct", "cpu_percent", "cpu_usage")),
        live_metric_value(records, "RAM", ("ram", "ram_pct", "memory_percent", "ram_percent", "memory_usage", "ram_usage")),
        live_metric_value(records, "Disk", ("disk", "disk_pct", "disk_usage", "disk_percent")),
        live_metric_value(records, "Queues", ("queues", "queue_depth", "queue_size")),
        live_metric_value(records, "Threads", ("threads", "thread_count", "active_threads")),
        live_metric_value(records, "Storage", ("storage", "storage_usage", "storage_percent", "local_storage")),
        live_metric_value(records, "Supabase Usage", ("supabase_usage", "supabase_storage", "supabase_db_size")),
        live_metric_value(records, "API / Network Latency", ("api_latency", "api_latency_ms", "network_latency", "network_latency_ms", "relay_latency", "relay_latency_ms", "latency_ms")),
        live_metric_value(records, "Pressure Risk", ("pressure_risk", "crash_risk", "storage_risk")),
    ]
    render_tv_pulse()
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer("Proof Details", items, [("Resource Sources", source_rows(records, MODULE_SOURCE_MAP["Resource / Storage / Pressure"]))])


def render_memory_explorer(records):
    memory_payload = records.get("memory_health", {}).get("payload", {})
    lineage_payload = records.get("memory_lineage", {}).get("payload", {})
    contribution_payload = records.get("memory_contribution", {}).get("payload", {})
    evolution_payload = records.get("evolution_memory", {}).get("payload", {})
    rejection_payload = records.get("strategy_rejection_analysis", {}).get("payload", {})
    alpha_payload = records.get("alpha_memory_summary", {}).get("payload", {})
    items = [
        visible_value("Memory Status", payload_first(memory_payload, ("status", "state", "summary"), records.get("memory_health", {}).get("status") or "UNKNOWN"), records.get("memory_health"), status=records.get("memory_health", {}).get("status"), source_label="memory_health"),
        visible_value("Patterns", list_count_from_payload(rejection_payload, ("patterns", "pattern_count", "patterns_found")), records.get("strategy_rejection_analysis"), status=records.get("strategy_rejection_analysis", {}).get("status"), source_label="strategy_rejection_analysis"),
        visible_value("Beliefs", list_count_from_payload(evolution_payload, ("beliefs", "belief_count", "active_beliefs")), records.get("evolution_memory"), status=records.get("evolution_memory", {}).get("status"), source_label="evolution_memory"),
        visible_value("Lineage Entries", list_count_from_payload(lineage_payload, ("nodes", "edges", "lineage_count", "node_count")), records.get("memory_lineage"), status=records.get("memory_lineage", {}).get("status"), source_label="memory_lineage"),
        visible_value("Contributions", list_count_from_payload(contribution_payload, ("contributions", "contribution_count", "records_added")), records.get("memory_contribution"), status=records.get("memory_contribution", {}).get("status"), source_label="memory_contribution"),
        visible_value("Alpha Memory", payload_first(alpha_payload, ("status", "state", "summary"), records.get("alpha_memory_summary", {}).get("status") or "UNKNOWN"), records.get("alpha_memory_summary"), status=records.get("alpha_memory_summary", {}).get("status"), source_label="alpha_memory_summary"),
        hft_memory_inclusion_value(records),
    ]
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer("Proof Details", items, [("Memory Sources", source_rows(records, MODULE_SOURCE_MAP["Memory / Knowledge Explorer"]))])


def render_freshness_map(records):
    counts = freshness_counts(records)
    items = [
        visible_value("Fresh Sources", counts["FRESH"], records.get("component_freshness_summary"), status="FRESH" if counts["FRESH"] else "UNKNOWN", source_label="component_freshness_summary"),
        visible_value("Stale Sources", counts["STALE"], records.get("component_freshness_summary"), status="STALE" if counts["STALE"] else records.get("component_freshness_summary", {}).get("status"), source_label="component_freshness_summary"),
        visible_value("Unknown Sources", counts["UNKNOWN"], records.get("component_freshness_summary"), status="UNKNOWN" if counts["UNKNOWN"] else records.get("component_freshness_summary", {}).get("status"), source_label="component_freshness_summary"),
        visible_value("Conflict Sources", counts["CONFLICT"], records.get("component_freshness_summary"), status="CONFLICT" if counts["CONFLICT"] else records.get("component_freshness_summary", {}).get("status"), source_label="component_freshness_summary"),
        visible_value("Truth Registry", records.get("dashboard_truth_registry", {}).get("status") or "UNKNOWN", records.get("dashboard_truth_registry"), status=records.get("dashboard_truth_registry", {}).get("status"), source_label="dashboard_truth_registry"),
        visible_value("Authoritative Truth", records.get("authoritative_runtime_truth", {}).get("status") or "UNKNOWN", records.get("authoritative_runtime_truth"), status=records.get("authoritative_runtime_truth", {}).get("status"), source_label="authoritative_runtime_truth"),
    ]
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer("Proof Details", items, [("Freshness Detail", freshness_detail_rows(records)), ("Freshness Sources", source_rows(records, MODULE_SOURCE_MAP["Freshness Map"]))])


def render_watchtower(records):
    active, historical, open_warnings, resolved_warnings, conflicts = v3_incident_lists(records)
    items = [
        watchtower_value(records, "Predicted Stale Risk", ("predicted_stale_risk", "stale_risk")),
        watchtower_value(records, "Disk Full Risk", ("disk_full_risk", "storage_full_risk")),
        watchtower_value(records, "Supabase Growth Risk", ("supabase_growth_risk", "db_growth_risk")),
        watchtower_value(records, "Worker Overload Risk", ("worker_overload_risk", "overload_risk")),
        visible_value("Open Warnings", len(open_warnings), records.get("runtime_warning_resolution"), status=records.get("runtime_warning_resolution", {}).get("status"), source_label="runtime_warning_resolution"),
        visible_value("Restart Blockers", len(active), records.get("restart_readiness_gate"), status=records.get("restart_readiness_gate", {}).get("status"), source_label="restart_readiness_gate"),
    ]
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer("Proof Details", items, [("Watchtower Sources", source_rows(records, MODULE_SOURCE_MAP["Watchtower"])), ("Open Warnings", open_warnings)])


def render_architecture_department(records):
    body_map = body_map_payload(records)
    body_nodes = body_map.get("nodes") if isinstance(body_map.get("nodes"), list) else None
    body_edges = body_map.get("edges") if isinstance(body_map.get("edges"), list) else None
    items = [
        visible_value("Body Map", records.get("titan_body_map_live", {}).get("status") or "UNKNOWN", records.get("titan_body_map_live"), status=records.get("titan_body_map_live", {}).get("status"), source_label="titan_body_map_live"),
        visible_value("Body Nodes", len(body_nodes) if body_nodes is not None else "UNKNOWN", records.get("titan_body_map_live"), status=records.get("titan_body_map_live", {}).get("status") if body_nodes is not None else "UNKNOWN", source_label="titan_body_map_live"),
        visible_value("Body Edges", len(body_edges) if body_edges is not None else "UNKNOWN", records.get("titan_body_map_live"), status=records.get("titan_body_map_live", {}).get("status") if body_edges is not None else "UNKNOWN", source_label="titan_body_map_live"),
        visible_value("Runtime Topology", records.get("runtime_topology", {}).get("status") or "UNKNOWN", records.get("runtime_topology"), status=records.get("runtime_topology", {}).get("status"), source_label="runtime_topology"),
        visible_value("Visibility Audit", records.get("runtime_visibility_audit", {}).get("status") or "UNKNOWN", records.get("runtime_visibility_audit"), status=records.get("runtime_visibility_audit", {}).get("status"), source_label="runtime_visibility_audit"),
        visible_value("Runtime Permissions", records.get("runtime_permissions", {}).get("status") or "UNKNOWN", records.get("runtime_permissions"), status=records.get("runtime_permissions", {}).get("status"), source_label="runtime_permissions"),
        hft_isolation_value(records),
        visible_value("Alpha Boundary", records.get("alpha_health", {}).get("status") or "UNKNOWN", records.get("alpha_health"), status=records.get("alpha_health", {}).get("status"), source_label="alpha_health"),
    ]
    boundary_rows = v3_architecture_rows(records)
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer("Proof Details", items, [("Architecture Sources", source_rows(records, MODULE_SOURCE_MAP["Architecture Department"] + ["titan_body_map_live"])), ("Boundary Policy Rows", boundary_rows)])


def render_system_mindmap(records):
    record = records.get("titan_body_map_live", {})
    nodes = body_map_nodes(records)
    edges = body_map_edges(records)
    if not record.get("exists") or not nodes:
        items = [
            visible_value("Body Map", "UNKNOWN", record, status="UNKNOWN", source_label="titan_body_map_live"),
            visible_value("Nodes", "UNKNOWN", record, status="UNKNOWN", source_label="titan_body_map_live"),
            visible_value("Edges", "UNKNOWN", record, status="UNKNOWN", source_label="titan_body_map_live"),
        ]
        render_tv_pulse()
        st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
        render_v4_proof_drawer("Proof Details", items, [("Body Map Sources", source_rows(records, ["titan_body_map_live"]))])
        return

    status_counts = {"FAILED": 0, "STALE": 0, "DEGRADED": 0, "UNKNOWN": 0, "HEALTHY": 0}
    for node in nodes:
        status = mindmap_status_for_node(node)
        if status in {"FAILED", "FAIL", "BLOCKED", "STOPPED", "CONFLICT"}:
            status_counts["FAILED"] += 1
        elif status == "STALE":
            status_counts["STALE"] += 1
        elif status == "DEGRADED":
            status_counts["DEGRADED"] += 1
        elif status == "UNKNOWN":
            status_counts["UNKNOWN"] += 1
        else:
            status_counts["HEALTHY"] += 1

    grouped = {}
    for node in nodes:
        explicit_group = first_present(node, ("layer", "group", "domain", "tier", "category"))
        group_name = str(explicit_group or "Published Body Map Nodes").strip() or "Published Body Map Nodes"
        grouped.setdefault(group_name, []).append(node)

    preferred_order = [
        "TITAN Core",
        "Core",
        "Runtime",
        "Trading",
        "Intelligence",
        "Learning",
        "Diagnostics",
        "HFT",
        "ECHO",
        "Published Body Map Nodes",
    ]
    ordered_groups = []
    seen_groups = set()
    for group_name in preferred_order:
        for actual_name in list(grouped):
            if actual_name.lower() == group_name.lower() and actual_name not in seen_groups:
                ordered_groups.append(actual_name)
                seen_groups.add(actual_name)
    for actual_name in sorted(grouped):
        if actual_name not in seen_groups:
            ordered_groups.append(actual_name)

    def render_group(group_name, limit=18):
        node_html = []
        group_nodes = grouped.get(group_name, [])
        for node in group_nodes[:limit]:
            name = str(node.get("name") or node.get("id") or node.get("component") or "UNKNOWN")
            status = mindmap_status_for_node(node)
            meta = node.get("source") or node.get("source_file") or node.get("writer") or node.get("path") or "titan_body_map_live"
            is_core = group_name.lower() in {"titan core", "core"}
            node_html.append(mindmap_node_html(name, status, meta, core=is_core))
        if len(group_nodes) > limit:
            node_html.append(mindmap_node_html(f"+{len(group_nodes) - limit} more", "UNKNOWN", "Open Proof Details", core=False))
        return f"""
        <div class="mindmap-tier">
            <div style="width:100%; color:#8ea7d7; font-size:12px; font-weight:900; text-transform:uppercase; letter-spacing:.08em; margin:2px 0 8px;">{escape(v4_clip(group_name, 48))}</div>
            {"".join(node_html)}
        </div>
        """

    edge_paths = []
    edge_labels = []
    for index, edge in enumerate(edges[:12]):
        y = 24 + (index * 22)
        source = str(first_present(edge, ("source", "from", "src", "parent")) or "UNKNOWN")
        target = str(first_present(edge, ("target", "to", "dst", "child")) or "UNKNOWN")
        edge_paths.append(f'<path d="M30 {y} H1170" stroke="rgba(96,165,250,0.28)" stroke-width="1.5"/>')
        edge_labels.append(f'<text x="42" y="{y - 5}" fill="#8ea7d7" font-size="10" font-weight="700">{escape(v4_clip(source, 42))} -> {escape(v4_clip(target, 42))}</text>')
    edge_svg = "".join(edge_paths + edge_labels)
    edge_caption = f"{len(edges)} published edges" if edges else "No published body-map edges"

    render_tv_pulse()
    st.markdown(
        f"""
        <div class="mindmap-shell">
            <svg class="mindmap-lines" viewBox="0 0 1200 320" preserveAspectRatio="none" role="img" aria-label="{escape(edge_caption)}">
                {edge_svg}
            </svg>
            <div class="mindmap-tree">
                {"".join(render_group(group_name) for group_name in ordered_groups)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    items = [
        visible_value("Body Map", record.get("status") or "UNKNOWN", record, status=record.get("status"), source_label="titan_body_map_live"),
        visible_value("Nodes", len(nodes), record, status=record.get("status"), source_label="titan_body_map_live"),
        visible_value("Edges", len(edges), record, status=record.get("status"), source_label="titan_body_map_live"),
        visible_value("Failed / Conflict", status_counts["FAILED"], record, status="FAILED" if status_counts["FAILED"] else record.get("status"), source_label="titan_body_map_live"),
        visible_value("Stale / Degraded", status_counts["STALE"] + status_counts["DEGRADED"], record, status="STALE" if status_counts["STALE"] else ("DEGRADED" if status_counts["DEGRADED"] else record.get("status")), source_label="titan_body_map_live"),
        visible_value("Unknown", status_counts["UNKNOWN"], record, status="UNKNOWN" if status_counts["UNKNOWN"] else record.get("status"), source_label="titan_body_map_live"),
    ]
    st.markdown(v4_value_cards_html(items), unsafe_allow_html=True)
    render_v4_proof_drawer("Proof Details", items, [("Body Map Nodes", nodes), ("Body Map Edges", edges), ("Body Map Source", source_rows(records, ["titan_body_map_live"]))])


CONTROL_SYSTEM_ROUTES = {
    "Command Center": render_command_center,
    "Trading Department": render_trading_department,
    "Execution Modes - Classic Mode + HFT Mode": render_execution_modes,
    "Runtime Department": render_runtime_department,
    "Intelligence Department": render_intelligence_department,
    "Learning Department": render_learning_department,
    "Diagnostics Department": render_diagnostics_department,
    "Incident Room": render_incident_room,
    "ECHO Department": render_echo_department,
    "Control Room": render_control_room,
    "Laboratory": render_laboratory,
    "Experience & Knowledge Layer": render_experience_knowledge,
    "Timeline / Replay Room": render_timeline_replay,
    "Decision Explainer": render_decision_explainer,
    "Data Lineage": render_data_lineage,
    "Trust / Proof": render_trust_proof,
    "Flow Visualizer": render_flow_visualizer,
    "Resource / Storage / Pressure": render_resource_pressure,
    "Memory / Knowledge Explorer": render_memory_explorer,
    "Freshness Map": render_freshness_map,
    "Watchtower": render_watchtower,
    "Architecture Department": render_architecture_department,
    "System Mindmap": render_system_mindmap,
}


def main(records, selected_module):
    if selected_module == "Command Center":
        render_command_center(records)
    elif selected_module == "Trading Department":
        render_trading_department(records)
    elif selected_module == "Execution Modes - Classic Mode + HFT Mode":
        render_execution_modes(records)
    elif selected_module == "Runtime Department":
        render_runtime_department(records)
    elif selected_module == "Intelligence Department":
        render_intelligence_department(records)
    elif selected_module == "Learning Department":
        render_learning_department(records)
    elif selected_module == "Diagnostics Department":
        render_diagnostics_department(records)
    elif selected_module == "Incident Room":
        render_incident_room(records)
    elif selected_module == "ECHO Department":
        render_echo_department(records)
    elif selected_module == "Control Room":
        render_control_room(records)
    elif selected_module == "Laboratory":
        render_laboratory(records)
    elif selected_module == "Experience & Knowledge Layer":
        render_experience_knowledge(records)
    elif selected_module == "Timeline / Replay Room":
        render_timeline_replay(records)
    elif selected_module == "Decision Explainer":
        render_decision_explainer(records)
    elif selected_module == "Data Lineage":
        render_data_lineage(records)
    elif selected_module == "Trust / Proof":
        render_trust_proof(records)
    elif selected_module == "Flow Visualizer":
        render_flow_visualizer(records)
    elif selected_module == "Resource / Storage / Pressure":
        render_resource_pressure(records)
    elif selected_module == "Memory / Knowledge Explorer":
        render_memory_explorer(records)
    elif selected_module == "Freshness Map":
        render_freshness_map(records)
    elif selected_module == "Watchtower":
        render_watchtower(records)
    elif selected_module == "Architecture Department":
        render_architecture_department(records)
    elif selected_module == "System Mindmap":
        render_system_mindmap(records)
    else:
        render_command_center(records)


def render_dashboard_v3_foundation():
    records = v3_load_evidence()
    st.markdown("""
<style>
section[data-testid="stSidebar"] * {
    font-size: 14px !important;
    font-weight: 720 !important;
}

div[data-testid="stRadio"] label {
    padding: 10px 12px;
    border-radius: 10px;
}

div[data-testid="stRadio"] input:checked + div {
    font-weight: 900;
}
</style>
""", unsafe_allow_html=True)
    with st.sidebar:
        selected_module = render_v4_sidebar(records)
    render_v4_topbar(records, selected_module)
    render_tv_pulse()
    main(records, selected_module)
    st.caption(
        f"TITAN Control System | modules: {len(CONTROL_SYSTEM_SECTIONS)} | widgets: {sum(len(items) for items in V3_WIDGET_INVENTORY.values())} | truth sources: {len(V3_TRUTH_SOURCES)} | no runtime controls"
    )


render_dashboard_v3_foundation()
st.stop()


# =========================================================
# LEGACY / UNREACHABLE / DO NOT USE
# Active TITAN OS dashboard execution stops above at st.stop().
# This retained section is historical dashboard code only.
# Do not wire new UI, truth logic, or runtime behavior below.
# =========================================================

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
journal_truth_unification_data = runtime_status_data.get("journal_truth_unification", {})
dashboard_truth_consolidation_data = runtime_status_data.get("dashboard_truth_consolidation", {})
authoritative_components_data = dashboard_truth_consolidation_data.get("components_rendered_from_authoritative_truth", {})
paper_engine_runtime_data = get_paper_engine_runtime_status()
scanner_runtime_data = get_scanner_runtime_status()
live_price_monitor_runtime_data = get_live_price_monitor_runtime_status()
master_runtime_data, _ = get_runtime_payload("master_brain_status", "/".join(["data", "runtime", "master_brain_status.json"]))
rejection_heatmap_data = safe_read_json(REJECTION_HEATMAP_PATH, {})
sideways_analysis_data = safe_read_json(SIDEWAYS_ANALYSIS_PATH, {})
learning_evolution_truth_data = get_learning_evolution_truth_data()
real_latest_scan_time = scanner_runtime_data["timestamp"]


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

live_trades_count = int(first_number(
    dashboard_truth_consolidation_data.get("active_trade_count"),
    journal_truth_unification_data.get("canonical_open_trade_count") if isinstance(journal_truth_unification_data, dict) else None,
    default=get_live_trades_count(),
))
trade_lifecycle_reconciliation = get_trade_lifecycle_reconciliation()
active_live_trades_count = _reconciliation_count(trade_lifecycle_reconciliation, "active_live_trades")
learning_open_trades_count = _reconciliation_count(trade_lifecycle_reconciliation, "learning_open_trades")
stale_open_trades_count = _reconciliation_count(trade_lifecycle_reconciliation, "stale_open_trades")
eod_unresolved_trades_count = _reconciliation_count(trade_lifecycle_reconciliation, "eod_unresolved_trades")
active_live_trades_count = live_trades_count

# Performance stats and account PnL use journal.outcome_tracker closed rows only.
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
open_outcome_trades = live_trades_count

# Dashboard should show CLOSED trades in performance
total_trades = closed_trades

accuracy_percent = trade_result_stats["accuracy"]
trade_performance_percent = accuracy_percent

rr_display = "1:2"

master_brain_data = get_master_brain_status(
    github_time=None,
    scan_time=latest_dt(real_latest_scan_time, latest_phase_report_time),
    outcome_time=trade_result_stats.get("latest_outcome_time"),
)
master_brain_data["master_status"] = (
    dashboard_truth_consolidation_data.get("master_brain_display_status")
    or master_brain_data.get("master_status")
)
if master_brain_data["master_status"] in {"STALE", "STOPPED", "UNKNOWN", "MARKER_ONLY", "DEGRADED"}:
    master_brain_data["evolution_status"] = master_brain_data["master_status"]
    master_brain_data["evolution_sub"] = "Authoritative runtime truth; progress files are not runtime health"
master_shadow_data = get_master_shadow_dashboard_data()
master_shadow_data["status"] = (
    dashboard_truth_consolidation_data.get("shadow_command_center_status")
    or master_shadow_data.get("status")
)

master_activity_time = latest_dt(
    master_brain_data.get("last_activity"),
    latest_phase_report_time,
    real_latest_scan_time,
)

def authoritative_component_status(name, fallback="UNKNOWN"):
    record = authoritative_components_data.get(name)
    if isinstance(record, dict):
        return str(record.get("status") or fallback).upper()
    return fallback


def authoritative_component_sub(name, fallback=""):
    record = authoritative_components_data.get(name)
    if not isinstance(record, dict):
        return fallback
    source_file = record.get("source_file") or "unknown source"
    timestamp = record.get("source_timestamp") or "unknown timestamp"
    age = record.get("age_seconds")
    reason = record.get("reason") or "no reason"
    age_text = "unknown age" if age is None else f"{int(float(age))}s old"
    return f"Source: {source_file} | Updated: {timestamp} | Age: {age_text} | Reason: {reason}"


last_scan_age = scanner_runtime_data["age"]
scan_status = authoritative_component_status("scanner", scanner_runtime_data["status"])
titan_status = dashboard_truth_consolidation_data.get("dashboard_overall_status") or runtime_status_data.get("autonomous_runtime_status")
github_display_status = market_aware_status(github_status, market_open, "WAITING")
master_brain_display_status = dashboard_truth_consolidation_data.get("master_brain_display_status") or master_brain_data["master_status"]

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

scan_breakdown = get_latest_scan_breakdown(scanner_runtime_data, master_runtime_data, scan_health)
latest_stocks_checked = scan_breakdown["stocks_checked"]
latest_trend_passed = scan_breakdown["trend_passed"]
latest_strict_trend_passed = int(first_number(scan_breakdown.get("strict_trend_passed"), default=0))
latest_adaptive_trend_passed = int(first_number(scan_breakdown.get("adaptive_trend_passed"), default=0))
latest_momentum_passed = scan_breakdown["momentum_passed"]
latest_structure_passed = scan_breakdown["structure_passed"]
latest_entry_passed = scan_breakdown["entry_passed"]
latest_raw_breakout_ready = scan_breakdown["raw_breakout_ready_count"]
latest_qualified_breakout_ready = scan_breakdown["qualified_breakout_ready_count"]
latest_breakout_ready = scan_breakdown["breakout_ready_count"]
latest_final_passed = scan_breakdown["final_passed"]
latest_final_passed_display = "N/A" if latest_final_passed is None else f"{latest_final_passed:,}"
latest_health_alerts = scan_breakdown["alerts_this_scan"]
stocks_scanned = latest_stocks_checked
stocks_passed = int(latest_final_passed or 0)
latest_scan_health_age = last_scan_display_from_dt(scan_breakdown.get("timestamp"), market_open)
scanner_finished_at = parse_dt(scan_breakdown.get("scan_finished_at_ist")) or scan_breakdown.get("timestamp")
scanner_cycle_suffix_text = scanner_cycle_suffix(scan_breakdown.get("scanner_cycle_id"))
scanner_refresh_proof = (
    f"Last scanner cycle: {scanner_cycle_age_text(scanner_finished_at)} | "
    f"Scan duration: {scan_duration_text(scan_breakdown.get('scan_duration_seconds'))} | "
    f"Source: {scan_breakdown.get('source', 'UNKNOWN')}"
)
if scanner_cycle_suffix_text:
    scanner_refresh_proof = f"{scanner_refresh_proof} | Cycle: ...{scanner_cycle_suffix_text}"
if scan_breakdown.get("counter_confidence") and scan_breakdown.get("counter_confidence") != "HIGH":
    scanner_refresh_proof = f"{scanner_refresh_proof} | Counter confidence: {scan_breakdown.get('counter_confidence')}"
scanner_signature_text = scanner_cycle_suffix(scan_breakdown.get("data_signature")) or "none"
scanner_updated_text = (
    scanner_finished_at.strftime("%d %b %Y %I:%M:%S %p IST")
    if isinstance(scanner_finished_at, datetime)
    else "unavailable"
)
scanner_age_text = age_text_from_dt(scanner_finished_at)
scanner_truth_footer = (
    f"Scanner source: {scan_breakdown.get('source', 'UNKNOWN')} | "
    f"Cycle: {scan_breakdown.get('scanner_cycle_id') or 'none'} | "
    f"Updated: {scanner_updated_text} | "
    f"Signature: ...{scanner_signature_text} | "
    f"Age: {scanner_age_text}"
)
authoritative_freshness_lines = [
    f"{name}: status={authoritative_component_status(component)} | {authoritative_component_sub(component)}"
    for name, component in [
        ("Scanner", "scanner"),
        ("OHLC", "ohlc_health"),
        ("Setup", "setup_engine"),
        ("Master Brain", "master_brain"),
    ]
]
if scan_breakdown.get("scanner_truth_status") and scan_breakdown.get("scanner_truth_status") != "ACTIVE":
    scanner_statuses = scan_breakdown.get("scanner_truth_statuses") or [scan_breakdown.get("scanner_truth_status")]
    scanner_truth_footer = f"{scanner_truth_footer} | {' | '.join(scanner_statuses)}"
final_passed_subtitle = (
    scan_breakdown.get("dashboard_status_message")
    or (
        "Final count unavailable from current runtime output"
        if latest_final_passed is None
        else "Final quality filter not run in scanner-only mode."
        if scan_breakdown.get("scan_only") and latest_final_passed == 0
        else "No setups found"
        if latest_final_passed == 0
        else "Quality filter passed"
    )
)
breakout_ready_subtitle = (
    "Alias of breakout-ready scanner gate"
    if scan_breakdown.get("scan_only") and not scan_breakdown.get("entry_stage_available")
    else "Breakout ready"
)
scanner_input_warning = (
    "INPUT_UNCHANGED_WARNING"
    if scan_breakdown.get("repeated_data_signature")
    else None
)
trend_passed_subtitle = (
    f"Strict {latest_strict_trend_passed:,} + adaptive {latest_adaptive_trend_passed:,}"
    if latest_adaptive_trend_passed
    else "Strict trend pass"
)
if not scan_breakdown.get("is_fresh"):
    latest_scan_health_age = "Stale scan breakdown" if scan_breakdown.get("timestamp") else (
        "Market closed / research mode" if not market_open else "No live price scan yet"
    )

live_price_monitor_payload = live_price_monitor_runtime_data["payload"]
latest_live_price_checked = int(first_number(live_price_monitor_payload.get("symbols_checked"), default=0))
upstox_live_price_status = live_price_monitor_runtime_data["status"]
upstox_live_price_age = live_price_monitor_runtime_data["age"]


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

dashboard_restart_blockers = dashboard_truth_consolidation_data.get("restart_blockers") or []
status_card(
    "Dashboard Truth",
    dashboard_truth_consolidation_data.get("dashboard_overall_status", "UNKNOWN"),
    (
        f"restart_allowed: {str(dashboard_truth_consolidation_data.get('restart_allowed', False)).lower()} | "
        f"blockers: {', '.join(dashboard_restart_blockers) if dashboard_restart_blockers else 'none'}"
    ),
)


# =========================================================
# 1. TOP STATUS
# =========================================================

st.markdown("<div class='section'>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>🧠 Top Control Status</div>", unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)

with c1:
    status_card("TITAN Status", titan_status, "Authoritative runtime truth")

with c2:
    status_card("GitHub 5-Min Runner", github_display_status, github_data["message"])

with c3:
    status_card("Supabase Connectivity", supabase_status, "Not runtime health")

with c4:
    metric_card(
        "TITAN Heartbeat",
        runtime_status_data["heartbeat_age"],
        "Local authoritative runtime files",
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

legacy_open_rows_by_file = (
    journal_truth_unification_data.get("legacy_open_rows_by_file")
    if isinstance(journal_truth_unification_data, dict)
    else {}
)
legacy_quarantined_count = int(first_number(
    journal_truth_unification_data.get("legacy_quarantined_file_count")
    if isinstance(journal_truth_unification_data, dict)
    else None,
    default=0,
))
if legacy_quarantined_count or legacy_open_rows_by_file:
    legacy_open_total = sum(
        int(first_number(value, default=0))
        for value in (legacy_open_rows_by_file or {}).values()
    )
    small_status(
        "Journal Legacy Quarantine",
        "WARNING" if legacy_open_total else "ARCHIVE_ONLY",
        (
            f"Canonical active: {live_trades_count}, "
            f"legacy files: {legacy_quarantined_count}, "
            f"legacy OPEN rows ignored: {legacy_open_total}"
        ),
    )

st.markdown("<br>", unsafe_allow_html=True)
le1, le2, le3 = st.columns(3)
with le1:
    metric_card(
        "Top Performing Setup Type",
        learning_evolution_truth_data["top_setup_type"],
        f"Closed outcomes: {learning_evolution_truth_data['closed_outcome_count']}",
    )
    metric_card(
        "Weakest Setup Type",
        learning_evolution_truth_data["weakest_setup_type"],
        "Outcome-backed weakness",
    )
with le2:
    metric_card("Best Symbols", learning_evolution_truth_data["best_symbols"], "Highest outcome-backed win rate")
    metric_card("Weakest Symbols", learning_evolution_truth_data["weakest_symbols"], "Lowest outcome-backed win rate")
with le3:
    metric_card("Learning Confidence", learning_evolution_truth_data["learning_confidence_display"], learning_evolution_truth_data["status"])
    metric_card("Evolution Changes Today", f"{learning_evolution_truth_data['evolution_changes_today']:,}", "Strategy weight log entries")
    metric_card(
        "Reinforcement Learning",
        learning_evolution_truth_data["reinforcement_runtime_status"],
        learning_evolution_truth_data["reinforcement_runtime_source"],
    )
    metric_card(
        "Meta-Learning",
        learning_evolution_truth_data["meta_learning_runtime_status"],
        learning_evolution_truth_data["meta_learning_runtime_source"],
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
# 5. CAPABILITY PROGRESS
# =========================================================

st.markdown("<div class='section'>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>Capability Progress</div>", unsafe_allow_html=True)
st.caption("Capability progress is static readiness context only; it is not runtime health.")

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

r1, r2 = st.columns([1, 1])

with r1:
    small_status("Scan Engine", scan_status, authoritative_component_sub("scanner", f"Last scan: {last_scan_age}"))
    small_status("GitHub 5-Min Runner", github_display_status, f"Last run: {github_age}")
    small_status("Supabase Connectivity", supabase_status, "Not runtime health")
    small_status("Master Brain", master_brain_display_status, authoritative_component_sub("master_brain", f"Last activity: {master_brain_data['last_activity_age']}"))
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
    small_status(
        "Autonomous Runtime",
        runtime_status_data["autonomous_runtime_status"],
        runtime_status_data["autonomous_runtime_sub"],
    )
    small_status("News Engine", authoritative_component_status("news_intelligence", news_status), f"News: {news_gathered:,} · Latest: {news_memory_data['age']}")
    small_status("Telegram Alert Engine", telegram_status, telegram_status_sub)
    small_status("Learning / Evolution", learning_status, master_brain_data["evolution_sub"])
    small_status("Outcome Tracker", authoritative_component_status("outcome_tracker", outcome_tracker_status), f"Open: {open_outcome_trades}, Closed: {closed_trades}")

st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# 7. SCAN BREAKDOWN
# =========================================================

st.markdown("<div class='section'>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>🔍 Scan Breakdown · Why No Alerts?</div>", unsafe_allow_html=True)

if scan_breakdown.get("limited_runtime"):
    b1, b2, b3 = st.columns(3)

    with b1:
        metric_card("Stocks Checked", f"{latest_stocks_checked:,}", "Latest VPS scanner runtime")

    with b2:
        status_card("Scanner Status", scan_status, authoritative_component_sub("scanner", "Authoritative scanner truth"))

    with b3:
        metric_card("Last Scanner Update", latest_scan_health_age, "scanner_status timestamp")

    st.info(
        "Scanner runtime is active, but detailed gate breakdown is not available yet.\n\n"
        "Next VPS scan cycle will update this once scanner_status publishes gate counts."
    )
    st.caption(scanner_refresh_proof)
    st.caption(scanner_truth_footer)
    for freshness_line in authoritative_freshness_lines:
        st.caption(freshness_line)
    if scanner_input_warning:
        st.caption(scanner_input_warning)

elif scan_breakdown.get("has_data"):
    b1, b2, b3, b4, b5, b6, b7 = st.columns(7)

    with b1:
        metric_card("Stocks Checked", f"{latest_stocks_checked:,}", "Latest scan cycle")

    with b2:
        metric_card("Trend Passed", f"{latest_trend_passed:,}", trend_passed_subtitle)

    with b3:
        metric_card("Momentum Passed", f"{latest_momentum_passed:,}", "Strong momentum")

    with b4:
        metric_card("Structure Passed", f"{latest_structure_passed:,}", "Clean structure")

    with b5:
        metric_card("Raw Breakout Ready", f"{latest_raw_breakout_ready:,}", "Breakout condition only")

    with b6:
        metric_card("Qualified Breakout", f"{latest_qualified_breakout_ready:,}", breakout_ready_subtitle)

    with b7:
        metric_card("Final Passed", latest_final_passed_display, final_passed_subtitle)

    st.markdown("<br>", unsafe_allow_html=True)

    h1, h2, h3 = st.columns(3)

    with h1:
        status_card(
            "Upstox Live Price",
            upstox_live_price_status,
            f"Live price scan: {latest_live_price_checked}/5 · {upstox_live_price_age}"
        )

    with h2:
        metric_card("Alerts This Scan", f"{latest_health_alerts:,}", "Real alerts only")

    with h3:
        if live_trades_count > 0:
            trade_count_label = "Active Live Trades"
            trade_count_value = live_trades_count
            trade_count_subtitle = "Current-day OPEN_PENDING only"
        elif learning_open_trades_count > 0:
            trade_count_label = "Learning Watchlist Trades"
            trade_count_value = learning_open_trades_count
            trade_count_subtitle = "Paper/learning only; not live"
        else:
            trade_count_label = "Active Live Trades"
            trade_count_value = 0
            trade_count_subtitle = f"Stale/EOD unresolved: {stale_open_trades_count + eod_unresolved_trades_count}"
        metric_card(trade_count_label, f"{trade_count_value:,}", trade_count_subtitle)

    rejection_counts = rejection_heatmap_data.get("rejection_counts") if isinstance(rejection_heatmap_data, dict) else {}
    if isinstance(rejection_counts, dict) and rejection_counts:
        st.markdown("### Top Rejection Reasons")
        for reason, count in list(rejection_counts.items())[:5]:
            st.caption(f"{reason}: {count}")

    sideways_reasons = sideways_analysis_data.get("top_sideways_reasons") if isinstance(sideways_analysis_data, dict) else {}
    if isinstance(sideways_reasons, dict) and sideways_reasons:
        st.markdown("### Top Sideways Reasons")
        for reason, count in list(sideways_reasons.items())[:5]:
            st.caption(f"{reason}: {count}")

    st.caption(scanner_refresh_proof)
    st.caption(scanner_truth_footer)
    for freshness_line in authoritative_freshness_lines:
        st.caption(freshness_line)
    if scanner_input_warning:
        st.caption(scanner_input_warning)

else:
    st.caption("Awaiting VPS scanner breakdown")
    b1, b2, b3, b4, b5, b6, b7 = st.columns(7)

    with b1:
        metric_card("Stocks Checked", "0", "Awaiting VPS scanner breakdown")

    with b2:
        metric_card("Trend Passed", "0", "Awaiting VPS scanner breakdown")

    with b3:
        metric_card("Momentum Passed", "0", "Awaiting VPS scanner breakdown")

    with b4:
        metric_card("Structure Passed", "0", "Awaiting VPS scanner breakdown")

    with b5:
        metric_card("Raw Breakout Ready", "0", "Awaiting VPS scanner breakdown")

    with b6:
        metric_card("Qualified Breakout", "0", "Awaiting VPS scanner breakdown")

    with b7:
        metric_card("Final Passed", "0", "Awaiting VPS scanner breakdown")

    st.caption(scanner_refresh_proof)
    st.caption(scanner_truth_footer)
    for freshness_line in authoritative_freshness_lines:
        st.caption(freshness_line)

st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# FOOTER
# =========================================================

st.caption("TITAN Control System · Streamlit Cloud · GitHub Actions · Supabase Memory")
st.caption("REAL_PNL_QTY_SYNC_FIX_V1_ACTIVE")
