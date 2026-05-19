from pathlib import Path

from consciousness_core.state import atomic_write_json, now_ist, stable_hash


GOALS_PATH = Path("data") / "consciousness_core" / "goals.json"


DEFAULT_GOALS = (
    "reduce false positives",
    "improve choppy market filter",
    "improve news reliability",
    "improve confidence calibration",
    "improve regime detection",
    "improve SL/TP logic",
    "improve research quality",
)


def load_goals(path=GOALS_PATH):
    try:
        import json

        with Path(path).open("r", encoding="utf-8") as goals_file:
            payload = json.load(goals_file)
        if isinstance(payload, list):
            return payload
    except Exception:
        pass
    return []


def update_goals(weaknesses, reflection=None, path=GOALS_PATH):
    existing = {goal["goal_id"]: goal for goal in load_goals(path) if isinstance(goal, dict)}
    for title in DEFAULT_GOALS:
        goal_id = "goal_" + stable_hash(title)[:16]
        existing.setdefault(
            goal_id,
            {
                "goal_id": goal_id,
                "title": title,
                "status": "ACTIVE",
                "priority": "medium",
                "evidence": [],
                "created_at": now_ist(),
                "updated_at": now_ist(),
            },
        )
    for weakness in weaknesses:
        title = {
            "weak_confidence_calibration": "improve confidence calibration",
            "high_confidence_loss": "improve confidence calibration",
            "confidence_warning": "improve confidence calibration",
            "no_trade_warning": "improve choppy market filter",
            "regime_warning": "improve regime detection",
            "losing_setup_patterns": "reduce false positives",
            "missing_critical_report": "improve research quality",
            "missing_optional_data": "improve research quality",
            "worker_failure": "improve research quality",
            "repeated_worker_failures": "improve research quality",
            "poor_backtesting_validation": "improve research quality",
            "strategy_underperformance": "reduce false positives",
        }.get(weakness.get("type"), "reduce false positives")
        goal_id = "goal_" + stable_hash(title)[:16]
        goal = existing[goal_id]
        goal["evidence"] = (goal.get("evidence") or [])[-19:] + [weakness]
        goal["priority"] = "high" if str(weakness.get("severity")).upper() == "HIGH" else goal.get("priority", "medium")
        goal["updated_at"] = now_ist()
    goals = list(existing.values())
    atomic_write_json(path, goals)
    return goals
