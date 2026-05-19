import json
from pathlib import Path

from consciousness_core.experience_utils import load_json, load_standard_reports, load_trade_rows, recent_rows
from consciousness_core.state import stable_hash


CORE_DIR = Path("data") / "consciousness_core"


def clamp(value, low=0.0, high=100.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return max(low, min(high, number))


def score_from_flags(*flags, base=0.0, step=15.0):
    return clamp(base + step * sum(1 for flag in flags if flag))


def text_blob(*payloads):
    return json.dumps(payloads, default=str).lower()


def has_terms(payload, terms):
    blob = text_blob(payload)
    return any(term in blob for term in terms)


def mode_is_weak(payload, mode_keys):
    for key in mode_keys:
        mode = str(payload.get(key) or "").upper()
        if mode in {"PROXY", "INSUFFICIENT", "NO_DATA", "UNKNOWN"}:
            return True
    return False


def load_institutional_inputs():
    reports = load_standard_reports()
    core_report = reports.get("consciousness_report", {})
    return {
        "reports": reports,
        "core_report": core_report,
        "beliefs": reports.get("beliefs", {}),
        "weaknesses": core_report.get("active_weaknesses", []),
        "proposals": reports.get("proposals", []),
        "news": reports.get("news", {}),
        "no_trade": reports.get("no_trade", {}),
        "confidence": reports.get("confidence", {}),
        "world_model_memory": load_json(CORE_DIR / "world_model_memory.json", {}),
        "causal_reasoning": load_json(CORE_DIR / "causal_reasoning.json", {}),
        "real_experience_memory": load_json(CORE_DIR / "real_experience_memory.json", {}),
        "daily_review": load_json(CORE_DIR / "daily_review.json", {}),
        "experience_clusters": load_json(CORE_DIR / "experience_clusters.json", {}),
        "learning_directives": load_json(CORE_DIR / "learning_directives.json", {}),
        "liquidity_map": load_json(Path("data") / "liquidity_map" / "latest_institutional_liquidity_report.json", {}),
        "microstructure": load_json(Path("data") / "microstructure" / "latest_microstructure_report.json", {}),
        "economic_calendar": load_json(Path("data") / "economic_calendar" / "latest_economic_calendar_report.json", {}),
        "market_pressure": load_json(Path("data") / "market_pressure" / "latest_market_pressure_report.json", {}),
        "sector_strength": load_json(Path("data") / "sector_strength" / "latest_sector_strength_report.json", {}),
        "trade_rows": load_trade_rows(),
    }


def confidence_quality(confidence):
    sample_size = int(confidence.get("predicted_vs_actual", {}).get("sample_size") or 0)
    score = clamp(confidence.get("calibrated_confidence_score") or confidence.get("reliability_score") or 50.0)
    weak = sample_size < 20 or str(confidence.get("calibration_warning") or "").upper() == "REVIEW"
    return {
        "sample_size": sample_size,
        "score": score,
        "weak": weak,
        "reason": "low calibration sample or review warning" if weak else "calibration evidence is usable",
    }


def evidence_item(source, signal, value=None):
    return {"source": source, "signal": signal, "value": value}


def recommendation(action, reason):
    return {"action": action, "reason": reason, "scope": "recommendation_only"}


def chain_id(parts):
    return "chain_" + stable_hash(parts)[:16]


def recent_outcome_stats(rows):
    recent = recent_rows(rows, days=10)
    wins = 0
    losses = 0
    for row in recent:
        outcome = text_blob(row.get("outcome"), row.get("result"), row.get("realized_pnl"), row.get("pnl_points"))
        if "target" in outcome or "win" in outcome or "profit" in outcome:
            wins += 1
        if "loss" in outcome or "stop" in outcome or "sl" in outcome:
            losses += 1
    total = wins + losses
    return {
        "recent_rows": len(recent),
        "wins": wins,
        "losses": losses,
        "win_rate": round((wins / total) * 100, 2) if total else 0.0,
    }
