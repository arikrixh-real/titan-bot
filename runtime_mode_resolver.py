import json
from datetime import datetime, timezone
from pathlib import Path

from engines.time_filter import current_bot_mode
from runtime_dependency_graph import SAFETY_FLAGS
from runtime_mode_router import runtime_mode_snapshot
from utils.market_hours import IST, as_ist_datetime


RUNTIME_DIR = Path("data") / "runtime"
CANONICAL_RUNTIME_MODE_PATH = RUNTIME_DIR / "canonical_runtime_mode.json"
RUNTIME_WARNING_RESOLUTION_STATUS_PATH = RUNTIME_DIR / "runtime_warning_resolution_status.json"

RUNTIME_FRESH_SECONDS = 15 * 60
MODE_SOURCES = {
    "daemon_health": RUNTIME_DIR / "daemon_health.json",
    "heartbeat": RUNTIME_DIR / "titan_heartbeat.json",
    "runtime_status": RUNTIME_DIR / "titan_runtime_status.json",
    "runtime_health": RUNTIME_DIR / "titan_authoritative_runtime_health.json",
    "scanner_status": RUNTIME_DIR / "scanner_status.json",
    "setup_engine_status": RUNTIME_DIR / "setup_engine_status.json",
    "master_brain_status": RUNTIME_DIR / "master_brain_status.json",
    "runtime_mode_status": RUNTIME_DIR / "runtime_mode_status.json",
}
MODE_ALIASES = {
    "INTELLIGENCE_MODE": "RESEARCH_MODE",
    "RESEARCH_ONLY": "RESEARCH_MODE",
    "READ_ONLY": "RESEARCH_MODE",
    "READ_ONLY_MASTER_BRAIN": "RESEARCH_MODE",
    "HEALTH": "HEALTH_ONLY",
    "FULL_RUNTIME_PIPELINE": "MARKET_MODE",
}
CANONICAL_MODE_PRIORITY = (
    "runtime_mode_status",
    "runtime_status",
    "runtime_health",
    "setup_engine_status",
    "master_brain_status",
    "scanner_status",
    "daemon_health",
    "heartbeat",
)


def _path_key(path):
    return str(Path(path)).replace("\\", "/")


def _read_json_safe(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": str(exc)}
    return payload if isinstance(payload, dict) else {"_read_error": "json_root_not_object"}


def _parse_timestamp(value):
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


def _payload_timestamp(payload):
    for key in (
        "generated_at_ist",
        "generated_at",
        "timestamp_ist",
        "scan_finished_at_ist",
        "last_completed_at_ist",
        "updated_at",
        "timestamp",
    ):
        parsed = _parse_timestamp(payload.get(key))
        if parsed:
            return parsed
    return None


def _file_timestamp(path):
    try:
        path = Path(path)
        if not path.exists():
            return None
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone(IST)
    except OSError:
        return None


def normalize_runtime_mode(mode):
    text = str(mode or "").strip().upper()
    if not text:
        return "UNKNOWN"
    return MODE_ALIASES.get(text, text)


def _extract_mode(payload):
    runtime_mode = payload.get("runtime_mode")
    if isinstance(runtime_mode, dict):
        for key in ("canonical_mode", "current_mode", "mode"):
            value = runtime_mode.get(key)
            if value:
                return value
    elif runtime_mode:
        return runtime_mode
    for key in ("canonical_mode", "current_mode", "mode", "scanner_mode"):
        value = payload.get(key)
        if value:
            return value
    return None


def _mode_source_record(name, path, now_ist):
    path = Path(path)
    payload = _read_json_safe(path)
    timestamp = _payload_timestamp(payload) or _file_timestamp(path)
    age = max(0.0, (now_ist - timestamp).total_seconds()) if timestamp else None
    present = path.exists()
    status = payload.get("overall_status") or payload.get("status") or ("PRESENT" if present else "MISSING")
    mode_authority_degraded = bool(
        name == "runtime_health"
        and (
            str(payload.get("runtime_owner") or "").lower() == "stale_lock_only"
            or str(status or "").upper() == "FAIL"
        )
    )
    fresh = bool(present and age is not None and age <= RUNTIME_FRESH_SECONDS and not mode_authority_degraded)
    raw_mode = _extract_mode(payload)
    return {
        "name": name,
        "path": _path_key(path),
        "present": present,
        "raw_mode": raw_mode,
        "normalized_mode": normalize_runtime_mode(raw_mode),
        "status": status,
        "mode_authority_degraded": mode_authority_degraded,
        "timestamp_ist": timestamp.isoformat() if timestamp else None,
        "age_seconds": round(age, 3) if age is not None else None,
        "fresh_seconds": RUNTIME_FRESH_SECONDS,
        "fresh": fresh,
        "stale": not fresh,
    }


def build_canonical_runtime_mode(path=CANONICAL_RUNTIME_MODE_PATH, now=None):
    now_ist = as_ist_datetime(now)
    try:
        schedule = runtime_mode_snapshot()
    except Exception:
        schedule = {
            "current_mode": normalize_runtime_mode(current_bot_mode(now_ist)),
            "generated_at": now_ist.isoformat(),
        }
    records = {
        name: _mode_source_record(name, source_path, now_ist)
        for name, source_path in MODE_SOURCES.items()
    }
    schedule_mode = normalize_runtime_mode(schedule.get("current_mode") or current_bot_mode(now_ist))
    if records["runtime_mode_status"].get("normalized_mode") == "UNKNOWN":
        records["runtime_mode_status"]["normalized_mode"] = schedule_mode
    records["runtime_mode_status"]["schedule_mode"] = schedule_mode

    fresh_modes = {
        name: record["normalized_mode"]
        for name, record in records.items()
        if record.get("fresh") and record.get("normalized_mode") != "UNKNOWN"
    }
    stale_modes = {
        name: record["normalized_mode"]
        for name, record in records.items()
        if record.get("stale") and record.get("normalized_mode") != "UNKNOWN"
    }

    canonical_source = None
    canonical_mode = None
    for name in CANONICAL_MODE_PRIORITY:
        record = records.get(name) or {}
        mode = record.get("normalized_mode")
        if record.get("fresh") and mode and mode != "UNKNOWN":
            canonical_source = name
            canonical_mode = mode
            break
    if canonical_mode is None:
        canonical_source = "schedule"
        canonical_mode = schedule_mode

    raw_conflicts = sorted(set(fresh_modes.values()) | set(stale_modes.values()))
    conflict_records = [
        {
            "source": name,
            "mode": mode,
            "fresh": bool(records.get(name, {}).get("fresh")),
            "stale": bool(records.get(name, {}).get("stale")),
        }
        for name, mode in sorted({**stale_modes, **fresh_modes}.items())
        if mode != canonical_mode
    ]
    stale_conflict_only = bool(conflict_records) and all(item["stale"] for item in conflict_records)
    resolution = "PASS"
    if len(set(fresh_modes.values())) > 1:
        resolution = "WARNING"
    elif conflict_records:
        resolution = "DOWNGRADED_STALE_RAW_MODE_CONFLICT"

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "canonical_mode": canonical_mode,
        "canonical_source": canonical_source,
        "resolution_status": resolution,
        "raw_modes": records,
        "fresh_modes": fresh_modes,
        "stale_modes": stale_modes,
        "raw_mode_values": raw_conflicts,
        "raw_conflicts_visible": conflict_records,
        "stale_conflict_only": stale_conflict_only,
        "topology_warning_reduction_allowed": stale_conflict_only and resolution != "WARNING",
        "schedule_mode": schedule_mode,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_runtime_warning_resolution_status(canonical=None, path=RUNTIME_WARNING_RESOLUTION_STATUS_PATH, now=None):
    now_ist = as_ist_datetime(now)
    canonical = canonical if isinstance(canonical, dict) else build_canonical_runtime_mode(now=now_ist)
    raw_conflicts = canonical.get("raw_conflicts_visible") or []
    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "runtime_warning_resolution_status": "PASS"
        if canonical.get("resolution_status") in {"PASS", "DOWNGRADED_STALE_RAW_MODE_CONFLICT"}
        else "WARNING",
        "canonical_mode": canonical.get("canonical_mode"),
        "canonical_source": canonical.get("canonical_source"),
        "conflicting_runtime_modes": {
            "raw_conflicts_visible": raw_conflicts,
            "resolved_by_canonical_mode": canonical.get("resolution_status") != "WARNING",
            "classification": canonical.get("resolution_status"),
        },
        "mutation_controls": {
            "daemon_restart": False,
            "process_kill": False,
            "artifact_delete": False,
            "broker_mutation": False,
            "telegram_mutation": False,
            "supabase_mutation": False,
            "dashboard_rendering_mutation": False,
            "scanner_selection_mutation": False,
            "execution_behavior_mutation": False,
            "ranking_mutation": False,
        },
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    canonical_payload = build_canonical_runtime_mode()
    build_runtime_warning_resolution_status(canonical=canonical_payload)
    print(json.dumps(canonical_payload, indent=2, sort_keys=True))
