import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

from memory_freshness_audit import SAFETY_FLAGS
from utils.market_hours import IST, as_ist_datetime


RUNTIME_DIR = Path("data") / "runtime"
MEMORY_DIR = Path("data") / "memory"
REPORTS_DIR = Path("reports")
LEGACY_VISIBILITY_PATH = RUNTIME_DIR / "legacy_engine_visibility_status.json"
STALE_SECONDS = 7 * 24 * 60 * 60

LEGACY_ENGINES = {
    "execution_engine": {
        "module": "titan_master_brain.execution_engine",
        "status": RUNTIME_DIR / "execution_engine_status.json",
    },
    "reinforcement_learning": {
        "module": "engines.reinforcement_learning_layer",
        "status": RUNTIME_DIR / "reinforcement_learning_status.json",
        "memory": MEMORY_DIR / "reinforcement_learning_memory.json",
        "report": REPORTS_DIR / "phase20_reinforcement_learning_report.txt",
    },
    "adaptive_intelligence": {
        "module": "engines.adaptive_intelligence",
        "memory": MEMORY_DIR / "adaptive_intelligence_state.json",
        "report": REPORTS_DIR / "adaptive_intelligence_report.txt",
    },
    "advanced_regime_intelligence": {
        "module": "engines.advanced_regime_intelligence",
        "memory": MEMORY_DIR / "advanced_regime_intelligence_memory.json",
        "report": REPORTS_DIR / "advanced_regime_intelligence_report.txt",
    },
    "lifecycle_memory": {
        "module": "engines.trade_lifecycle_intelligence",
        "memory": MEMORY_DIR / "lifecycle_memory.json",
        "report": REPORTS_DIR / "lifecycle_shadow_report.txt",
    },
    "cross_setup_memory": {
        "module": "engines.cross_setup_intelligence",
        "memory": MEMORY_DIR / "cross_setup_memory.json",
        "report": REPORTS_DIR / "cross_setup_report.txt",
    },
    "master_shadow_memory": {
        "module": "engines.master_shadow_command_center",
        "memory": MEMORY_DIR / "master_shadow_memory.json",
        "report": REPORTS_DIR / "master_shadow_command_center.txt",
    },
    "strategy_family_memory": {
        "module": "engines.strategy_family_memory",
        "memory": MEMORY_DIR / "strategy_family_memory.json",
        "report": REPORTS_DIR / "strategy_family_report.txt",
    },
}


def _read_json(path):
    try:
        if not path or not Path(path).exists():
            return {}
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": str(exc)}
    return payload if isinstance(payload, dict) else {"_read_error": "json_root_not_object"}


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
        if not path or not Path(path).exists():
            return None
        return datetime.fromtimestamp(Path(path).stat().st_mtime, tz=timezone.utc).astimezone(IST)
    except OSError:
        return None


def _module_visible(module_name):
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def _engine_visibility(name, spec, now_ist):
    artifact_paths = []
    payloads = {}
    for key in ("status", "memory", "report"):
        path = spec.get(key)
        if path:
            artifact_paths.append(path)
            if Path(path).suffix.lower() == ".json":
                payloads[key] = _read_json(path)

    present_paths = [path for path in artifact_paths if Path(path).exists()]
    timestamps = []
    for key, payload in payloads.items():
        timestamp = _payload_timestamp(payload) or _file_timestamp(spec.get(key))
        if timestamp:
            timestamps.append(timestamp)
    for path in present_paths:
        timestamp = _file_timestamp(path)
        if timestamp:
            timestamps.append(timestamp)

    latest = max(timestamps) if timestamps else None
    age = max(0.0, (now_ist - latest).total_seconds()) if latest else None
    module_visible = _module_visible(spec.get("module", ""))
    connected = bool(module_visible or present_paths)
    stale = bool(not connected or age is None or age > STALE_SECONDS)

    if not connected:
        status = "MISSING"
    elif stale:
        status = "LEGACY_VISIBLE_STALE"
    elif spec.get("status") and Path(spec["status"]).exists():
        status = "VISIBLE_STATUS"
    else:
        status = "VISIBLE_ARTIFACT_ONLY"

    return {
        "engine": name,
        "connected": connected,
        "connected_visibility_only": connected,
        "active_runtime_worker": False,
        "status": status,
        "stale": stale,
        "latest_timestamp_ist": latest.isoformat() if latest else None,
        "age_seconds": round(age, 3) if age is not None else None,
        "module": spec.get("module"),
        "module_visible": module_visible,
        "artifact_paths": [str(path).replace("\\", "/") for path in present_paths],
        "missing_expected_artifacts": [
            str(path).replace("\\", "/") for path in artifact_paths if not Path(path).exists()
        ],
        "advisory_only": True,
        "affects_live_ranking": False,
        "affects_execution": False,
    }


def build_legacy_engine_visibility(path=None, now=None):
    if path is None:
        path = LEGACY_VISIBILITY_PATH
    now_ist = as_ist_datetime(now)
    engines = {
        name: _engine_visibility(name, spec, now_ist)
        for name, spec in LEGACY_ENGINES.items()
    }
    connected = [name for name, item in engines.items() if item["connected"]]
    stale = [name for name, item in engines.items() if item["stale"]]
    missing = [name for name, item in engines.items() if not item["connected"]]
    total = len(engines) or 1
    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "overall_status": "WARNING" if stale or missing else "PASS",
        "legacy_visibility_score": round((len(connected) / total) * 100, 2),
        "connected_legacy_engines": connected,
        "stale_legacy_engines": stale,
        "missing_legacy_engines": missing,
        "engines": engines,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(build_legacy_engine_visibility(), indent=2, sort_keys=True))
