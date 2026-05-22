from .io_utils import atomic_write_json, load_json
from .vault_paths import (
    CONFIDENCE_LESSONS_PATH,
    EXPERIENCE_INTELLIGENCE_SUMMARY_PATH,
    FAILURE_PATTERN_MEMORY_PATH,
    IMPORTED_EXPERIENCE_MEMORY_PATH,
    NO_TRADE_MEMORY_PATH,
    PROCESSED_INDEX_PATH,
    SETUP_RELIABILITY_MEMORY_PATH,
    STOCK_PERSONALITY_MEMORY_PATH,
)


def _safe_key(value, fallback="UNKNOWN"):
    text = str(value or "").strip()
    return text[:120] if text else fallback


def _bucket_score(value):
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if score >= 80:
        return "80_100"
    if score >= 60:
        return "60_79"
    if score >= 40:
        return "40_59"
    return "0_39"


def _empty_bucket(key):
    return {
        "key": key,
        "total": 0,
        "wins": 0,
        "losses": 0,
        "positive": 0,
        "negative": 0,
        "neutral": 0,
        "win_rate": None,
        "dominant_polarity": "UNKNOWN",
        "sample_lessons": [],
    }


def _add_lesson(bucket, lesson):
    bucket["total"] += 1
    outcome = str(lesson.get("trade_result") or lesson.get("outcome") or "").upper()
    polarity = str(lesson.get("polarity") or "").upper()
    if outcome == "WIN":
        bucket["wins"] += 1
    elif outcome == "LOSS":
        bucket["losses"] += 1
    if polarity == "POSITIVE":
        bucket["positive"] += 1
    elif polarity == "NEGATIVE":
        bucket["negative"] += 1
    else:
        bucket["neutral"] += 1
    if len(bucket["sample_lessons"]) < 5:
        bucket["sample_lessons"].append(
            {
                "lesson_type": lesson.get("lesson_type"),
                "symbol": lesson.get("symbol"),
                "setup_type": lesson.get("setup_type"),
                "regime": lesson.get("regime"),
                "outcome": lesson.get("outcome"),
                "polarity": lesson.get("polarity"),
                "text": lesson.get("text"),
                "validation_status": lesson.get("validation_status", "UNVALIDATED"),
                "trust_level": lesson.get("trust_level", "IMPORTED_UNVALIDATED"),
            }
        )


def _finalize_bucket(bucket):
    resolved = dict(bucket)
    total_resolved = resolved["wins"] + resolved["losses"]
    if total_resolved:
        resolved["win_rate"] = round(resolved["wins"] / total_resolved, 4)
    polarities = {
        "POSITIVE": resolved["positive"],
        "NEGATIVE": resolved["negative"],
        "NEUTRAL": resolved["neutral"],
    }
    resolved["dominant_polarity"] = max(polarities, key=polarities.get) if resolved["total"] else "UNKNOWN"
    return resolved


def _top_buckets(buckets, limit=25):
    return [
        _finalize_bucket(bucket)
        for bucket in sorted(
            buckets.values(),
            key=lambda item: (item["total"], item["positive"] + item["negative"]),
            reverse=True,
        )[:limit]
    ]


def _cluster(memory, predicate, key_func, limit=25):
    buckets = {}
    for lesson in memory:
        if not predicate(lesson):
            continue
        key = _safe_key(key_func(lesson))
        bucket = buckets.setdefault(key, _empty_bucket(key))
        _add_lesson(bucket, lesson)
    return _top_buckets(buckets, limit=limit)


def load_processed_index():
    return load_json(PROCESSED_INDEX_PATH, {"files": {}, "chunks": {}, "last_run": None})


def save_processed_index(index):
    atomic_write_json(PROCESSED_INDEX_PATH, index)


def load_imported_memory():
    return load_json(IMPORTED_EXPERIENCE_MEMORY_PATH, [])


def save_imported_memory(memory):
    atomic_write_json(IMPORTED_EXPERIENCE_MEMORY_PATH, memory)


def write_derived_memories(memory):
    setup = [item for item in memory if item.get("lesson_type") in {"setup_type", "trade_result", "entry_reason"}]
    stock = [item for item in memory if item.get("lesson_type") == "stock_behavior"]
    failure = [item for item in memory if item.get("lesson_type") in {"failure_success_reason", "trap_evidence"}]
    no_trade = [item for item in memory if item.get("lesson_type") == "no_trade_lesson"]
    confidence = [item for item in memory if item.get("lesson_type") == "confidence_lesson"]

    atomic_write_json(SETUP_RELIABILITY_MEMORY_PATH, setup)
    atomic_write_json(STOCK_PERSONALITY_MEMORY_PATH, stock)
    atomic_write_json(FAILURE_PATTERN_MEMORY_PATH, failure)
    atomic_write_json(NO_TRADE_MEMORY_PATH, no_trade)
    atomic_write_json(CONFIDENCE_LESSONS_PATH, confidence)


def write_experience_intelligence_summary(memory, stats=None, warnings=None):
    memory = [item for item in memory or [] if isinstance(item, dict)]
    payload = {
        "generated_at_source": "experience_vault_runner",
        "source_type": "EXTERNAL_EXPERIENCE",
        "trust_level": "IMPORTED_UNVALIDATED",
        "validation_status": "UNVALIDATED",
        "safety": {
            "summary_only": True,
            "native_memory_merge": False,
            "live_strategy_mutation": False,
            "direct_scoring_mutation": False,
            "broker_orders": False,
            "telegram_changes": False,
        },
        "run_stats": stats or {},
        "warning_count": len(warnings or []),
        "lesson_count": len(memory),
        "setup_reliability": _cluster(
            memory,
            lambda item: bool(item.get("setup_type")) or item.get("lesson_type") in {"setup_type", "trade_result", "entry_reason"},
            lambda item: item.get("setup_type") or item.get("value"),
        ),
        "regime_reliability": _cluster(
            memory,
            lambda item: bool(item.get("regime")),
            lambda item: item.get("regime"),
        ),
        "symbol_behavior_summaries": _cluster(
            memory,
            lambda item: bool(item.get("symbol")) or item.get("lesson_type") == "stock_behavior",
            lambda item: item.get("symbol") or item.get("stock_behavior"),
        ),
        "confidence_bucket_summaries": _cluster(
            memory,
            lambda item: item.get("confidence") is not None or item.get("score") is not None or item.get("lesson_type") == "confidence_lesson",
            lambda item: _bucket_score(item.get("confidence") if item.get("confidence") is not None else item.get("score")),
        ),
        "no_trade_clusters": _cluster(
            memory,
            lambda item: item.get("lesson_type") == "no_trade_lesson" or bool(item.get("no_trade_lesson")),
            lambda item: item.get("setup_type") or item.get("regime") or item.get("no_trade_lesson") or item.get("value"),
        ),
        "failure_clusters": _cluster(
            memory,
            lambda item: str(item.get("polarity") or "").upper() == "NEGATIVE"
            or str(item.get("trade_result") or item.get("outcome") or "").upper() == "LOSS"
            or item.get("lesson_type") in {"failure_success_reason", "trap_evidence"},
            lambda item: item.get("failure_success_reason") or item.get("setup_type") or item.get("trap_evidence") or item.get("value"),
        ),
    }
    atomic_write_json(EXPERIENCE_INTELLIGENCE_SUMMARY_PATH, payload)
    return payload
