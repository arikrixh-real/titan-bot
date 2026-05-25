import json
from datetime import datetime, timezone
from pathlib import Path

from runtime_dependency_graph import SAFETY_FLAGS
from utils.market_hours import IST, as_ist_datetime


RUNTIME_DIR = Path("data") / "runtime"
MASTER_BRAIN_STATUS_PATH = RUNTIME_DIR / "master_brain_status.json"
SETUP_ENGINE_STATUS_PATH = RUNTIME_DIR / "setup_engine_status.json"
MASTER_BRAIN_RUNTIME_HEALTH_PATH = RUNTIME_DIR / "master_brain_runtime_health.json"
SETUP_ENGINE_RUNTIME_HEALTH_PATH = RUNTIME_DIR / "setup_engine_runtime_health.json"
FRESH_SECONDS = 15 * 60


def read_json_safe(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": str(exc)}
    return payload if isinstance(payload, dict) else {"_read_error": "json_root_not_object"}


def atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def parse_timestamp(value):
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc).astimezone(IST)
        text = str(value).strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed.astimezone(IST)
    except Exception:
        return None


def payload_timestamp(payload):
    for key in (
        "master_brain_last_success",
        "setup_last_success",
        "scan_finished_at_ist",
        "timestamp_ist",
        "generated_at_ist",
        "updated_at_ist",
        "timestamp",
    ):
        parsed = parse_timestamp(payload.get(key))
        if parsed is not None:
            return parsed
    return None


def _age_seconds(timestamp, now_ist):
    if timestamp is None:
        return None
    return max(0.0, (now_ist - timestamp).total_seconds())


def _success_status(payload):
    status = str(payload.get("status") or "").upper()
    if not status:
        return bool(payload)
    return not any(marker in status for marker in ("ERROR", "FAIL", "UNAVAILABLE", "STALE"))


def _classify_runtime_health(payload, age_seconds):
    if not payload or payload.get("_read_error"):
        return "UNAVAILABLE"
    if age_seconds is None or age_seconds > FRESH_SECONDS:
        return "STALE"
    status = str(payload.get("status") or "").upper()
    fallback = bool(payload.get("scan_only") or payload.get("fallback_reason") or payload.get("fallback_components"))
    if fallback or "FALLBACK" in status:
        return "FALLBACK_ACTIVE"
    if any(marker in status for marker in ("ERROR", "FAIL", "DEGRADED")):
        return "DEGRADED"
    return "ACTIVE"


def _freshness_confidence(health):
    if health == "ACTIVE":
        return "HIGH"
    if health in {"DEGRADED", "FALLBACK_ACTIVE"}:
        return "MEDIUM"
    if health in {"STALE", "UNAVAILABLE"}:
        return "LOW"
    return "UNKNOWN"


def enrich_master_brain_payload(payload, now=None):
    payload = dict(payload or {})
    now_ist = as_ist_datetime(now)
    timestamp = payload_timestamp(payload) or now_ist
    age_seconds = _age_seconds(timestamp, now_ist)
    health = _classify_runtime_health(payload, age_seconds)
    success_time = timestamp.isoformat() if _success_status(payload) else payload.get("master_brain_last_success")
    payload.setdefault("master_brain_cycle_id", payload.get("scan_id") or payload.get("scanner_cycle_id") or now_ist.isoformat())
    payload["master_brain_last_success"] = success_time
    payload["master_brain_runtime_mode"] = payload.get("runtime_mode") or payload.get("mode") or "UNKNOWN"
    payload["master_brain_runtime_health"] = health
    payload["master_brain_freshness_confidence"] = _freshness_confidence(health)
    return payload


def enrich_setup_engine_payload(payload, now=None):
    payload = dict(payload or {})
    now_ist = as_ist_datetime(now)
    timestamp = payload_timestamp(payload) or now_ist
    age_seconds = _age_seconds(timestamp, now_ist)
    health = _classify_runtime_health(payload, age_seconds)
    success_time = timestamp.isoformat() if _success_status(payload) else payload.get("setup_last_success")
    payload.setdefault("setup_cycle_id", payload.get("scan_id") or payload.get("scan_cycle_id") or now_ist.isoformat())
    payload["setup_last_success"] = success_time
    payload["setup_pipeline_health"] = "HEALTHY" if health == "ACTIVE" else health
    payload["setup_runtime_health"] = health
    payload["setup_freshness_confidence"] = _freshness_confidence(health)
    return payload


def build_master_brain_runtime_health(now=None, status_payload=None, status_path=MASTER_BRAIN_STATUS_PATH, output_path=MASTER_BRAIN_RUNTIME_HEALTH_PATH):
    now_ist = as_ist_datetime(now)
    payload = status_payload if isinstance(status_payload, dict) else read_json_safe(status_path)
    timestamp = payload_timestamp(payload)
    age = _age_seconds(timestamp, now_ist)
    health = _classify_runtime_health(payload, age)
    result = {
        "generated_at_ist": now_ist.isoformat(),
        "overall_status": "PASS" if health == "ACTIVE" else "WARNING",
        "master_brain_runtime_health": health,
        "master_brain_cycle_id": payload.get("master_brain_cycle_id") or payload.get("scan_id") or payload.get("scanner_cycle_id"),
        "master_brain_last_success": payload.get("master_brain_last_success") or (timestamp.isoformat() if _success_status(payload) and timestamp else None),
        "master_brain_runtime_mode": payload.get("master_brain_runtime_mode") or payload.get("runtime_mode") or payload.get("mode") or "UNKNOWN",
        "master_brain_freshness_confidence": _freshness_confidence(health),
        "status_timestamp_ist": timestamp.isoformat() if timestamp else None,
        "status_age_seconds": round(age, 3) if age is not None else None,
        "source_status": payload.get("status"),
        "source_present": bool(payload) and not payload.get("_read_error"),
        "fallback_reason": payload.get("fallback_reason"),
        "safety_flags": dict(SAFETY_FLAGS),
    }
    atomic_write_json(output_path, result)
    return result


def build_setup_engine_runtime_health(now=None, status_payload=None, status_path=SETUP_ENGINE_STATUS_PATH, output_path=SETUP_ENGINE_RUNTIME_HEALTH_PATH):
    now_ist = as_ist_datetime(now)
    payload = status_payload if isinstance(status_payload, dict) else read_json_safe(status_path)
    timestamp = payload_timestamp(payload)
    age = _age_seconds(timestamp, now_ist)
    health = _classify_runtime_health(payload, age)
    result = {
        "generated_at_ist": now_ist.isoformat(),
        "overall_status": "PASS" if health == "ACTIVE" else "WARNING",
        "setup_runtime_health": health,
        "setup_cycle_id": payload.get("setup_cycle_id") or payload.get("scan_id") or payload.get("scan_cycle_id"),
        "setup_last_success": payload.get("setup_last_success") or (timestamp.isoformat() if _success_status(payload) and timestamp else None),
        "setup_pipeline_health": payload.get("setup_pipeline_health") or ("HEALTHY" if health == "ACTIVE" else health),
        "setup_freshness_confidence": _freshness_confidence(health),
        "status_timestamp_ist": timestamp.isoformat() if timestamp else None,
        "status_age_seconds": round(age, 3) if age is not None else None,
        "source_status": payload.get("status"),
        "source_present": bool(payload) and not payload.get("_read_error"),
        "fallback_reason": payload.get("fallback_reason"),
        "safety_flags": dict(SAFETY_FLAGS),
    }
    atomic_write_json(output_path, result)
    return result
