import json
from pathlib import Path

from engines.time_filter import current_bot_mode
from engines.news_intelligence_2_engine import build_news_intelligence_report
from intelligence.news_engine import run_news_engine
from utils.market_hours import as_ist_datetime


NEWS_PULSE_STATUS_PATH = Path("data") / "runtime" / "news_pulse_status.json"
LIGHT_NEWS_PULSE_STATUS_PATH = Path("data") / "runtime" / "light_news_pulse_status.json"
NEWS_INTELLIGENCE_STATUS_PATH = Path("data") / "runtime" / "news_intelligence_status.json"
NEWS_INTELLIGENCE_REPORT_PATH = Path("data") / "news_intelligence" / "latest_news_intelligence_2_report.json"


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _observed_titles(news_items, limit=5):
    observed_titles = []
    seen_titles = set()
    for item in news_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title or title in seen_titles:
            continue
        observed_titles.append(title)
        seen_titles.add(title)
        if len(observed_titles) == limit:
            break
    return observed_titles


def run_news_pulse(path=NEWS_PULSE_STATUS_PATH):
    now_ist = as_ist_datetime()
    mode = current_bot_mode(now_ist)

    try:
        news_items = run_news_engine() or []
        payload = {
            "timestamp_ist": now_ist.isoformat(),
            "mode": mode,
            "status": "NEWS_PULSE_FETCHED",
            "item_count": len(news_items),
            "latest_news_timestamp_ist": now_ist.isoformat(),
            "observed_titles": _observed_titles(news_items),
            "storage": "local_news_memory_and_runtime_status",
            "supabase_write": True,
            "trading_effect": False,
            "telegram_alerts": False,
            "trade_creation": False,
        }
    except Exception as exc:
        payload = {
            "timestamp_ist": now_ist.isoformat(),
            "mode": mode,
            "status": "NEWS_PULSE_ERROR",
            "item_count": None,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "storage": "runtime_status_only",
            "supabase_write": False,
            "trading_effect": False,
            "telegram_alerts": False,
            "trade_creation": False,
        }

    _write_json(path, payload)
    return payload


def run_light_news_pulse():
    return run_news_pulse(LIGHT_NEWS_PULSE_STATUS_PATH)


def run_news_intelligence(path=NEWS_INTELLIGENCE_STATUS_PATH):
    now_ist = as_ist_datetime()
    mode = current_bot_mode(now_ist)

    try:
        news_items = run_news_engine() or []
        report = build_news_intelligence_report(news_items=news_items, context={"runtime_mode": mode})
        report["timestamp_ist"] = now_ist.isoformat()
        report["runtime_mode"] = mode
        report["telegram_alerts"] = False
        report["trade_creation"] = False
        NEWS_INTELLIGENCE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        NEWS_INTELLIGENCE_REPORT_PATH.write_text(
            json.dumps(report, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        payload = {
            "timestamp_ist": now_ist.isoformat(),
            "mode": mode,
            "status": "NEWS_INTELLIGENCE_REFRESHED",
            "item_count": len(news_items),
            "latest_news_timestamp_ist": now_ist.isoformat(),
            "report_path": str(NEWS_INTELLIGENCE_REPORT_PATH).replace("\\", "/"),
            "observed_titles": _observed_titles(news_items),
            "trading_effect": False,
            "telegram_alerts": False,
            "trade_creation": False,
        }
    except Exception as exc:
        payload = {
            "timestamp_ist": now_ist.isoformat(),
            "mode": mode,
            "status": "NEWS_INTELLIGENCE_ERROR",
            "item_count": None,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "trading_effect": False,
            "telegram_alerts": False,
            "trade_creation": False,
        }

    _write_json(path, payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run_news_pulse(), indent=2, sort_keys=True))
