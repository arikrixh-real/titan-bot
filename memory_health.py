import json
from pathlib import Path

from legacy_engine_visibility import build_legacy_engine_visibility
from memory_freshness_audit import SAFETY_FLAGS, discover_memory_freshness


MEMORY_HEALTH_PATH = Path("data") / "runtime" / "titan_memory_health.json"


def _names(records, classification):
    return [item["name"] for item in records if item.get("classification") == classification]


def _score(numerator, denominator):
    if denominator <= 0:
        return 100.0
    return round(max(0.0, min(100.0, (numerator / denominator) * 100.0)), 2)


def run_memory_health_check(path=None, now=None):
    if path is None:
        path = MEMORY_HEALTH_PATH
    freshness = discover_memory_freshness(now=now)
    records = freshness.get("artifacts") or []
    memory_records = [item for item in records if item.get("source_type") == "memory"]

    active = _names(memory_records, "ACTIVE")
    stale = _names(memory_records, "STALE")
    orphan = _names(memory_records, "ORPHAN")
    corrupted = _names(memory_records, "CORRUPTED")
    missing = _names(memory_records, "MISSING")
    legacy_visible = _names(memory_records, "LEGACY_VISIBLE")

    total_memory = len(memory_records)
    freshness_good = len(active) + len(legacy_visible)
    integrity_good = total_memory - len(corrupted) - len(missing)
    memory_freshness_score = _score(freshness_good, total_memory)
    memory_integrity_score = _score(integrity_good, total_memory)

    legacy_visibility = build_legacy_engine_visibility(now=now)
    missing_visibility = legacy_visibility.get("missing_legacy_engines") or []
    legacy_visibility_score = legacy_visibility.get("legacy_visibility_score", 0.0)

    if corrupted or memory_integrity_score < 70:
        overall_status = "FAIL"
    elif stale or orphan or missing or missing_visibility or legacy_visibility.get("stale_legacy_engines"):
        overall_status = "WARNING"
    else:
        overall_status = "PASS"

    payload = {
        "generated_at_ist": freshness.get("generated_at_ist"),
        "overall_status": overall_status,
        "total_memory_files": total_memory,
        "active_memory_files": len(active) + len(legacy_visible),
        "stale_memory_files": len(stale),
        "orphan_memory_files": len(orphan),
        "corrupted_memory_files": len(corrupted),
        "missing_expected_memory_files": len(missing),
        "memory_freshness_score": memory_freshness_score,
        "memory_integrity_score": memory_integrity_score,
        "legacy_visibility_score": legacy_visibility_score,
        "stale_memory_summary": stale[:100],
        "orphan_memory_summary": orphan[:100],
        "missing_visibility_summary": missing_visibility,
        "missing_expected_memory_summary": missing,
        "corrupted_memory_summary": corrupted,
        "classification_counts": {
            "ACTIVE": len(active),
            "STALE": len(stale),
            "LEGACY_VISIBLE": len(legacy_visible),
            "ORPHAN": len(orphan),
            "MISSING": len(missing),
            "CORRUPTED": len(corrupted),
            "GENERATED_RUNTIME": len(_names(records, "GENERATED_RUNTIME")),
            "ADVISORY_ONLY": len(_names(records, "ADVISORY_ONLY")),
        },
        "artifacts": records,
        "legacy_engine_visibility": {
            "path": "data/runtime/legacy_engine_visibility_status.json",
            "overall_status": legacy_visibility.get("overall_status"),
            "connected_legacy_engines": legacy_visibility.get("connected_legacy_engines") or [],
            "stale_legacy_engines": legacy_visibility.get("stale_legacy_engines") or [],
            "missing_legacy_engines": missing_visibility,
        },
        "safety_flags": dict(SAFETY_FLAGS),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_memory_health_check(), indent=2, sort_keys=True))
