import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

try:
    from supabase import create_client
except Exception:
    create_client = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.market_hours import IST, is_trade_window

SCANNER_STATUS_PATH = ROOT / "data" / "runtime" / "scanner_status.json"
RUNTIME_STATUS_TABLE = "runtime_status"
SCANNER_STALE_SECONDS = 7 * 60
SIGNATURE_REPEAT_WARNING_CYCLES = 3
COUNTER_KEYS = [
    "stocks_checked",
    "trend_passed",
    "momentum_passed",
    "structure_passed",
    "breakout_ready_count",
    "entry_passed",
    "final_passed",
]


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def parse_dt(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed.astimezone(IST)
    except Exception:
        return None


def payload_dt(payload):
    if not isinstance(payload, dict):
        return None
    return parse_dt(
        payload.get("timestamp_ist")
        or payload.get("scanner_timestamp")
        or payload.get("scan_finished_at_ist")
        or payload.get("generated_at")
        or payload.get("updated_at")
        or payload.get("created_at")
        or payload.get("timestamp")
    )


def age_seconds(payload):
    timestamp = payload_dt(payload)
    if not timestamp:
        return None
    return max((datetime.now(IST) - timestamp).total_seconds(), 0)


def first_int(payload, *keys):
    for key in keys:
        value = payload.get(key) if isinstance(payload, dict) else None
        if value in (None, ""):
            continue
        try:
            return int(float(value))
        except Exception:
            continue
    return 0


def summarize_payload(payload, source):
    payload = payload if isinstance(payload, dict) else {}
    return {
        "source": source,
        "timestamp": (payload_dt(payload).isoformat() if payload_dt(payload) else None),
        "age_seconds": round(age_seconds(payload), 3) if age_seconds(payload) is not None else None,
        "scanner_cycle_id": payload.get("scanner_cycle_id"),
        "data_signature": payload.get("data_signature"),
        "scan_duration_seconds": payload.get("scan_duration_seconds"),
        "stocks_checked": first_int(payload, "stocks_checked"),
        "trend_passed": first_int(payload, "trend_passed", "trend_passed_count"),
        "momentum_passed": first_int(payload, "momentum_passed", "momentum_passed_count"),
        "structure_passed": first_int(payload, "structure_passed", "structure_passed_count"),
        "breakout_ready": first_int(payload, "breakout_ready_count", "entry_passed"),
        "final_passed": first_int(payload, "final_passed", "final_passed_count"),
    }


def get_supabase_payload():
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key or create_client is None:
        return {}, "SUPABASE_UNAVAILABLE"
    try:
        client = create_client(url, key)
        result = (
            client.table(RUNTIME_STATUS_TABLE)
            .select("payload,timestamp_ist")
            .eq("status_key", "scanner_status")
            .limit(1)
            .execute()
        )
        rows = result.data if isinstance(result.data, list) else []
        if not rows or not isinstance(rows[0], dict):
            return {}, "SUPABASE_NO_SCANNER_ROW"
        payload = rows[0].get("payload")
        if not isinstance(payload, dict):
            return {}, "SUPABASE_BAD_PAYLOAD"
        payload = dict(payload)
        if rows[0].get("timestamp_ist") and not payload.get("timestamp_ist"):
            payload["timestamp_ist"] = rows[0].get("timestamp_ist")
        return payload, "SUPABASE_RUNTIME_STATUS_SCANNER"
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}, "SUPABASE_READ_ERROR"


def ohlc_stale(payload):
    pipeline = payload.get("pipeline_health") if isinstance(payload.get("pipeline_health"), dict) else {}
    data_health = payload.get("scanner_data_health") if isinstance(payload.get("scanner_data_health"), dict) else {}
    return bool(
        payload.get("ohlc_fallback_required")
        or payload.get("stale_data_warning")
        or pipeline.get("ohlc_stale")
        or data_health.get("ohlc_stale")
        or str(data_health.get("stale_policy") or payload.get("stale_policy") or "").upper().startswith("STALE")
    )


def repeat_count(payload):
    for key in [
        "repeated_data_signature_count",
        "same_data_signature_cycles",
        "data_signature_repeat_count",
        "signature_repeat_count",
    ]:
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            return int(float(value))
        except Exception:
            continue
    return 1 if payload.get("repeated_data_signature") else 0


def scanner_flags(payload):
    off_hours = not is_trade_window()
    age = age_seconds(payload)
    stale = bool(age is None or age > SCANNER_STALE_SECONDS)
    stale_ohlc = ohlc_stale(payload)
    if off_hours:
        stale = False
        stale_ohlc = False
    repeats = repeat_count(payload)
    return {
        "market_open": not off_hours,
        "stale": stale,
        "stale_status": "SCAN_STALE" if stale else "OK",
        "ohlc_stale": stale_ohlc,
        "ohlc_status": "SCAN_ONLY_STALE_OHLC" if stale_ohlc else "OK",
        "repeated_signature": repeats >= SIGNATURE_REPEAT_WARNING_CYCLES,
        "repeat_status": "INPUT_UNCHANGED_WARNING" if repeats >= SIGNATURE_REPEAT_WARNING_CYCLES else "OK",
        "repeat_count": repeats,
    }


def comparable(summary):
    return {key: summary.get(key) for key in [
        "scanner_cycle_id",
        "data_signature",
        "stocks_checked",
        "trend_passed",
        "momentum_passed",
        "structure_passed",
        "breakout_ready",
        "final_passed",
    ]}


def main():
    local_payload = read_json(SCANNER_STATUS_PATH)
    supabase_payload, supabase_source = get_supabase_payload()
    if supabase_source == "SUPABASE_RUNTIME_STATUS_SCANNER" and supabase_payload:
        dashboard_payload = supabase_payload
        dashboard_source = supabase_source
    else:
        dashboard_payload = local_payload
        dashboard_source = "LOCAL_RUNTIME_SCANNER_STATUS_JSON" if local_payload else "UNAVAILABLE"

    local_summary = summarize_payload(local_payload, "LOCAL_RUNTIME_SCANNER_STATUS_JSON")
    supabase_summary = summarize_payload(supabase_payload, supabase_source)
    dashboard_summary = summarize_payload(dashboard_payload, dashboard_source)
    truth_source = supabase_summary if supabase_source == "SUPABASE_RUNTIME_STATUS_SCANNER" else local_summary
    mismatch = comparable(dashboard_summary) != comparable(truth_source)

    print("=== latest runtime scanner file values ===")
    print(json.dumps(local_summary, indent=2, sort_keys=True))
    print("\n=== latest Supabase scanner values ===")
    print(json.dumps(supabase_summary, indent=2, sort_keys=True))
    if supabase_source == "SUPABASE_READ_ERROR":
        print(f"Supabase read error: {supabase_payload.get('error')}")
    print("\n=== dashboard-read values ===")
    print(json.dumps(dashboard_summary, indent=2, sort_keys=True))
    print("\n=== checks ===")
    flags = scanner_flags(dashboard_payload)
    print(f"mismatch: {'YES' if mismatch else 'NO'}")
    print(f"stale: {'YES' if flags['stale'] else 'NO'} ({flags['stale_status']})")
    print(f"repeated_signature: {'YES' if flags['repeated_signature'] else 'NO'} ({flags['repeat_status']}, count={flags['repeat_count']})")
    print(f"ohlc_stale: {'YES' if flags['ohlc_stale'] else 'NO'} ({flags['ohlc_status']})")
    print(f"market_open: {'YES' if flags['market_open'] else 'NO'}")


if __name__ == "__main__":
    main()
