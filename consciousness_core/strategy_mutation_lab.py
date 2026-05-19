import json
from pathlib import Path

from consciousness_core.state import atomic_write_json, now_ist, stable_hash


OUTPUT_PATH = Path("data") / "consciousness_core" / "strategy_mutations.json"


def _load_json(path, default):
    try:
        with Path(path).open("r", encoding="utf-8") as payload_file:
            payload = json.load(payload_file)
        return payload if isinstance(payload, type(default)) else default
    except Exception:
        return default


def _candidate(kind, target, description, evidence, guardrails):
    return {
        "mutation_id": "mutation_" + stable_hash([kind, target, description, evidence])[:16],
        "created_at": now_ist(),
        "kind": kind,
        "target_engine": target,
        "description": description,
        "apply_scope": "SANDBOX_OR_PAPER_ONLY",
        "live_apply_allowed": False,
        "evidence": evidence[:10],
        "guardrails": guardrails,
    }


def run_strategy_mutation_lab(output_path=OUTPUT_PATH):
    experience = _load_json(Path("data/consciousness_core/experience_memory.json"), {})
    causal = _load_json(Path("data/consciousness_core/causal_reasoning.json"), {})
    mutations = []
    weak_engines = {item.get("engine") for item in experience.get("weak_engines", []) if isinstance(item, dict)}
    causal_lessons = causal.get("causal_lessons", [])

    if "backtesting" in weak_engines:
        mutations.append(
            _candidate(
                "validation_block",
                "backtesting",
                "block strategy parameter promotion under insufficient validation",
                causal_lessons,
                ["paper/backtest only", "requires non-zero sample size", "no live strategy writes"],
            )
        )
    if "confidence_calibration" in weak_engines:
        mutations.append(
            _candidate(
                "confidence_reduction",
                "confidence_calibration",
                "reduce confidence contribution when calibration evidence is weak",
                causal_lessons,
                ["paper/backtest only", "minimum calibration sample required", "no live confidence changes"],
            )
        )
    if any("CHOPPY" in str(item).upper() or "CAUTION" in str(item).upper() for item in experience.get("regime_lessons", [])):
        mutations.append(
            _candidate(
                "choppy_filter",
                "no_trade",
                "tighten choppy or caution regime filter in sandbox tests",
                causal_lessons,
                ["paper/backtest only", "compare skipped trades against outcomes", "no live no-trade rule changes"],
            )
        )
    if experience.get("repeated_failure_patterns"):
        mutations.append(
            _candidate(
                "sector_confirmation",
                "setup_engine",
                "require sector confirmation for setups resembling repeated failure patterns",
                experience.get("repeated_failure_patterns", []),
                ["paper/backtest only", "track rejected candidates", "no live setup edits"],
            )
        )
    if not mutations:
        mutations.append(
            _candidate(
                "data_sufficiency_gate",
                "research_pipeline",
                "block trades under insufficient validation in sandbox analysis",
                causal_lessons,
                ["paper/backtest only", "recommendation artifact only", "no execution changes"],
            )
        )
    payload = {"generated_at": now_ist(), "mutations": mutations[:100]}
    atomic_write_json(output_path, payload)
    return payload
