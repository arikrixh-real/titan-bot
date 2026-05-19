from pathlib import Path

from consciousness_core.state import atomic_write_json, now_ist, stable_hash


MISSIONS_PATH = Path("data") / "consciousness_core" / "research_missions.json"
def load_missions(path=MISSIONS_PATH):
    try:
        import json

        with Path(path).open("r", encoding="utf-8") as mission_file:
            payload = json.load(mission_file)
        if isinstance(payload, list):
            return payload
    except Exception:
        pass
    return []


def _mission_from_weakness(weakness):
    weakness_type = weakness.get("type")
    engine = weakness.get("affected_engine") or "unknown"
    if weakness_type == "high_confidence_loss":
        title = "study failed high-confidence trades"
    elif weakness_type in {"no_trade_warning", "regime_warning"}:
        title = "study breakout failures in choppy markets"
    elif weakness_type == "weak_confidence_calibration":
        title = "study confidence calibration sample weakness"
    elif weakness_type == "poor_backtesting_validation":
        title = "study missing backtest validation coverage"
    elif weakness_type in {"worker_failure", "repeated_worker_failures", "placeholder_important_worker"}:
        title = f"study {engine} reliability gap"
    elif "news" in str(weakness).lower():
        title = "study news impact delay"
    else:
        title = f"study {engine} weakness"
    return {
        "mission_id": "mission_" + stable_hash([title, engine, weakness.get("weakness_id")])[:16],
        "title": title,
        "reason": weakness.get("recommended_investigation") or "weakness requires research before action",
        "evidence": weakness.get("evidence", []),
        "priority": "HIGH" if weakness.get("severity") == "HIGH" else "MEDIUM" if weakness.get("severity") == "MEDIUM" else "LOW",
        "target_engine": engine,
        "status": "OPEN",
        "created_at": now_ist(),
        "updated_at": now_ist(),
    }


def generate_research_missions(weaknesses, goals, path=MISSIONS_PATH):
    existing = {
        mission["mission_id"]: mission
        for mission in load_missions(path)
        if isinstance(mission, dict) and mission.get("target_engine")
    }
    for weakness in weaknesses:
        mission = _mission_from_weakness(weakness)
        mission_id = mission["mission_id"]
        current = existing.get(mission_id, {})
        mission["created_at"] = current.get("created_at", mission["created_at"])
        mission["evidence"] = (current.get("evidence") or [])[-10:] + mission["evidence"][:5]
        mission["updated_at"] = now_ist()
        existing[mission_id] = mission
    missions = sorted(existing.values(), key=lambda item: item.get("priority", ""), reverse=True)[-200:]
    atomic_write_json(path, missions)
    return missions
