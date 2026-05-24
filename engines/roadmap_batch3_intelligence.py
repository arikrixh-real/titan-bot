"""
TITAN Roadmap Batch 3 - Phases 44-47 advisory intelligence.

Persistent sidecars for temporal, breadth, crowd psychology, and narrative
memory. These engines read local TITAN artifacts only, write memory/status/report
files, and never mutate scanners, ranking, execution, Telegram, broker,
Supabase, dashboard, or live order behavior.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IST = ZoneInfo("Asia/Kolkata")
STATE_VERSION = "44-47.0"
MAX_HISTORY = 100
MAX_ITEMS = 12
MAX_FILE_BYTES = 1_500_000
MAX_RECORDS = 400

PHASE_PATHS = {
    "phase44": {
        "memory": PROJECT_ROOT / "data" / "memory" / "temporal_intelligence_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "temporal_intelligence_status.json",
        "report": PROJECT_ROOT / "reports" / "temporal_intelligence_report.txt",
    },
    "phase45": {
        "memory": PROJECT_ROOT / "data" / "memory" / "market_breadth_intelligence_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "market_breadth_intelligence_status.json",
        "report": PROJECT_ROOT / "reports" / "market_breadth_intelligence_report.txt",
    },
    "phase46": {
        "memory": PROJECT_ROOT / "data" / "memory" / "crowd_psychology_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "crowd_psychology_status.json",
        "report": PROJECT_ROOT / "reports" / "crowd_psychology_report.txt",
    },
    "phase47": {
        "memory": PROJECT_ROOT / "data" / "memory" / "market_narrative_intelligence_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "market_narrative_intelligence_status.json",
        "report": PROJECT_ROOT / "reports" / "market_narrative_intelligence_report.txt",
    },
}

INPUT_PATHS = {
    "historical_replay_progress": PROJECT_ROOT / "data" / "runtime" / "historical_replay_progress.json",
    "historical_experience_jsonl": PROJECT_ROOT / "data" / "experience_vault" / "imported_trade_logs" / "historical_experience_import.jsonl",
    "no_trade_report": PROJECT_ROOT / "data" / "no_trade" / "latest_no_trade_intelligence_report.json",
    "no_trade_memory": PROJECT_ROOT / "data" / "memory" / "no_trade_refinement_memory.json",
    "strategy_genome": PROJECT_ROOT / "data" / "memory" / "strategy_genome_memory.json",
    "meta_regime": PROJECT_ROOT / "data" / "memory" / "meta_regime_intelligence_state.json",
    "accuracy_validation": PROJECT_ROOT / "data" / "memory" / "accuracy_validation_state.json",
    "advanced_regime": PROJECT_ROOT / "data" / "memory" / "advanced_regime_intelligence_memory.json",
    "trap_memory": PROJECT_ROOT / "data" / "memory" / "trap_fakeout_memory.json",
    "phase8_narrative": PROJECT_ROOT / "data" / "memory" / "market_narrative_memory.json",
    "news_intelligence": PROJECT_ROOT / "data" / "news_intelligence" / "latest_news_intelligence_2_report.json",
    "news_batch": PROJECT_ROOT / "titan_brain" / "memory" / "news_batch_state.json",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ist() -> datetime:
    return datetime.now(IST)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        result = float(value)
        return result if math.isfinite(result) else default
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(_safe_float(value, default))
    except Exception:
        return default


def _safe_text(value: Any, default: str = "") -> str:
    try:
        text = str(value if value is not None else default).strip()
        return text if text else default
    except Exception:
        return default


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _score(value: float) -> float:
    return round(_clamp01(value), 4)


def _score100(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists() or path.stat().st_size == 0 or path.stat().st_size > MAX_FILE_BYTES:
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _read_jsonl(path: Path, limit: int = MAX_RECORDS) -> List[Dict[str, Any]]:
    try:
        if not path.exists() or path.stat().st_size > MAX_FILE_BYTES:
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
            except Exception:
                continue
        return rows
    except Exception:
        return []


def _load_inputs() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    payloads: Dict[str, Dict[str, Any]] = {}
    sources: Dict[str, Dict[str, Any]] = {}
    now_ts = datetime.now(timezone.utc).timestamp()
    for name, path in INPUT_PATHS.items():
        if name == "historical_experience_jsonl":
            continue
        payload = _read_json(path)
        payloads[name] = payload
        status = "MISSING"
        age_seconds = None
        try:
            if path.exists():
                age_seconds = round(max(0.0, now_ts - path.stat().st_mtime), 3)
                status = "OK" if payload else "EMPTY_OR_INVALID"
        except Exception:
            status = "STAT_ERROR"
        sources[name] = {
            "path": _relative(path),
            "available": bool(payload),
            "status": status,
            "age_seconds": age_seconds,
        }
    records = _read_jsonl(INPUT_PATHS["historical_experience_jsonl"])
    sources["historical_experience_jsonl"] = {
        "path": _relative(INPUT_PATHS["historical_experience_jsonl"]),
        "available": bool(records),
        "status": "OK" if records else "MISSING_OR_EMPTY",
        "record_count": len(records),
    }
    return payloads, sources, records


def _safety_flags() -> Dict[str, Any]:
    return {
        "advisory_only": True,
        "research_only": True,
        "shadow_mode": True,
        "affects_live_ranking": False,
        "affects_execution": False,
        "broker_mutation": False,
        "telegram_mutation": False,
        "supabase_mutation": False,
        "dashboard_mutation": False,
        "scanner_mutation": False,
        "live_order_behavior": False,
        "recommended_live_weight": 0.0,
        "rank_adjustment": 0.0,
    }


def _market_data_from_master(master_input: Dict[str, Any] | None, context: Dict[str, Any] | None) -> Dict[str, Any]:
    ctx = context if isinstance(context, dict) else {}
    master = master_input if isinstance(master_input, dict) else {}
    market_packet = master.get("market") if isinstance(master.get("market"), dict) else {}
    market_data = market_packet.get("data") if isinstance(market_packet.get("data"), dict) else {}
    merged = dict(market_data)
    for key in (
        "index_breadth",
        "sector_strength",
        "sector_rankings",
        "sector_rotation",
        "sector_news_pressure",
        "risk_tone",
        "risk_tone_score",
        "breadth_score",
        "advance_decline_ratio",
        "market_regime",
        "regime",
        "volatility",
        "volatility_score",
    ):
        if key in ctx and key not in merged:
            merged[key] = ctx.get(key)
    return merged


def _outcome(row: Dict[str, Any]) -> str:
    text = _safe_text(row.get("outcome") or row.get("result") or row.get("status") or row.get("trade_result")).upper()
    if text in {"WIN", "WON", "TP", "TARGET", "TARGET_HIT", "PROFIT", "SUCCESS"}:
        return "WIN"
    if text in {"LOSS", "LOST", "SL", "STOPLOSS", "STOP_LOSS", "SL_HIT", "FAILED"}:
        return "LOSS"
    return "UNKNOWN"


def _hour_from_row(row: Dict[str, Any]) -> int | None:
    for key in ("entry_time", "signal_time", "timestamp", "opened_at", "created_at", "generated_at"):
        text = _safe_text(row.get(key))
        if not text:
            continue
        try:
            if text.endswith("Z"):
                text = f"{text[:-1]}+00:00"
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=IST)
            return parsed.astimezone(IST).hour
        except Exception:
            continue
    session = _safe_text(row.get("session_context_label") or row.get("entry_timing_label")).lower()
    if "open" in session:
        return 9
    if "mid" in session or "lunch" in session:
        return 12
    if "close" in session or "late" in session:
        return 14
    return None


def _session_label(hour: int | None = None) -> str:
    hour = _now_ist().hour if hour is None else hour
    if hour < 9:
        return "PRE_MARKET"
    if hour < 11:
        return "OPENING_SESSION"
    if hour < 14:
        return "MIDDAY_SESSION"
    if hour < 16:
        return "CLOSING_SESSION"
    return "POST_MARKET"


def _bucket_stats(rows: Iterable[Dict[str, Any]], key_fn) -> Dict[str, Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = key_fn(row)
        if not key:
            continue
        bucket = buckets.setdefault(str(key), {"samples": 0, "wins": 0, "losses": 0, "volatility_sum": 0.0})
        bucket["samples"] += 1
        outcome = _outcome(row)
        if outcome == "WIN":
            bucket["wins"] += 1
        elif outcome == "LOSS":
            bucket["losses"] += 1
        bucket["volatility_sum"] += _safe_float(row.get("volatility_score") or row.get("atr_percent") or row.get("range_percent"), 50.0)
    for bucket in buckets.values():
        attempts = bucket["wins"] + bucket["losses"]
        bucket["win_rate"] = round(bucket["wins"] / attempts, 4) if attempts else 0.0
        bucket["loss_rate"] = round(bucket["losses"] / attempts, 4) if attempts else 0.0
        bucket["avg_volatility_score"] = round(bucket.pop("volatility_sum") / max(bucket["samples"], 1), 4)
        bucket["timing_quality_score"] = _score((bucket["win_rate"] * 0.65) + ((1.0 - bucket["loss_rate"]) * 0.35))
    return dict(sorted(buckets.items())[:MAX_ITEMS])


def _phase_base(phase: str, previous: Dict[str, Any], sources: Dict[str, Any]) -> Dict[str, Any]:
    paths = PHASE_PATHS[phase]
    now = _now()
    return {
        "version": STATE_VERSION,
        "generated_at": now,
        "first_seen_at": previous.get("first_seen_at") or now,
        "previous_generated_at": previous.get("generated_at"),
        "run_count": _safe_int(previous.get("run_count"), 0) + 1,
        "continued_from_previous_state": bool(previous),
        "previous_run_count": previous.get("run_count", 0),
        "memory_sources": sources,
        "state_path": _relative(paths["memory"]),
        "runtime_status_path": _relative(paths["runtime"]),
        "report_path": _relative(paths["report"]),
        "safety_flags": _safety_flags(),
        **_safety_flags(),
    }


def build_temporal_intelligence(
    previous: Dict[str, Any] | None = None,
    evaluated_setups: List[Dict[str, Any]] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    setups = [item for item in evaluated_setups or [] if isinstance(item, dict)]
    rows = records + setups
    hour_stats = _bucket_stats(rows, lambda row: _hour_from_row(row))
    session_stats = _bucket_stats(rows, lambda row: _session_label(_hour_from_row(row)))
    entry_stats = _bucket_stats(rows, lambda row: row.get("entry_timing_label") or row.get("session_context_label") or row.get("timing_label"))
    volatility_by_time = {
        name: {"samples": stats["samples"], "avg_volatility_score": stats["avg_volatility_score"]}
        for name, stats in hour_stats.items()
    }
    setup_timing = _bucket_stats(rows, lambda row: row.get("setup_type") or row.get("strategy_family") or row.get("strategy"))
    quality_values = [stats.get("timing_quality_score", 0.0) for stats in list(hour_stats.values()) + list(entry_stats.values())]
    timing_quality = _score(sum(quality_values) / len(quality_values)) if quality_values else 0.5
    replay = payloads.get("historical_replay_progress", {})
    no_trade = payloads.get("no_trade_report", {}) or payloads.get("no_trade_memory", {})
    state = {
        **_phase_base("phase44", previous, sources),
        "phase": "PHASE_44_TEMPORAL_INTELLIGENCE",
        "status": "OK" if rows or replay else "WAITING_FOR_REPLAY_MEMORY",
        "connected": True,
        "current_session": _session_label(),
        "session_behavior": session_stats,
        "intraday_rhythm": hour_stats,
        "timing_quality_score": timing_quality,
        "volatility_by_time": volatility_by_time,
        "setup_timing_success_failure": setup_timing,
        "replay_timing_behavior": {
            "replay_consumed": bool(replay),
            "last_records_generated": replay.get("last_records_generated"),
            "total_records_generated": replay.get("total_records_generated"),
            "latest_replay_records_seen": len(records),
        },
        "input_context": {
            "no_trade_consumed": bool(no_trade),
            "strategy_genome_consumed": bool(payloads.get("strategy_genome")),
            "meta_regime_consumed": bool(payloads.get("meta_regime")),
            "accuracy_validation_consumed": bool(payloads.get("accuracy_validation")),
            "context_mode": (context or {}).get("trading_mode") if isinstance(context, dict) else None,
        },
        "advisory_context": {
            "master_brain": "Report-only timing context; final_decision_engine remains ranking owner.",
            "strategy_adaptation": "Use timing buckets as sandbox research features.",
            "replay_intelligence": "Prioritize replay slices with weak timing quality.",
            "consciousness_meta_layers": "Expose timing drift and session mismatch hypotheses.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "timing_quality_score": timing_quality, "current_session": state["current_session"]})
    state["history"] = history[-MAX_HISTORY:]
    return state


def _extract_breadth(market: Dict[str, Any]) -> Dict[str, Any]:
    raw = market.get("index_breadth") if isinstance(market.get("index_breadth"), dict) else {}
    score = _safe_float(raw.get("breadth_score") or raw.get("participation_score") or market.get("breadth_score"), 50.0)
    adr = _safe_float(raw.get("advance_decline_ratio") or market.get("advance_decline_ratio"), 1.0)
    return {
        "available": bool(raw or "breadth_score" in market),
        "breadth_score": _score100(score),
        "advance_decline_ratio": round(adr, 4),
        "state": "HEALTHY_PARTICIPATION" if score >= 62 else "HIDDEN_WEAKNESS" if score <= 38 else "MIXED_PARTICIPATION",
        "raw": raw,
    }


def build_market_breadth_intelligence(
    previous: Dict[str, Any] | None = None,
    temporal_state: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, _records = _load_inputs()
    temporal_state = temporal_state if isinstance(temporal_state, dict) else _read_json(PHASE_PATHS["phase44"]["memory"])
    market = _market_data_from_master(master_input, context)
    breadth = _extract_breadth(market)
    sectors = market.get("sector_strength") if isinstance(market.get("sector_strength"), dict) else {}
    rankings = market.get("sector_rankings") if isinstance(market.get("sector_rankings"), list) else []
    sector_participation = {}
    for sector, data in sectors.items():
        if not isinstance(data, dict):
            continue
        sector_participation[str(sector)] = {
            "strength_score": _score100(_safe_float(data.get("strength_score"), 50.0)),
            "breadth_20dma_ratio": round(_safe_float(data.get("breadth_20dma_ratio"), 0.5), 4),
            "symbols_counted": _safe_int(data.get("symbols_counted"), 0),
        }
    risk_tone_score = _safe_float(market.get("risk_tone_score"), 50.0)
    divergence = _score(abs(risk_tone_score - breadth["breadth_score"]) / 100.0)
    confirmation = _score((breadth["breadth_score"] / 100.0) * 0.64 + ((100.0 - abs(50.0 - risk_tone_score)) / 100.0) * 0.18 + (1.0 - divergence) * 0.18)
    hidden = _score((1.0 - breadth["breadth_score"] / 100.0) * 0.72 + divergence * 0.28)
    temporal_quality = _safe_float(temporal_state.get("timing_quality_score"), 0.5)
    participation_health = _score((breadth["breadth_score"] / 100.0) * 0.62 + confirmation * 0.23 + temporal_quality * 0.15)
    state = {
        **_phase_base("phase45", previous, sources),
        "phase": "PHASE_45_MARKET_BREADTH_INTELLIGENCE",
        "status": "OK" if breadth.get("available") or sectors else "WAITING_FOR_MARKET_BREADTH_CONTEXT",
        "connected": True,
        "phase44_consumed": bool(temporal_state),
        "phase44_run_count_seen": temporal_state.get("run_count"),
        "market_participation_health_score": participation_health,
        "index_breadth": breadth,
        "sector_participation": sector_participation,
        "sector_rankings_seen": rankings[:MAX_ITEMS],
        "breadth_divergence_score": divergence,
        "hidden_weakness_strength_score": hidden,
        "market_wide_confirmation_quality": confirmation,
        "regime_consumed": bool(payloads.get("advanced_regime") or payloads.get("meta_regime")),
        "no_trade_consumed": bool(payloads.get("no_trade_report") or payloads.get("no_trade_memory")),
        "advisory_context": {
            "regime_intelligence": "Breadth health qualifies regime confidence in reports only.",
            "no_trade_intelligence": "Hidden weakness signals can be reviewed by no-trade research.",
            "confidence_systems": "Breadth confirmation is advisory and does not change live rank.",
            "master_brain": "Participation context is exposed as sidecar state only.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "participation_health": participation_health, "divergence": divergence})
    state["history"] = history[-MAX_HISTORY:]
    return state


def _text_blob(*values: Any) -> str:
    return " ".join(_safe_text(value).lower() for value in values if value is not None)


def build_crowd_psychology_state(
    previous: Dict[str, Any] | None = None,
    temporal_state: Dict[str, Any] | None = None,
    breadth_state: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    temporal_state = temporal_state if isinstance(temporal_state, dict) else _read_json(PHASE_PATHS["phase44"]["memory"])
    breadth_state = breadth_state if isinstance(breadth_state, dict) else _read_json(PHASE_PATHS["phase45"]["memory"])
    no_trade = payloads.get("no_trade_report", {}) or payloads.get("no_trade_memory", {})
    trap = payloads.get("trap_memory", {})
    meta = payloads.get("meta_regime", {})
    fear_terms = Counter()
    euphoria_terms = Counter()
    for row in records[-MAX_RECORDS:]:
        text = _text_blob(row.get("semantic_labels"), row.get("trap_label"), row.get("behavioral_pattern_label"), row.get("emotional_market_proxy"), row.get("failure_reason_label"), row.get("reason"))
        for term in ("panic", "fear", "risk_off", "selloff", "crash", "capitulation"):
            if term in text:
                fear_terms[term] += 1
        for term in ("euphoria", "risk_on", "fomo", "exhaustion", "overconfidence", "climax"):
            if term in text:
                euphoria_terms[term] += 1
    breadth_weakness = _safe_float(breadth_state.get("hidden_weakness_strength_score"), 0.0)
    timing_quality = _safe_float(temporal_state.get("timing_quality_score"), 0.5)
    no_trade_score = _safe_float(no_trade.get("no_trade_score") or no_trade.get("danger_score"), 0.0) / 100.0
    trap_pressure = 0.0
    buckets = trap.get("pattern_buckets") if isinstance(trap.get("pattern_buckets"), dict) else {}
    for bucket in buckets.values():
        if isinstance(bucket, dict):
            trap_pressure = max(trap_pressure, _safe_float(bucket.get("loss_rate"), 0.0) * min(1.0, _safe_float(bucket.get("samples"), 0.0) / 20.0))
    panic = _score(max(no_trade_score, breadth_weakness) * 0.45 + trap_pressure * 0.25 + (len(fear_terms) / 20.0) * 0.20 + (1.0 - timing_quality) * 0.10)
    euphoria = _score((len(euphoria_terms) / 20.0) * 0.44 + max(0.0, 1.0 - breadth_weakness) * 0.22 + (timing_quality if timing_quality > 0.7 else 0.0) * 0.14 + _safe_float((context or {}).get("risk_tone_score"), 50.0) / 100.0 * 0.20)
    instability = _score(max(panic, euphoria) * 0.42 + _safe_float(meta.get("global_meta_regime_risk_score"), 0.0) * 0.28 + trap_pressure * 0.30)
    state = {
        **_phase_base("phase46", previous, sources),
        "phase": "PHASE_46_CROWD_PSYCHOLOGY_ENGINE",
        "status": "OK" if records or trap or no_trade else "WAITING_FOR_CROWD_MEMORY_INPUTS",
        "connected": True,
        "phase44_consumed": bool(temporal_state),
        "phase44_run_count_seen": temporal_state.get("run_count"),
        "phase45_consumed": bool(breadth_state),
        "phase45_run_count_seen": breadth_state.get("run_count"),
        "fear_euphoria": {"fear_score": panic, "euphoria_score": euphoria, "dominant_state": "FEAR" if panic > euphoria else "EUPHORIA" if euphoria > panic else "BALANCED"},
        "panic_behavior_score": panic,
        "crowd_instability_score": instability,
        "trap_psychology_score": _score(trap_pressure),
        "overconfidence_score": euphoria,
        "emotional_replay_patterns": {
            "fear_terms": dict(fear_terms.most_common(MAX_ITEMS)),
            "euphoria_terms": dict(euphoria_terms.most_common(MAX_ITEMS)),
            "records_seen": len(records),
        },
        "advisory_context": {
            "master_brain": "Crowd state is advisory-only sidecar context.",
            "consciousness_meta_layers": "Use emotion/instability as hypotheses for reflection.",
            "replay_intelligence": "Replay emotionally extreme slices first.",
            "strategy_adaptation": "Sandbox overconfidence/trap patterns without live promotion.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "panic": panic, "euphoria": euphoria, "instability": instability})
    state["history"] = history[-MAX_HISTORY:]
    return state


def _news_items(news_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("news", "news_items", "items", "articles"):
        value = news_payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def build_market_narrative_intelligence(
    previous: Dict[str, Any] | None = None,
    breadth_state: Dict[str, Any] | None = None,
    crowd_state: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    news_items: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, _records = _load_inputs()
    breadth_state = breadth_state if isinstance(breadth_state, dict) else _read_json(PHASE_PATHS["phase45"]["memory"])
    crowd_state = crowd_state if isinstance(crowd_state, dict) else _read_json(PHASE_PATHS["phase46"]["memory"])
    phase8 = payloads.get("phase8_narrative", {})
    news_intel = payloads.get("news_intelligence", {})
    batch_news = _news_items(payloads.get("news_batch", {}))
    items = [item for item in news_items or [] if isinstance(item, dict)] or batch_news
    themes = Counter()
    sector_themes: Dict[str, Counter] = defaultdict(Counter)
    macro_terms = {"rbi", "fed", "inflation", "cpi", "gdp", "rate", "policy", "currency", "crude", "oil", "budget", "election"}
    macro_hits = Counter()
    for item in items[-100:]:
        text = _text_blob(item.get("title"), item.get("summary"), item.get("description"))
        event = _safe_text(item.get("event_classification") or item.get("event") or news_intel.get("event_classification"), "GENERAL_NEWS").upper()
        themes[event] += 1
        for term in macro_terms:
            if term in text:
                macro_hits[term] += 1
        for sector in item.get("sectors") or item.get("sector_tags") or []:
            sector_themes[_safe_text(sector, "UNKNOWN").upper()][event] += 1
    if news_intel:
        market_narrative = news_intel.get("market_narrative") if isinstance(news_intel.get("market_narrative"), dict) else {}
        themes[_safe_text(market_narrative.get("narrative_type") or news_intel.get("event_classification"), "NEWS_INTELLIGENCE")] += 1
    current_type = themes.most_common(1)[0][0] if themes else _safe_text((phase8.get("current_narrative") or {}).get("narrative_type") if isinstance(phase8.get("current_narrative"), dict) else None, "DATA_INSUFFICIENT_NEUTRAL")
    prior_type = previous.get("dominant_narrative")
    contradiction = _score(
        _safe_float(breadth_state.get("breadth_divergence_score"), 0.0) * 0.45
        + _safe_float(crowd_state.get("crowd_instability_score"), 0.0) * 0.35
        + (0.20 if prior_type and prior_type != current_type else 0.0)
    )
    persistence = _score((0.55 if prior_type == current_type else 0.15) + min(1.0, themes[current_type] / 10.0) * 0.30 + (1.0 - contradiction) * 0.15)
    decay = _score((1.0 - persistence) * 0.7 + contradiction * 0.3)
    sector_narratives = {
        sector: {"dominant_theme": counter.most_common(1)[0][0], "theme_count": counter.most_common(1)[0][1]}
        for sector, counter in list(sector_themes.items())[:MAX_ITEMS]
        if counter
    }
    state = {
        **_phase_base("phase47", previous, sources),
        "phase": "PHASE_47_MARKET_NARRATIVE_INTELLIGENCE",
        "status": "OK" if items or news_intel or phase8 else "WAITING_FOR_NEWS_NARRATIVE_INPUTS",
        "connected": True,
        "phase45_consumed": bool(breadth_state),
        "phase45_run_count_seen": breadth_state.get("run_count"),
        "phase46_consumed": bool(crowd_state),
        "phase46_run_count_seen": crowd_state.get("run_count"),
        "dominant_narrative": current_type,
        "dominant_themes": dict(themes.most_common(MAX_ITEMS)),
        "sector_narratives": sector_narratives,
        "macro_narratives": dict(macro_hits.most_common(MAX_ITEMS)),
        "narrative_persistence_score": persistence,
        "narrative_decay_score": decay,
        "narrative_contradiction_score": contradiction,
        "news_driven_behavioral_context": {
            "news_items_seen": len(items),
            "news_intelligence_consumed": bool(news_intel),
            "phase8_narrative_consumed": bool(phase8),
            "crowd_dominant_state": ((crowd_state.get("fear_euphoria") or {}).get("dominant_state") if isinstance(crowd_state.get("fear_euphoria"), dict) else None),
            "breadth_state": ((breadth_state.get("index_breadth") or {}).get("state") if isinstance(breadth_state.get("index_breadth"), dict) else None),
        },
        "advisory_context": {
            "master_brain": "Narrative state remains report-side context only.",
            "strategy_adaptation": "Use persistent/decaying themes for sandbox research.",
            "consciousness_meta_reasoning": "Surface narrative contradictions for reflection.",
            "narrative_aware_replay": "Prioritize replay around theme shifts and crowd contradiction.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "dominant_narrative": current_type, "persistence": persistence, "contradiction": contradiction})
    state["history"] = history[-MAX_HISTORY:]
    return state


def _runtime_status(state: Dict[str, Any], phase_key: str, extra_fields: Iterable[str]) -> Dict[str, Any]:
    status = {
        "phase": state.get("phase"),
        "status": state.get("status"),
        "connected": True,
        "generated_at": state.get("generated_at"),
        "run_count": state.get("run_count"),
        "continued_from_previous_state": state.get("continued_from_previous_state"),
        "state_path": state.get("state_path"),
        "report_path": state.get("report_path"),
        "safety_flags": state.get("safety_flags"),
        "pyramid_placement": f"master_controller_{phase_key}_sidecar",
        **_safety_flags(),
    }
    for field in extra_fields:
        if field in state:
            status[field] = state.get(field)
    return status


def _render_report(title: str, state: Dict[str, Any], fields: Iterable[str]) -> str:
    lines = [
        title,
        "=" * len(title),
        f"Updated: {state.get('generated_at')}",
        f"Status: {state.get('status')} | Connected: {state.get('connected')}",
        f"Run count: {state.get('run_count')} | Continued: {state.get('continued_from_previous_state')}",
        "",
        "Safety",
        "- advisory_only=true research_only=true shadow_mode=true",
        "- affects_live_ranking=false affects_execution=false broker_mutation=false telegram_mutation=false supabase_mutation=false",
        "",
        "Values",
    ]
    for field in fields:
        lines.append(f"- {field}: {state.get(field)}")
    lines.extend(["", "Cross-Phase Consumption"])
    for field in (
        "phase44_consumed",
        "phase44_run_count_seen",
        "phase45_consumed",
        "phase45_run_count_seen",
        "phase46_consumed",
        "phase46_run_count_seen",
    ):
        if field in state:
            lines.append(f"- {field}: {state.get(field)}")
    lines.extend(["", "Memory Sources"])
    for name, item in sorted((state.get("memory_sources") or {}).items()):
        lines.append(f"- {name}: available={item.get('available')}, status={item.get('status')}, path={item.get('path')}")
    return "\n".join(lines) + "\n"


def _persist(phase_key: str, state: Dict[str, Any], report_title: str, report_fields: Iterable[str], status_fields: Iterable[str], write_files: bool) -> Dict[str, Any]:
    paths = PHASE_PATHS[phase_key]
    runtime = _runtime_status(state, phase_key, status_fields)
    state["runtime_status"] = runtime
    if write_files:
        _write_json(paths["memory"], state)
        _write_json(paths["runtime"], runtime)
        paths["report"].parent.mkdir(parents=True, exist_ok=True)
        paths["report"].write_text(_render_report(report_title, state, report_fields), encoding="utf-8")
    return state


def run_temporal_intelligence(evaluated_setups: List[Dict[str, Any]] | None = None, context: Dict[str, Any] | None = None, write_files: bool = True) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase44"]["memory"])
    state = build_temporal_intelligence(previous=previous, evaluated_setups=evaluated_setups, context=context)
    return _persist("phase44", state, "TITAN Phase 44 Temporal Intelligence Report", ("current_session", "timing_quality_score", "session_behavior", "replay_timing_behavior"), ("current_session", "timing_quality_score", "replay_timing_behavior"), write_files)


def run_market_breadth_intelligence(master_input: Dict[str, Any] | None = None, context: Dict[str, Any] | None = None, temporal_state: Dict[str, Any] | None = None, write_files: bool = True) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase45"]["memory"])
    state = build_market_breadth_intelligence(previous=previous, temporal_state=temporal_state, master_input=master_input, context=context)
    return _persist("phase45", state, "TITAN Phase 45 Market Breadth Intelligence Report", ("market_participation_health_score", "breadth_divergence_score", "hidden_weakness_strength_score", "market_wide_confirmation_quality"), ("phase44_consumed", "phase44_run_count_seen", "market_participation_health_score", "breadth_divergence_score", "market_wide_confirmation_quality"), write_files)


def run_crowd_psychology_engine(context: Dict[str, Any] | None = None, temporal_state: Dict[str, Any] | None = None, breadth_state: Dict[str, Any] | None = None, write_files: bool = True) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase46"]["memory"])
    state = build_crowd_psychology_state(previous=previous, temporal_state=temporal_state, breadth_state=breadth_state, context=context)
    return _persist(
        "phase46",
        state,
        "TITAN Phase 46 Crowd Psychology Report",
        ("fear_euphoria", "panic_behavior_score", "crowd_instability_score", "trap_psychology_score", "overconfidence_score"),
        (
            "phase44_consumed",
            "phase45_consumed",
            "phase44_run_count_seen",
            "phase45_run_count_seen",
            "fear_euphoria",
            "panic_behavior_score",
            "crowd_instability_score",
            "trap_psychology_score",
            "overconfidence_score",
            "emotional_replay_patterns",
        ),
        write_files,
    )


def run_market_narrative_intelligence(context: Dict[str, Any] | None = None, news_items: List[Dict[str, Any]] | None = None, breadth_state: Dict[str, Any] | None = None, crowd_state: Dict[str, Any] | None = None, write_files: bool = True) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase47"]["memory"])
    state = build_market_narrative_intelligence(previous=previous, breadth_state=breadth_state, crowd_state=crowd_state, context=context, news_items=news_items)
    return _persist("phase47", state, "TITAN Phase 47 Market Narrative Intelligence Report", ("dominant_narrative", "dominant_themes", "narrative_persistence_score", "narrative_decay_score", "narrative_contradiction_score"), ("phase45_consumed", "phase46_consumed", "phase45_run_count_seen", "phase46_run_count_seen", "dominant_narrative", "narrative_persistence_score", "narrative_contradiction_score"), write_files)


def run_roadmap_batch3_intelligence(
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    evaluated_setups: List[Dict[str, Any]] | None = None,
    news_items: List[Dict[str, Any]] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    phase44 = run_temporal_intelligence(evaluated_setups=evaluated_setups, context=context, write_files=write_files)
    phase45 = run_market_breadth_intelligence(master_input=master_input, context=context, temporal_state=phase44, write_files=write_files)
    phase46 = run_crowd_psychology_engine(context=context, temporal_state=phase44, breadth_state=phase45, write_files=write_files)
    phase47 = run_market_narrative_intelligence(context=context, news_items=news_items, breadth_state=phase45, crowd_state=phase46, write_files=write_files)
    return {
        "phase44_temporal_intelligence": phase44,
        "phase45_market_breadth_intelligence": phase45,
        "phase46_crowd_psychology_engine": phase46,
        "phase46_crowd_psychology": phase46,
        "phase47_market_narrative_intelligence": phase47,
        "advisory_only": True,
        "research_only": True,
        "shadow_mode": True,
        "affects_live_ranking": False,
        "affects_execution": False,
        "broker_mutation": False,
        "telegram_mutation": False,
        "supabase_mutation": False,
    }


if __name__ == "__main__":
    result = run_roadmap_batch3_intelligence(write_files=True)
    print("TITAN Roadmap Batch 3 refreshed")
    for key, state in result.items():
        if isinstance(state, dict) and state.get("phase"):
            print(key, state.get("status"), state.get("run_count"))
