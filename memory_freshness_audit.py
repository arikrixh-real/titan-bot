import json
from datetime import datetime, timezone
from pathlib import Path

from utils.market_hours import IST, as_ist_datetime


MEMORY_DIR = Path("data") / "memory"
RUNTIME_DIR = Path("data") / "runtime"
REPORTS_DIR = Path("reports")
ACTIVE_FRESH_SECONDS = 24 * 60 * 60
STALE_SECONDS = 7 * 24 * 60 * 60

EXPECTED_MEMORY_ARTIFACTS = {
    "adaptive_intelligence_state": "legacy_engine",
    "advanced_regime_intelligence_memory": "legacy_engine",
    "cross_setup_memory": "legacy_engine",
    "lifecycle_memory": "legacy_engine",
    "master_shadow_memory": "legacy_engine",
    "strategy_family_memory": "legacy_engine",
    "reinforcement_learning_memory": "legacy_engine",
    "strategy_genome_memory": "legacy_engine",
    "historical_adaptive_intelligence_state": "legacy_memory",
}

KNOWN_LEGACY_REPORT_STEMS = {
    "adaptive_intelligence_report",
    "advanced_regime_intelligence_report",
    "cross_setup_report",
    "lifecycle_shadow_report",
    "master_shadow_command_center",
    "strategy_family_report",
    "strategy_genome_report",
}

SAFETY_FLAGS = {
    "advisory_only": True,
    "affects_live_ranking": False,
    "affects_execution": False,
    "broker_mutation": False,
    "telegram_mutation": False,
    "supabase_mutation": False,
    "live_order_behavior": False,
    "recommended_live_weight": 0.0,
    "rank_adjustment": 0.0,
}


def _read_json_diagnostic(path):
    try:
        if not path.exists():
            return {}, None
        if path.stat().st_size == 0:
            return {}, "empty_json_file"
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, str(exc)
    if not isinstance(payload, dict):
        return {}, "json_root_not_object"
    return payload, None


def _parse_timestamp(value):
    if value is None or value == "":
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
        "timestamp_ist",
        "last_updated_ist",
        "last_completed_at_ist",
        "scan_finished_at_ist",
        "timestamp_utc",
        "last_updated",
        "updated_at",
        "created_at",
        "timestamp",
    ):
        parsed = _parse_timestamp(payload.get(key))
        if parsed is not None:
            return parsed
    return None


def _file_timestamp(path):
    try:
        if not path.exists():
            return None
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone(IST)
    except OSError:
        return None


def _age_seconds(path, payload, now_ist):
    timestamp = _payload_timestamp(payload) or _file_timestamp(path)
    if timestamp is None:
        return None, None
    return timestamp, max(0.0, (now_ist - timestamp).total_seconds())


def _classification_for(path, payload, error, now_ist, source_type):
    stem = path.stem
    if error:
        return "CORRUPTED"
    timestamp, age = _age_seconds(path, payload, now_ist)
    if source_type == "runtime_status":
        return "GENERATED_RUNTIME"
    if source_type == "report":
        if "memory_consolidation" in stem or stem in KNOWN_LEGACY_REPORT_STEMS:
            return "ADVISORY_ONLY"
        return "ORPHAN"
    if payload.get("generated_baseline") and payload.get("status") == "GENERATED_BASELINE":
        return "LEGACY_VISIBLE"
    if stem not in EXPECTED_MEMORY_ARTIFACTS:
        return "ORPHAN"
    if age is None or age > STALE_SECONDS:
        return "STALE"
    if age > ACTIVE_FRESH_SECONDS or EXPECTED_MEMORY_ARTIFACTS.get(stem, "").startswith("legacy"):
        return "LEGACY_VISIBLE"
    return "ACTIVE"


def _artifact_record(path, now_ist, source_type):
    payload = {}
    error = None
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload, error = _read_json_diagnostic(path)
    timestamp, age = _age_seconds(path, payload, now_ist)
    classification = _classification_for(path, payload, error, now_ist, source_type)
    return {
        "name": path.stem,
        "path": str(path).replace("\\", "/"),
        "source_type": source_type,
        "classification": classification,
        "present": path.exists(),
        "timestamp_ist": timestamp.isoformat() if timestamp else None,
        "age_seconds": round(age, 3) if age is not None else None,
        "stale": classification == "STALE",
        "legacy_visible": classification == "LEGACY_VISIBLE",
        "corrupted": classification == "CORRUPTED",
        "error": error,
        "status": payload.get("overall_status") or payload.get("status"),
        "advisory_only": True,
    }


def discover_memory_freshness(now=None):
    now_ist = as_ist_datetime(now)
    artifacts = []

    for path in sorted(MEMORY_DIR.glob("*.json")):
        artifacts.append(_artifact_record(path, now_ist, "memory"))

    for path in sorted(RUNTIME_DIR.glob("*status*.json")):
        artifacts.append(_artifact_record(path, now_ist, "runtime_status"))

    for path in sorted(REPORTS_DIR.glob("*.json")) + sorted(REPORTS_DIR.glob("*.txt")):
        stem = path.stem
        if "memory" in stem or stem in KNOWN_LEGACY_REPORT_STEMS or "report" in stem:
            artifacts.append(_artifact_record(path, now_ist, "report"))

    present_memory_names = {Path(item["path"]).stem for item in artifacts if item["source_type"] == "memory"}
    missing = []
    for stem in sorted(EXPECTED_MEMORY_ARTIFACTS):
        if stem not in present_memory_names:
            missing.append(
                {
                    "name": stem,
                    "path": str((MEMORY_DIR / f"{stem}.json")).replace("\\", "/"),
                    "source_type": "memory",
                    "classification": "MISSING",
                    "present": False,
                    "timestamp_ist": None,
                    "age_seconds": None,
                    "stale": False,
                    "legacy_visible": False,
                    "corrupted": False,
                    "error": "missing_expected_memory_file",
                    "status": "MISSING",
                    "advisory_only": True,
                }
            )

    return {
        "generated_at_ist": now_ist.isoformat(),
        "artifacts": artifacts + missing,
        "safety_flags": dict(SAFETY_FLAGS),
    }
