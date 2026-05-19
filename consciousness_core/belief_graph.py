from pathlib import Path

from consciousness_core.state import atomic_write_json, now_ist, stable_hash


BELIEFS_PATH = Path("data") / "consciousness_core" / "beliefs.json"
MAX_SOURCE_EVENTS = 30


def load_beliefs(path=BELIEFS_PATH):
    try:
        import json

        with Path(path).open("r", encoding="utf-8") as beliefs_file:
            payload = json.load(beliefs_file)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {}


def _belief_id(statement):
    return "belief_" + stable_hash(statement)[:16]


def update_belief(beliefs, statement, evidence=None, delta=0.04, contradiction=False):
    if not statement:
        return beliefs
    belief_id = _belief_id(statement)
    belief = beliefs.setdefault(
        belief_id,
        {
            "belief_id": belief_id,
            "statement": statement,
            "confidence": 0.5,
            "evidence_count": 0,
            "contradiction_count": 0,
            "success_count": 0,
            "failure_count": 0,
            "regime_dependency": "unknown",
            "last_updated": now_ist(),
            "last_seen": now_ist(),
            "source_events": [],
            "status": "ACTIVE",
        },
    )
    if contradiction:
        belief["contradiction_count"] += 1
        belief["failure_count"] += 1
        belief["confidence"] = max(0.05, float(belief["confidence"]) - abs(delta))
    else:
        belief["evidence_count"] += 1
        belief["success_count"] += 1
        belief["confidence"] = min(0.98, float(belief["confidence"]) + abs(delta))
    if evidence:
        belief["source_events"] = (belief.get("source_events") or [])[-MAX_SOURCE_EVENTS + 1 :]
        belief["source_events"].append(evidence)
    belief["last_updated"] = now_ist()
    belief["last_seen"] = now_ist()
    belief["status"] = "DISPUTED" if belief["contradiction_count"] > belief["evidence_count"] else "ACTIVE"
    return beliefs


def update_beliefs_from_weaknesses(beliefs, weaknesses):
    for weakness in weaknesses:
        weakness_type = weakness.get("type")
        evidence = {
            "weakness_id": weakness.get("weakness_id"),
            "severity": weakness.get("severity"),
            "affected_engine": weakness.get("affected_engine"),
            "evidence": weakness.get("evidence", [])[:3],
        }
        if weakness_type in {"no_trade_warning", "regime_warning"}:
            statement = "choppy or contradictory regimes need stricter filters before trade permission increases"
            update_belief(beliefs, statement, evidence=evidence, delta=0.06)
        elif weakness_type in {"weak_confidence_calibration", "high_confidence_loss", "confidence_warning"}:
            statement = "confidence model may overestimate trade probability when calibration samples are weak or losses occur"
            update_belief(beliefs, statement, evidence=evidence, delta=0.07)
        elif weakness_type in {"worker_failure", "repeated_worker_failures", "placeholder_important_worker"}:
            engine = weakness.get("affected_engine") or "runtime worker"
            statement = f"{engine} reliability is degraded and downstream outputs should be treated cautiously"
            update_belief(beliefs, statement, evidence=evidence, delta=0.06)
        elif weakness_type == "poor_backtesting_validation":
            statement = "strategy improvements need populated backtest or paper validation before promotion"
            update_belief(beliefs, statement, evidence=evidence, delta=0.05)
        elif weakness_type == "evolution_stagnation":
            statement = "evolution should remain conservative until closed trade sample size improves"
            update_belief(beliefs, statement, evidence=evidence, delta=0.05)
        elif weakness_type == "strategy_underperformance":
            statement = "underperforming strategy clusters require stricter filters and further study"
            update_belief(beliefs, statement, evidence=evidence, delta=0.05)
    return beliefs


def decay_stale_beliefs(beliefs, decay=0.005):
    for belief in beliefs.values():
        confidence = float(belief.get("confidence") or 0.5)
        if confidence > 0.5:
            belief["confidence"] = max(0.5, confidence - decay)
        elif confidence < 0.5:
            belief["confidence"] = min(0.5, confidence + decay)
    return beliefs


def save_beliefs(beliefs, path=BELIEFS_PATH):
    atomic_write_json(path, beliefs)
    return beliefs
