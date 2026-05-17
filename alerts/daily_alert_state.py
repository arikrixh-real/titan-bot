import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
DAILY_ALERT_STATE_FILE = Path("state") / "daily_alert_state.json"
LEGACY_DAILY_ALERT_STATE_FILE = Path("data") / "daily_alert_state.json"


def today_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _read_state_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    return payload if isinstance(payload, dict) else {}


def _fresh_state(today: str) -> Dict[str, Any]:
    return {
        "date": today,
        "alerts_sent": 0,
        "messages": [],
        "alerted_keys": [],
    }


def _normalize_state(state: Dict[str, Any], today: str) -> Dict[str, Any]:
    if state.get("date") != today:
        return _fresh_state(today)

    normalized = dict(state)
    normalized["date"] = today

    try:
        normalized["alerts_sent"] = int(normalized.get("alerts_sent", 0))
    except Exception:
        normalized["alerts_sent"] = 0

    messages = normalized.get("messages", [])
    normalized["messages"] = messages if isinstance(messages, list) else []

    alerted_keys = normalized.get("alerted_keys", [])
    normalized["alerted_keys"] = alerted_keys if isinstance(alerted_keys, list) else []

    return normalized


def _merge_states(primary: Dict[str, Any], fallback: Dict[str, Any], today: str) -> Dict[str, Any]:
    primary = _normalize_state(primary, today)
    fallback = _normalize_state(fallback, today)

    messages = list(dict.fromkeys(primary.get("messages", []) + fallback.get("messages", [])))
    alerted_keys = list(dict.fromkeys(primary.get("alerted_keys", []) + fallback.get("alerted_keys", [])))

    primary["messages"] = messages
    primary["alerted_keys"] = alerted_keys
    primary["alerts_sent"] = max(
        int(primary.get("alerts_sent", 0)),
        int(fallback.get("alerts_sent", 0)),
        min(len(messages), 3),
        min(len(alerted_keys), 3),
    )
    return primary


def load_daily_alert_state() -> Dict[str, Any]:
    today = today_ist()
    canonical = _read_state_file(DAILY_ALERT_STATE_FILE)
    legacy = _read_state_file(LEGACY_DAILY_ALERT_STATE_FILE)

    if canonical and legacy:
        state = _merge_states(canonical, legacy, today)
    elif canonical:
        state = _normalize_state(canonical, today)
    elif legacy:
        state = _normalize_state(legacy, today)
    else:
        state = _fresh_state(today)

    save_daily_alert_state(state)
    return state


def save_daily_alert_state(state: Dict[str, Any]) -> None:
    today = today_ist()
    normalized = _normalize_state(state, today)
    DAILY_ALERT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    DAILY_ALERT_STATE_FILE.write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
