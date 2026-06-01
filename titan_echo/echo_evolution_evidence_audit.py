"""Audit Phase 18 evolution claims with stricter evidence standards."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
ECHO_RUNTIME = RUNTIME_DIR / "echo"

EVOLUTION_PROOF_PATH = ECHO_RUNTIME / "evolution_proof_report.json"
INTEGRATION_PROOF_PATH = ECHO_RUNTIME / "integration_proof_report.json"
FILE_INDEX_PATH = ECHO_RUNTIME / "titan_file_index.json"
MODULE_REGISTRY_PATH = ECHO_RUNTIME / "titan_module_registry.json"
CONNECTION_GRAPH_PATH = ECHO_RUNTIME / "titan_connection_graph.json"
LIVE_STATUS_PATH = ECHO_RUNTIME / "live_status.json"
OBSERVATIONS_PATH = ECHO_RUNTIME / "observations.json"
OBSERVATION_SUMMARY_PATH = ECHO_RUNTIME / "observation_summary.json"
OUTPUT_PATH = ECHO_RUNTIME / "evolution_evidence_audit.json"

IST = timezone(timedelta(hours=5, minutes=30))

CATEGORIES = [
    "memory_growth",
    "learning_activity",
    "outcome_feedback_loop",
    "evolution_parameter_changes",
    "performance_improvement_evidence",
    "confidence_calibration",
    "strategy_adaptation",
    "decision_influence",
    "self_reflection_usage",
    "historical_experience_usage",
]

BASE_RUNTIME_FILES = [
    "learning_status.json",
    "evolution_status.json",
    "memory_status.json",
    "experience_memory_status.json",
    "outcome_tracker_diagnostics.json",
    "trade_contract_diagnostics.json",
    "final_validated_setups.json",
    "scanner_status.json",
]

CATEGORY_KEYWORDS = {
    "memory_growth": ["memory", "growth", "lineage", "compression", "contribution"],
    "learning_activity": ["learning", "meta_learning", "reinforcement", "training"],
    "outcome_feedback_loop": ["outcome", "feedback", "trade_outcome", "pnl", "win_rate"],
    "evolution_parameter_changes": ["evolution", "mutation", "parameter", "weight", "genome"],
    "performance_improvement_evidence": ["performance", "improvement", "accuracy", "score", "win_rate"],
    "confidence_calibration": ["confidence", "calibration", "recalibration"],
    "strategy_adaptation": ["strategy", "adaptation", "genome", "weight", "rejection"],
    "decision_influence": ["decision", "influence", "ranking", "selection", "master_brain"],
    "self_reflection_usage": ["reflection", "self_reflection", "recursive_self_reflection"],
    "historical_experience_usage": ["historical", "experience", "replay", "long_term", "memory"],
}

CATEGORY_SUBSYSTEMS = {
    "memory_growth": ["Memory"],
    "learning_activity": ["Learning"],
    "outcome_feedback_loop": ["Outcome Tracker"],
    "evolution_parameter_changes": ["Evolution"],
    "performance_improvement_evidence": ["Outcome Tracker", "Learning", "Evolution"],
    "confidence_calibration": ["Learning", "Outcome Tracker"],
    "strategy_adaptation": ["Evolution", "Master Brain"],
    "decision_influence": ["Master Brain", "Unified Brain"],
    "self_reflection_usage": ["Consciousness Core"],
    "historical_experience_usage": ["Memory", "Learning"],
}

STATE_CHANGE_TERMS = [
    "changed",
    "change",
    "delta",
    "updated",
    "update",
    "mutation",
    "weight_change",
    "version",
    "history",
    "lineage",
    "previous",
    "current",
    "before",
    "after",
]

DECISION_TERMS = [
    "decision",
    "influence",
    "selection",
    "selected",
    "master_brain",
    "setup_rank",
    "trade_decision",
    "approved_setup",
]

OUTCOME_TERMS = [
    "outcome",
    "pnl",
    "win_rate",
    "accuracy",
    "performance",
    "improvement",
    "improved",
    "profit",
    "loss",
    "trade_result",
    "validated",
]

ACTIVITY_TERMS = [
    "status",
    "running",
    "enabled",
    "active",
    "heartbeat",
    "last_run",
    "diagnostics",
]

SAFE_NEXT_MISSIONS = [
    {
        "mission_title": "Outcome improvement proof audit",
        "risk_level": "LOW",
        "execution_allowed": False,
        "objective": "Prove whether learning and evolution changes improve trade outcomes instead of only changing files.",
    },
    {
        "mission_title": "Decision influence trace audit",
        "risk_level": "LOW",
        "execution_allowed": False,
        "objective": "Trace whether memory, learning, and strategy state are consumed by Master Brain decisions.",
    },
    {
        "mission_title": "Confidence calibration proof audit",
        "risk_level": "LOW",
        "execution_allowed": False,
        "objective": "Verify confidence calibration with before/after calibration metrics and decision impact.",
    },
]


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def load_json(path: Path, default: Any | None = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {} if default is None else default


def try_load_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle), None
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError as exc:
        return None, f"malformed line {exc.lineno}"
    except OSError as exc:
        return None, f"read error {exc.__class__.__name__}"


def as_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str).lower()


def extract_index_files(file_index: Any) -> list[str]:
    if isinstance(file_index, dict):
        candidates = file_index.get("files") or file_index.get("indexed_files") or file_index.get("file_index")
        if isinstance(candidates, list):
            return [
                str(item.get("relative_path", ""))
                for item in candidates
                if isinstance(item, dict) and item.get("relative_path")
            ]
    if isinstance(file_index, list):
        return [
            str(item.get("relative_path", ""))
            for item in file_index
            if isinstance(item, dict) and item.get("relative_path")
        ]
    return []


def discover_runtime_files(file_index: Any) -> list[Path]:
    names = {RUNTIME_DIR / name for name in BASE_RUNTIME_FILES}
    interesting_terms = [
        "learning",
        "evolution",
        "memory",
        "experience",
        "calibration",
        "strategy",
        "outcome",
        "reflection",
    ]
    for path in RUNTIME_DIR.glob("*.json"):
        if any(term in path.name.lower() for term in interesting_terms):
            names.add(path)
    for relative in extract_index_files(file_index):
        normalized = relative.replace("\\", "/").lower()
        if normalized.startswith("data/runtime/") and normalized.endswith(".json"):
            if any(term in normalized for term in interesting_terms):
                names.add(REPO_ROOT / relative)
    return sorted(names)


def runtime_records(file_index: Any) -> list[dict[str, Any]]:
    records = []
    for path in discover_runtime_files(file_index):
        data, error = try_load_json(path)
        exists = error is None
        records.append(
            {
                "relative_path": path.relative_to(REPO_ROOT).as_posix() if path.exists() else f"data/runtime/{path.name}",
                "exists": exists,
                "error": error,
                "size_bytes": path.stat().st_size if path.exists() else 0,
                "modified_ist": datetime.fromtimestamp(path.stat().st_mtime, IST).isoformat() if path.exists() else "",
                "data": data if exists else None,
            }
        )
    return records


def original_category_map(evolution_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapped = {}
    for item in evolution_report.get("categories", []):
        if isinstance(item, dict) and item.get("category"):
            mapped[str(item["category"])] = item
    return mapped


def hit_terms(text: str, terms: list[str]) -> list[str]:
    return sorted({term for term in terms if term in text})


def integration_improving_statuses(integration: Any) -> dict[str, str]:
    statuses: dict[str, str] = {}
    if not isinstance(integration, dict):
        return statuses
    for item in integration.get("subsystems", []):
        if isinstance(item, dict) and item.get("subsystem"):
            statuses[str(item["subsystem"])] = str(item.get("improving", "UNKNOWN"))
    return statuses


def category_evidence(
    category: str,
    records: list[dict[str, Any]],
    global_text: str,
    improving_statuses: dict[str, str],
) -> dict[str, Any]:
    keywords = CATEGORY_KEYWORDS[category]
    evidence_found: list[str] = []
    evidence_missing: list[str] = []
    state_terms: list[str] = []
    decision_terms: list[str] = []
    outcome_terms: list[str] = []
    activity_terms: list[str] = []
    state_sources: list[str] = []
    decision_sources: list[str] = []
    outcome_sources: list[str] = []

    for record in records:
        record_text = f"{record['relative_path'].lower()} {as_text(record.get('data'))}"
        keyword_hits = hit_terms(record_text, keywords)
        if not keyword_hits:
            continue
        evidence_found.append(
            f"{record['relative_path']}: category keywords {', '.join(keyword_hits[:6])}"
        )
        record_state_terms = hit_terms(record_text, STATE_CHANGE_TERMS)
        record_decision_terms = hit_terms(record_text, DECISION_TERMS)
        record_outcome_terms = hit_terms(record_text, OUTCOME_TERMS)
        if record_state_terms:
            state_terms.extend(record_state_terms)
            state_sources.append(record["relative_path"])
        if record_decision_terms:
            decision_terms.extend(record_decision_terms)
            decision_sources.append(record["relative_path"])
        if record_outcome_terms and (record_state_terms or any(term in record_text for term in ["improved", "improvement", "delta", "before", "after"])):
            outcome_terms.extend(record_outcome_terms)
            outcome_sources.append(record["relative_path"])
        activity_terms.extend(hit_terms(record_text, ACTIVITY_TERMS))

    original_global_hits = hit_terms(global_text, keywords)
    if original_global_hits:
        evidence_found.append(f"ECHO artifacts mention {', '.join(original_global_hits[:8])}")
        activity_terms.extend(hit_terms(global_text, ACTIVITY_TERMS))

    state_proven = bool(state_terms)
    decision_proven = bool(decision_terms)
    raw_outcome_proven = bool(outcome_terms)
    related_subsystems = CATEGORY_SUBSYSTEMS.get(category, [])
    related_improving = {name: improving_statuses.get(name, "UNKNOWN") for name in related_subsystems}
    subsystem_improvement_proven = any(status == "YES" for status in related_improving.values())
    outcome_proven = raw_outcome_proven and subsystem_improvement_proven

    if not evidence_found:
        strength = "MISSING"
        adjusted_score = 0
        evidence_missing.append("No direct category evidence found in Phase 18 report, ECHO artifacts, or runtime truth files.")
    elif state_proven and decision_proven and outcome_proven:
        strength = "STRONG"
        adjusted_score = 90
    elif state_proven and (decision_proven or outcome_proven):
        strength = "MODERATE"
        adjusted_score = 65
        if not decision_proven:
            evidence_missing.append("Decision influence is not proven.")
        if not outcome_proven:
            evidence_missing.append("Outcome improvement is not proven.")
    elif state_proven or decision_proven or outcome_proven:
        strength = "WEAK"
        adjusted_score = 35
        if not state_proven:
            evidence_missing.append("State change is not proven.")
        if not decision_proven:
            evidence_missing.append("Decision influence is not proven.")
        if not outcome_proven:
            evidence_missing.append("Outcome improvement is not proven.")
    else:
        strength = "ACTIVITY_ONLY"
        adjusted_score = 15
        evidence_missing.append("Evidence shows file presence, status, or activity but no state change, decision influence, or outcome improvement.")

    if evidence_found and not activity_terms:
        evidence_missing.append("Runtime activity terms were not directly found for this category.")
    if raw_outcome_proven and not subsystem_improvement_proven:
        evidence_missing.append(
            "Runtime outcome terms exist, but Phase 17 integration proof does not confirm improving=YES for related subsystem(s)."
        )
    if state_proven and decision_proven and not outcome_proven:
        evidence_missing.append("State and decision evidence exist, but improvement proof is still missing.")

    return {
        "audited_strength": strength,
        "adjusted_score": adjusted_score,
        "evidence_found": list(dict.fromkeys(evidence_found))[:20],
        "evidence_missing": list(dict.fromkeys(evidence_missing))[:12],
        "whether_state_change_is_proven": state_proven,
        "whether_decision_influence_is_proven": decision_proven,
        "whether_outcome_improvement_is_proven": outcome_proven,
        "audit_notes": [
            f"State terms: {', '.join(sorted(set(state_terms))[:8])}" if state_terms else "No state-change terms found.",
            f"Decision terms: {', '.join(sorted(set(decision_terms))[:8])}" if decision_terms else "No decision-influence terms found.",
            f"Outcome terms: {', '.join(sorted(set(outcome_terms))[:8])}" if outcome_terms else "No outcome-improvement terms found.",
            f"State sources: {', '.join(sorted(set(state_sources))[:5])}" if state_sources else "No state-change source found.",
            f"Decision sources: {', '.join(sorted(set(decision_sources))[:5])}" if decision_sources else "No decision-influence source found.",
            f"Outcome sources: {', '.join(sorted(set(outcome_sources))[:5])}" if outcome_sources else "No outcome-improvement source found.",
            f"Related subsystem improving status: {related_improving}" if related_improving else "No related subsystem improving status found.",
        ],
    }


def adjusted_verdict(score: int, categories: list[dict[str, Any]]) -> str:
    strong = sum(1 for item in categories if item["audited_strength"] == "STRONG")
    moderate_or_better = sum(1 for item in categories if item["audited_strength"] in {"STRONG", "MODERATE"})
    activity_or_better = sum(1 for item in categories if item["audited_strength"] != "MISSING")
    if score >= 75 and strong >= 5:
        return "REAL_EVOLUTION"
    if score >= 45 and moderate_or_better >= 5:
        return "PARTIAL_EVOLUTION"
    if score > 10 and activity_or_better:
        return "ACTIVITY_ONLY"
    return "UNKNOWN"


def strongest(categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(categories, key=lambda item: (-int(item["adjusted_score"]), item["category"]))[:5]


def weakest(categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(categories, key=lambda item: (int(item["adjusted_score"]), item["category"]))[:5]


def missing_proofs(categories: list[dict[str, Any]]) -> list[dict[str, str]]:
    proofs = []
    for item in categories:
        for missing in item["evidence_missing"]:
            proofs.append({"category": item["category"], "missing_proof": missing})
    return proofs[:15]


def build_report() -> dict[str, Any]:
    evolution = load_json(EVOLUTION_PROOF_PATH, {})
    integration = load_json(INTEGRATION_PROOF_PATH, {})
    file_index = load_json(FILE_INDEX_PATH, {})
    modules = load_json(MODULE_REGISTRY_PATH, {})
    graph = load_json(CONNECTION_GRAPH_PATH, {})
    live_status = load_json(LIVE_STATUS_PATH, {})
    observations = load_json(OBSERVATIONS_PATH, {})
    observation_summary = load_json(OBSERVATION_SUMMARY_PATH, {})

    records = runtime_records(file_index)
    original_categories = original_category_map(evolution if isinstance(evolution, dict) else {})
    global_text = as_text(
        {
            "evolution": evolution,
            "integration": integration,
            "modules": modules,
            "graph": graph,
            "live_status": live_status,
            "observations": observations,
            "observation_summary": observation_summary,
        }
    )
    improving_statuses = integration_improving_statuses(integration)

    audited_categories = []
    for category in CATEGORIES:
        original = original_categories.get(category, {})
        audit = category_evidence(category, records, global_text, improving_statuses)
        audited_categories.append(
            {
                "category": category,
                "original_status": original.get("status", "UNKNOWN"),
                "original_score": original.get("score", 0),
                **audit,
            }
        )

    adjusted_score = round(sum(int(item["adjusted_score"]) for item in audited_categories) / len(audited_categories))
    original_score = int(evolution.get("overall_evolution_score", 0)) if isinstance(evolution, dict) else 0
    over_scored = [
        {
            "category": item["category"],
            "original_score": item["original_score"],
            "adjusted_score": item["adjusted_score"],
            "audited_strength": item["audited_strength"],
        }
        for item in audited_categories
        if int(item["original_score"] or 0) - int(item["adjusted_score"]) >= 20
    ]

    return {
        "schema": "titan_echo.evolution_evidence_audit.v1",
        "timestamp_ist": timestamp_ist(),
        "original_evolution_score": original_score,
        "adjusted_evolution_score": adjusted_score,
        "original_verdict": evolution.get("evolution_verdict", "UNKNOWN") if isinstance(evolution, dict) else "UNKNOWN",
        "adjusted_verdict": adjusted_verdict(adjusted_score, audited_categories),
        "categories": audited_categories,
        "over_scored_categories": over_scored,
        "strongest_verified_evidence": strongest(audited_categories),
        "weakest_verified_evidence": weakest(audited_categories),
        "missing_proofs": missing_proofs(audited_categories),
        "recommended_next_missions": SAFE_NEXT_MISSIONS,
        "runtime_files_inspected": [
            {
                "relative_path": item["relative_path"],
                "exists": item["exists"],
                "error": item["error"],
                "size_bytes": item["size_bytes"],
                "modified_ist": item["modified_ist"],
            }
            for item in records
        ],
        "audit_standard": "STRONG requires state change, decision influence, and outcome improvement evidence. File existence or script activity alone is ACTIVITY_ONLY.",
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    report = build_report()
    write_json(OUTPUT_PATH, report)
    print("TITAN ECHO evolution evidence audit: PASSED")
    print(f"Original evolution score: {report['original_evolution_score']}")
    print(f"Adjusted evolution score: {report['adjusted_evolution_score']}")
    print(f"Original verdict: {report['original_verdict']}")
    print(f"Adjusted verdict: {report['adjusted_verdict']}")
    print(f"Over-scored categories: {len(report['over_scored_categories'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
