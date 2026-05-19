import json
from pathlib import Path

from consciousness_core.state import atomic_write_json, now_ist, stable_hash


MISSIONS_PATH = Path("data") / "consciousness_core" / "research_missions.json"
OUTPUT_PATH = Path("data") / "consciousness_core" / "research_experiments.json"


def _load_json(path, default):
    try:
        with Path(path).open("r", encoding="utf-8") as payload_file:
            payload = json.load(payload_file)
        return payload if isinstance(payload, type(default)) else default
    except Exception:
        return default


def _required_data(mission):
    evidence_sources = [
        item.get("source")
        for item in mission.get("evidence") or []
        if isinstance(item, dict) and item.get("source")
    ]
    base = ["trade outcomes", "trade journal", "backtesting report"]
    if mission.get("target_engine") in {"confidence_calibration", "confidence_model"}:
        base.append("confidence calibration report")
    if mission.get("target_engine") in {"market_regime_update", "no_trade"}:
        base.append("no-trade/regime report")
    return sorted(set(base + evidence_sources))


def run_research_lab(missions_path=MISSIONS_PATH, output_path=OUTPUT_PATH):
    missions = _load_json(missions_path, [])
    experiments = []
    for mission in missions:
        if not isinstance(mission, dict):
            continue
        required_data = _required_data(mission)
        blocker = None
        if any("missing" in str(item).lower() for item in mission.get("evidence") or []):
            blocker = "missing source data must be restored before conclusion"
        experiments.append(
            {
                "experiment_id": "experiment_" + stable_hash([mission.get("mission_id"), mission.get("title")])[:16],
                "mission_id": mission.get("mission_id"),
                "hypothesis": mission.get("reason") or mission.get("title"),
                "target_engine": mission.get("target_engine"),
                "required_data": required_data,
                "test_method": "compare historical evidence, paper outcomes, and validation reports without changing live strategy",
                "success_condition": "paper/backtest evidence improves while risk and missing-data warnings do not increase",
                "blocker": blocker,
                "status": "BLOCKED" if blocker else "READY_TO_TEST",
                "created_at": now_ist(),
            }
        )
    payload = {"generated_at": now_ist(), "experiments": experiments[:200]}
    atomic_write_json(output_path, payload)
    return payload
