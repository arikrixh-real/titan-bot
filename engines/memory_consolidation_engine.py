"""
TITAN Phase 36 - Memory Consolidation Engine

Consolidates memory into summaries, indexes, buckets, and archives without
deleting or rewriting core TITAN memory sources. Never places orders.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List


BASE_DIR = os.path.join("data", "memory_consolidation")
REPORT_PATH = os.path.join(BASE_DIR, "latest_memory_consolidation_report.json")
STRATEGIC_INDEX_PATH = os.path.join(BASE_DIR, "strategic_memory_index.json")
REGIME_BUCKETS_PATH = os.path.join(BASE_DIR, "regime_memory_buckets.json")
IMPORTANT_PATTERNS_PATH = os.path.join(BASE_DIR, "important_patterns.json")
BAD_PATTERN_ARCHIVE_PATH = os.path.join(BASE_DIR, "bad_pattern_archive.json")


def safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return float(default)
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        return float(value)
    except Exception:
        return float(default)


def safe_text(value, default=""):
    try:
        if value is None:
            return str(default)
        return str(value).strip()
    except Exception:
        return str(default)


def safe_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    return [value]


def clamp(value, min_value=0.0, max_value=100.0):
    try:
        value = safe_float(value, min_value)
        return max(float(min_value), min(float(max_value), value))
    except Exception:
        return float(min_value)


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _memory_items(memory_data=None):
    if isinstance(memory_data, list):
        return [item for item in memory_data if isinstance(item, dict)]
    if isinstance(memory_data, dict):
        items = []
        for key in ("items", "memories", "patterns", "trades", "data"):
            value = memory_data.get(key)
            if isinstance(value, list):
                items.extend(item for item in value if isinstance(item, dict))
        if not items:
            for key, value in memory_data.items():
                if isinstance(value, dict):
                    item = dict(value)
                    item.setdefault("memory_key", key)
                    items.append(item)
        return items
    return []


def _trade_items(trade_history=None):
    return [item for item in safe_list(trade_history) if isinstance(item, dict)]


def _is_win(item):
    item = _as_dict(item)
    result = safe_text(item.get("result") or item.get("outcome") or item.get("status")).upper()
    pnl = safe_float(item.get("pnl") or item.get("pnl_pct") or item.get("profit"), 0.0)
    return result in {"WIN", "PROFIT", "TARGET", "SUCCESS"} or pnl > 0.0


def _is_loss(item):
    item = _as_dict(item)
    result = safe_text(item.get("result") or item.get("outcome") or item.get("status")).upper()
    pnl = safe_float(item.get("pnl") or item.get("pnl_pct") or item.get("profit"), 0.0)
    return result in {"LOSS", "STOP", "STOP_LOSS", "FAILED"} or pnl < 0.0


def _pattern_name(item):
    item = _as_dict(item)
    return safe_text(
        item.get("pattern")
        or item.get("setup_type")
        or item.get("strategy")
        or item.get("family")
        or item.get("memory_key")
        or "UNKNOWN"
    ).upper()


def normalize_memory_inputs(memory_data=None, trade_history=None, context=None):
    context = _as_dict(context)
    memories = _memory_items(memory_data)
    trades = _trade_items(trade_history)
    return {
        "memory_items": memories,
        "trade_history": trades,
        "context": dict(context),
        "memory_count": len(memories),
        "trade_count": len(trades),
    }


def _data_mode(memory_data, trade_history, context):
    memory_count = len(_memory_items(memory_data))
    trade_count = len(_trade_items(trade_history))
    context = _as_dict(context)
    context_count = sum(1 for _, value in context.items() if value not in (None, "", [], {}))
    if memory_count >= 3 or trade_count >= 3 or (memory_count + trade_count >= 2 and context_count >= 2):
        return "REAL_MEMORY"
    if memory_count or trade_count or context_count:
        return "PROXY"
    return "INSUFFICIENT"


def compress_long_term_memory(memory_data=None):
    items = _memory_items(memory_data)
    by_pattern: Dict[str, Dict[str, Any]] = {}
    for item in items:
        pattern = _pattern_name(item)
        bucket = by_pattern.setdefault(pattern, {"pattern": pattern, "count": 0, "score_sum": 0.0, "examples": []})
        bucket["count"] += 1
        bucket["score_sum"] += clamp(item.get("score") or item.get("quality_score") or item.get("win_rate") or 50.0)
        if len(bucket["examples"]) < 3:
            bucket["examples"].append(item)
    summaries = []
    for bucket in by_pattern.values():
        summaries.append(
            {
                "pattern": bucket["pattern"],
                "count": bucket["count"],
                "average_score": round(clamp(bucket["score_sum"] / max(bucket["count"], 1)), 2),
                "examples_kept": len(bucket["examples"]),
            }
        )
    return {"original_count": len(items), "compressed_count": len(summaries), "pattern_summaries": summaries[:50]}


def preserve_important_patterns(memory_data=None, trade_history=None):
    candidates = _memory_items(memory_data) + _trade_items(trade_history)
    stats: Dict[str, Dict[str, Any]] = {}
    for item in candidates:
        pattern = _pattern_name(item)
        bucket = stats.setdefault(pattern, {"pattern": pattern, "wins": 0, "losses": 0, "score_sum": 0.0, "count": 0})
        bucket["count"] += 1
        bucket["score_sum"] += clamp(item.get("score") or item.get("quality_score") or 50.0)
        if _is_win(item):
            bucket["wins"] += 1
        if _is_loss(item):
            bucket["losses"] += 1
    important = []
    for bucket in stats.values():
        win_rate = (bucket["wins"] / max(bucket["wins"] + bucket["losses"], 1)) * 100.0
        avg_score = bucket["score_sum"] / max(bucket["count"], 1)
        priority = clamp((win_rate * 0.55) + (avg_score * 0.35) + min(bucket["count"], 10) * 1.0)
        if priority >= 55.0 or bucket["wins"] >= 2:
            important.append(
                {
                    "pattern": bucket["pattern"],
                    "priority_score": round(priority, 2),
                    "wins": bucket["wins"],
                    "losses": bucket["losses"],
                    "sample_count": bucket["count"],
                }
            )
    important.sort(key=lambda item: item.get("priority_score", 0.0), reverse=True)
    return {"important_count": len(important), "patterns": important[:50]}


def archive_bad_patterns(memory_data=None, trade_history=None):
    candidates = _memory_items(memory_data) + _trade_items(trade_history)
    stats: Dict[str, Dict[str, Any]] = {}
    for item in candidates:
        pattern = _pattern_name(item)
        bucket = stats.setdefault(pattern, {"pattern": pattern, "wins": 0, "losses": 0, "count": 0})
        bucket["count"] += 1
        if _is_win(item):
            bucket["wins"] += 1
        if _is_loss(item):
            bucket["losses"] += 1
    archive = []
    for bucket in stats.values():
        attempts = bucket["wins"] + bucket["losses"]
        loss_rate = (bucket["losses"] / max(attempts, 1)) * 100.0
        if bucket["losses"] >= 2 and loss_rate >= 55.0:
            archive.append(
                {
                    "pattern": bucket["pattern"],
                    "loss_rate": round(clamp(loss_rate), 2),
                    "wins": bucket["wins"],
                    "losses": bucket["losses"],
                    "archive_reason": "Repeated poor outcomes; de-prioritize recall.",
                }
            )
    archive.sort(key=lambda item: item.get("loss_rate", 0.0), reverse=True)
    return {"bad_pattern_count": len(archive), "patterns": archive[:50]}


def build_strategic_memory_index(memory_data=None, context=None):
    items = _memory_items(memory_data)
    index: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        strategy = _pattern_name(item)
        entry = {
            "memory_key": safe_text(item.get("memory_key") or item.get("id") or strategy),
            "score": round(clamp(item.get("score") or item.get("quality_score") or item.get("win_rate") or 50.0), 2),
            "regime": safe_text(item.get("regime") or item.get("market_regime") or "UNKNOWN").upper(),
        }
        index.setdefault(strategy, []).append(entry)
    for entries in index.values():
        entries.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    return {"strategy_count": len(index), "index": {key: value[:20] for key, value in index.items()}}


def calculate_memory_priority(memory_item=None, context=None):
    item = _as_dict(memory_item)
    context = _as_dict(context)
    reliability = clamp(item.get("reliability") or item.get("win_rate") or item.get("quality_score") or item.get("score") or 50.0)
    recency = clamp(item.get("recency_score") or item.get("recent_weight") or 50.0)
    current_regime = safe_text(context.get("market_regime") or context.get("regime")).upper()
    item_regime = safe_text(item.get("regime") or item.get("market_regime")).upper()
    regime_bonus = 10.0 if current_regime and item_regime == current_regime else 0.0
    penalty = 20.0 if _is_loss(item) else 0.0
    return round(clamp((reliability * 0.50) + (recency * 0.30) + regime_bonus + 10.0 - penalty), 2)


def build_regime_specific_memory_buckets(memory_data=None, context=None):
    items = _memory_items(memory_data)
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        regime = safe_text(item.get("regime") or item.get("market_regime") or "UNKNOWN").upper()
        buckets.setdefault(regime, []).append(
            {
                "pattern": _pattern_name(item),
                "priority": calculate_memory_priority(item, context),
                "score": round(clamp(item.get("score") or item.get("quality_score") or 50.0), 2),
            }
        )
    for entries in buckets.values():
        entries.sort(key=lambda item: item.get("priority", 0.0), reverse=True)
    return {"bucket_count": len(buckets), "buckets": {key: value[:25] for key, value in buckets.items()}}


def calculate_adaptive_recall_weight(memory_item=None, context=None):
    priority = calculate_memory_priority(memory_item, context)
    item = _as_dict(memory_item)
    sample = safe_float(item.get("sample_count") or item.get("count"), 1.0)
    sample_weight = clamp((sample / 10.0) * 100.0)
    weight = (priority * 0.75) + (sample_weight * 0.25)
    if _is_loss(item):
        weight -= 15.0
    return round(clamp(weight), 2)


def consolidate_experience_memory(memory_data=None, trade_history=None, context=None):
    trades = _trade_items(trade_history)
    wins = sum(1 for item in trades if _is_win(item))
    losses = sum(1 for item in trades if _is_loss(item))
    total = len(trades)
    win_rate = (wins / max(wins + losses, 1)) * 100.0
    important = preserve_important_patterns(memory_data, trade_history)
    bad = archive_bad_patterns(memory_data, trade_history)
    return {
        "trade_count": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(clamp(win_rate), 2),
        "important_pattern_count": important.get("important_count", 0),
        "bad_pattern_count": bad.get("bad_pattern_count", 0),
        "consolidation_state": "STABLE" if win_rate >= 45.0 and bad.get("bad_pattern_count", 0) <= important.get("important_count", 0) else "REVIEW",
    }


def _build_prioritization(memory_data=None, context=None):
    items = _memory_items(memory_data)
    ranked = []
    for item in items:
        ranked.append(
            {
                "pattern": _pattern_name(item),
                "priority": calculate_memory_priority(item, context),
                "recall_weight": calculate_adaptive_recall_weight(item, context),
            }
        )
    ranked.sort(key=lambda item: item.get("priority", 0.0), reverse=True)
    return {"item_count": len(ranked), "top_priorities": ranked[:50]}


def _build_recall_weights(memory_data=None, context=None):
    items = _memory_items(memory_data)
    weights = {}
    for index, item in enumerate(items):
        key = safe_text(item.get("memory_key") or item.get("id") or f"memory_{index}")
        weights[key] = calculate_adaptive_recall_weight(item, context)
    return {"weight_count": len(weights), "weights": weights}


def _write_json(path, payload):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
    except Exception:
        pass


def build_memory_consolidation_report(memory_data=None, trade_history=None, context=None):
    context = _as_dict(context)
    mode = _data_mode(memory_data, trade_history, context)
    explanations: List[str] = []

    compression = compress_long_term_memory(memory_data)
    important = preserve_important_patterns(memory_data, trade_history)
    bad_archive = archive_bad_patterns(memory_data, trade_history)
    strategic_index = build_strategic_memory_index(memory_data, context)
    prioritization = _build_prioritization(memory_data, context)
    regime_buckets = build_regime_specific_memory_buckets(memory_data, context)
    recall_weights = _build_recall_weights(memory_data, context)
    experience = consolidate_experience_memory(memory_data, trade_history, context)

    memory_count = len(_memory_items(memory_data))
    trade_count = len(_trade_items(trade_history))
    stable_points = 50.0
    stable_points += min(20.0, memory_count * 2.0)
    stable_points += min(15.0, trade_count * 1.0)
    stable_points += min(15.0, safe_float(important.get("important_count"), 0.0) * 3.0)
    stable_points -= min(25.0, safe_float(bad_archive.get("bad_pattern_count"), 0.0) * 5.0)

    warning = "NONE"
    if bad_archive.get("bad_pattern_count", 0) >= 5 and important.get("important_count", 0) == 0:
        warning = "SKIP"
    elif mode in {"INSUFFICIENT", "PROXY"} or bad_archive.get("bad_pattern_count", 0) > important.get("important_count", 0):
        warning = "REVIEW"

    if mode == "INSUFFICIENT":
        memory_quality = 50.0
        bias = "REVIEW"
        warning = "REVIEW"
        explanations.append("Insufficient memory data; neutral consolidation report created.")
    else:
        if warning == "SKIP":
            stable_points -= 12.0
            explanations.append("Bad-pattern archive dominates memory; soft penalty noted.")
        elif warning in {"REVIEW", "WAIT"}:
            stable_points -= 5.0
            explanations.append("Memory consolidation needs review; small soft penalty noted.")
        memory_quality = clamp(stable_points)
        bias = "STABLE" if memory_quality >= 65.0 and warning == "NONE" else "FRAGMENTED" if memory_quality < 45.0 else "REVIEW"
        explanations.append(f"{mode} consolidation used available memory, trade history, and context.")

    report = {
        "advisory_only": True,
        "research_only": True,
        "shadow_mode": True,
        "live_order_allowed": False,
        "live_rank_mutation_allowed": False,
        "pyramid_placement": "master_controller_memory_sidecar",
        "memory_data_mode": mode,
        "memory_compression": compression,
        "important_patterns": important,
        "bad_pattern_archive": bad_archive,
        "strategic_memory_index": strategic_index,
        "memory_prioritization": prioritization,
        "regime_memory_buckets": regime_buckets,
        "adaptive_recall_weights": recall_weights,
        "experience_consolidation": experience,
        "memory_quality_score": round(clamp(memory_quality), 2),
        "memory_bias": bias,
        "memory_warning": warning if warning in {"NONE", "WAIT", "SKIP", "REVIEW"} else "REVIEW",
        "live_order_allowed": False,
        "explanations": explanations,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

    _write_json(REPORT_PATH, report)
    _write_json(STRATEGIC_INDEX_PATH, strategic_index)
    _write_json(REGIME_BUCKETS_PATH, regime_buckets)
    _write_json(IMPORTANT_PATTERNS_PATH, important)
    _write_json(BAD_PATTERN_ARCHIVE_PATH, bad_archive)
    return report


if __name__ == "__main__":
    sample_memory_data = [
        {"id": "m1", "pattern": "breakout", "regime": "trend", "score": 72, "win_rate": 64, "sample_count": 8},
        {"id": "m2", "pattern": "reversal", "regime": "range", "score": 44, "result": "LOSS", "sample_count": 3},
        {"id": "m3", "pattern": "breakout", "regime": "trend", "score": 78, "result": "WIN", "sample_count": 6},
    ]
    sample_trade_history = [
        {"strategy": "breakout", "regime": "trend", "result": "WIN", "pnl_pct": 1.1},
        {"strategy": "breakout", "regime": "trend", "result": "WIN", "pnl_pct": 0.9},
        {"strategy": "reversal", "regime": "range", "result": "LOSS", "pnl_pct": -0.8},
        {"strategy": "reversal", "regime": "range", "result": "LOSS", "pnl_pct": -0.6},
    ]
    sample_context = {"market_regime": "trend", "trading_mode": "SELECTIVE"}
    print(json.dumps(build_memory_consolidation_report(sample_memory_data, sample_trade_history, sample_context), indent=2, sort_keys=True))
