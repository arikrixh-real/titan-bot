import json
from pathlib import Path

from engines.time_filter import current_bot_mode
from intelligence.news_engine import get_stock_news
from utils.market_hours import as_ist_datetime


NEWS_PULSE_STATUS_PATH = Path("data") / "runtime" / "news_pulse_status.json"


def run_news_pulse(path=NEWS_PULSE_STATUS_PATH):
    now_ist = as_ist_datetime()
    mode = current_bot_mode(now_ist)

    try:
        news_items = get_stock_news() or []
        sample_titles = []
        seen_titles = set()
        for item in news_items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            if not title or title in seen_titles:
                continue
            sample_titles.append(title)
            seen_titles.add(title)
            if len(sample_titles) == 5:
                break
        payload = {
            "timestamp_ist": now_ist.isoformat(),
            "mode": mode,
            "status": "NEWS_PULSE_FETCHED",
            "item_count": len(news_items),
            "sample_titles": sample_titles,
            "storage": "runtime_status_only",
            "supabase_write": False,
            "trading_effect": False,
        }
    except Exception as exc:
        payload = {
            "timestamp_ist": now_ist.isoformat(),
            "mode": mode,
            "status": "NEWS_PULSE_ERROR",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "storage": "runtime_status_only",
            "supabase_write": False,
            "trading_effect": False,
        }

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_news_pulse(), indent=2, sort_keys=True))
