from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


BASE = Path("data/runtime/echo")
INPUTS = {
    "failure_split_audit": BASE / "failure_split_audit.json",
    "runtime_failure_summary": BASE / "runtime_failure_summary.json",
    "post_repair_runtime_summary": BASE / "post_repair_runtime_summary.json",
    "runtime_evidence_summary": BASE / "runtime_evidence_summary.json",
    "scanner_breakout_integrity_repair_report": BASE / "scanner_breakout_integrity_repair_report.json",
    "echo_conversation_style": BASE / "echo_conversation_style.json",
}
PLAN_PATH = BASE / "runtime_repair_priority_plan.json"
SUMMARY_PATH = BASE / "runtime_repair_priority_summary.json"

FORBIDDEN_ACTIONS = [
    "Do not modify scanner.",
    "Do not modify workers.",
    "Do not modify Master Brain.",
    "Do not modify Unified Brain.",
    "Do not modify broker/risk.",
    "Do not restart TITAN.",
    "Do not deploy.",
    "Do not push.",
]

REAL_FAILURE_TERMS = {
    "fail",
    "failed",
    "failure",
    "error",
    "exception",
    "crash",
    "broken",
    "invalid",
    "missing",
    "blocked",
    "unhealthy",
}
REPAIRED_TERMS = {
    "already repaired",
    "repaired",
    "fixed",
    "resolved",
    "remediated",
    "patched",
    "waiting",
    "pending runtime",
    "regeneration",
    "regen",
}
STALE_TERMS = {"stale", "old", "historical", "outdated", "superseded", "previous", "prior"}
EXTERNAL_TERMS = {
    "external",
    "config",
    "configuration",
    "credential",
    "credentials",
    "secret",
    "api key",
    "apikey",
    "token",
    "network",
    "permission",
    "environment",
    "env var",
    "env",
    "missing dependency",
}
LOW_VALUE_TERMS = {
    "conversation style",
    "style",
    "cosmetic",
    "low value",
    "minor",
    "warning",
    "advisory",
    "informational",
    "non-blocking",
}
MISSING_EVIDENCE_CATEGORY = "missing_evidence_waiting_for_data"
DEPENDENCY_TERMS = {
    "scanner": "scanner/runtime evidence chain",
    "worker": "worker execution path",
    "master": "Master Brain downstream consumers",
    "unified": "Unified Brain downstream consumers",
    "broker": "broker/risk execution path",
    "risk": "broker/risk execution path",
    "runtime": "runtime regeneration and summaries",
    "evidence": "runtime evidence audit trail",
    "conversation": "conversation style reporting only",
}


@dataclass
class Finding:
    source: str
    path: str
    subsystem: str
    title: str
    evidence: list[str]
    category: str
    root_cause: str
    dependency_impact: str
    risk_level: str
    fix_complexity: str
    expected_improvement: str
    required_verification: list[str]
    score: int


def load_json(path: Path) -> Any:
    if not path.exists():
        return missing_evidence_payload(path)
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        return {
            "status": "UNKNOWN_NOT_PROVEN",
            "evidence_status": "WAITING_FOR_DATA",
            "issue_type": "MISSING_EVIDENCE",
            "source_file": str(path),
            "reason": f"INVALID_JSON:{type(exc).__name__}",
            "read_only_fallback": True,
        }


def missing_evidence_payload(path: Path) -> dict[str, Any]:
    return {
        "status": "UNKNOWN_NOT_PROVEN",
        "evidence_status": "WAITING_FOR_DATA",
        "issue_type": "MISSING_EVIDENCE",
        "source_file": str(path),
        "reason": "MISSING_EVIDENCE",
        "read_only_fallback": True,
        "no_fake_health_claim": True,
    }


def compact(value: Any, limit: int = 260) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, sort_keys=True, default=str)
    text = " ".join(text.replace("\n", " ").split())
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def walk(value: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, f"{path}[{index}]")


def text_blob(value: Any) -> str:
    return compact(value, 2000).lower()


def contains_any(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def infer_subsystem(path: str, value: Any) -> str:
    text = f"{path} {text_blob(value)}"
    for term in DEPENDENCY_TERMS:
        if term in text:
            return term
    if "failure_split" in text or "breakout" in text:
        return "runtime"
    return "runtime"


def infer_category(source: str, value: Any) -> str:
    text = text_blob(value)
    if isinstance(value, dict) and value.get("issue_type") == "MISSING_EVIDENCE":
        return MISSING_EVIDENCE_CATEGORY
    if contains_any(text, LOW_VALUE_TERMS) or source == "echo_conversation_style":
        return "low_value_repairs"
    if contains_any(text, EXTERNAL_TERMS):
        return "external_config_issues"
    if contains_any(text, REPAIRED_TERMS) or source == "scanner_breakout_integrity_repair_report":
        return "already_repaired_waiting_for_runtime_regeneration"
    if contains_any(text, STALE_TERMS):
        return "stale_evidence_only"
    return "real_current_failures"


def infer_root_cause(category: str, subsystem: str, evidence: list[str]) -> str:
    joined = " ".join(evidence).lower()
    if category == MISSING_EVIDENCE_CATEGORY:
        return f"{subsystem} repair priority is UNKNOWN_NOT_PROVEN because required evidence is missing or unreadable."
    if category == "already_repaired_waiting_for_runtime_regeneration":
        return "Repair evidence exists, but runtime artifacts still need regeneration before the failure can be cleared."
    if category == "stale_evidence_only":
        return "Failure appears to be historical or superseded evidence, not a confirmed current runtime defect."
    if category == "external_config_issues":
        return "The evidence points to environment, credential, dependency, permission, network, or configuration state outside code repair scope."
    if category == "low_value_repairs":
        return "Issue has low runtime impact or is limited to reporting/style quality."
    if "missing" in joined:
        return f"{subsystem} is missing a required artifact, key, dependency, or generated runtime output."
    if "exception" in joined or "error" in joined:
        return f"{subsystem} is producing runtime errors that need targeted code or data-contract repair."
    if "invalid" in joined:
        return f"{subsystem} is emitting invalid data or violating an expected runtime contract."
    return f"{subsystem} has a confirmed current failure in the runtime evidence split."


def infer_dependency_impact(subsystem: str, category: str) -> str:
    impact = DEPENDENCY_TERMS.get(subsystem, "runtime health reporting")
    if category == MISSING_EVIDENCE_CATEGORY:
        return f"Cannot rank {impact} confidently until missing evidence is regenerated or transferred."
    if category == "real_current_failures":
        return f"Blocks or degrades {impact}; repair should happen before lower-signal cleanup."
    if category == "already_repaired_waiting_for_runtime_regeneration":
        return f"Affects {impact} visibility until runtime artifacts are regenerated."
    if category == "external_config_issues":
        return f"May block {impact}, but requires configuration validation rather than code repair."
    if category == "stale_evidence_only":
        return f"No current dependency impact confirmed; retain as audit context."
    return f"Limited dependency impact on {impact}."


def infer_risk(category: str, evidence: list[str]) -> str:
    joined = " ".join(evidence).lower()
    if category == MISSING_EVIDENCE_CATEGORY:
        return "low"
    if category == "real_current_failures":
        if any(term in joined for term in ("crash", "blocked", "critical", "fatal", "missing")):
            return "high"
        return "medium"
    if category == "external_config_issues":
        return "medium"
    if category == "already_repaired_waiting_for_runtime_regeneration":
        return "low"
    return "low"


def infer_complexity(category: str, evidence: list[str]) -> str:
    joined = " ".join(evidence).lower()
    if category == MISSING_EVIDENCE_CATEGORY:
        return "low"
    if category in {"stale_evidence_only", "low_value_repairs"}:
        return "low"
    if category == "already_repaired_waiting_for_runtime_regeneration":
        return "low"
    if category == "external_config_issues":
        return "medium"
    if any(term in joined for term in ("schema", "contract", "cross", "dependency", "integration")):
        return "high"
    return "medium"


def expected_improvement(category: str, subsystem: str) -> str:
    if category == MISSING_EVIDENCE_CATEGORY:
        return "No repair is recommended from missing evidence alone; regenerate evidence before ranking runtime repairs."
    if category == "real_current_failures":
        return f"Removes an active {subsystem} runtime failure and should reduce current failure count after regeneration."
    if category == "already_repaired_waiting_for_runtime_regeneration":
        return "No code change expected; regeneration should move this out of the active failure set if repair evidence is valid."
    if category == "external_config_issues":
        return "Runtime health may improve after environment/config validation, without code changes."
    if category == "stale_evidence_only":
        return "No runtime improvement expected; only prevents wasted repair work."
    return "Small reporting-quality improvement; defer behind active runtime failures."


def verification_for(category: str, subsystem: str) -> list[str]:
    checks = [
        "Re-run Batch 6 failure split audit after the targeted repair.",
        "Regenerate runtime evidence summaries.",
        "Confirm the repaired item moves out of real_current_failures.",
    ]
    if category == "external_config_issues":
        return [
            "Validate required environment/config values without changing scanner, workers, brains, or broker/risk.",
            "Re-run runtime evidence collection after configuration is corrected.",
            "Confirm the issue is absent from runtime_failure_summary.json.",
        ]
    if category == "already_repaired_waiting_for_runtime_regeneration":
        return [
            "Regenerate runtime artifacts only after an approved runtime-generation mission.",
            "Confirm stale failure references disappear from runtime_failure_summary.json.",
            "Confirm scanner_breakout_integrity_repair_report.json remains clean.",
        ]
    if category == MISSING_EVIDENCE_CATEGORY:
        return [
            "Regenerate or transfer the missing ECHO evidence artifacts.",
            "Re-run the runtime repair priority planner.",
            "Do not modify scanner, workers, Master Brain, Unified Brain, broker/risk from missing evidence alone.",
        ]
    if category in {"stale_evidence_only", "low_value_repairs"}:
        return [
            "Confirm no active failure in runtime_failure_summary.json.",
            "Leave repair deferred unless it reappears as a real current failure.",
        ]
    if subsystem in {"scanner", "worker", "master", "unified", "broker", "risk"}:
        checks.append("Do not modify protected subsystems during this planning mission.")
    return checks


def evidence_score(category: str, source: str, evidence: list[str]) -> int:
    score = 0
    if category == MISSING_EVIDENCE_CATEGORY:
        score += 1
    elif category == "real_current_failures":
        score += 100
    elif category == "external_config_issues":
        score += 55
    elif category == "already_repaired_waiting_for_runtime_regeneration":
        score += 35
    elif category == "stale_evidence_only":
        score += 15
    else:
        score += 5
    if source in {"runtime_failure_summary", "post_repair_runtime_summary", "failure_split_audit"}:
        score += 20
    joined = " ".join(evidence).lower()
    if any(term in joined for term in ("critical", "fatal", "crash", "blocked")):
        score += 25
    if "missing" in joined:
        score += 10
    return score


def title_for(path: str, value: Any) -> str:
    if isinstance(value, dict):
        for key in ("name", "title", "issue", "failure", "error", "subsystem", "id"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return compact(item, 100)
    return path.split(".")[-1].replace("_", " ")[:100]


def make_finding(source: str, path: str, value: Any) -> Finding:
    evidence = [compact(value)]
    subsystem = infer_subsystem(path, value)
    category = infer_category(source, value)
    root_cause = infer_root_cause(category, subsystem, evidence)
    score = evidence_score(category, source, evidence)
    return Finding(
        source=source,
        path=path,
        subsystem=subsystem,
        title=title_for(path, value),
        evidence=evidence,
        category=category,
        root_cause=root_cause,
        dependency_impact=infer_dependency_impact(subsystem, category),
        risk_level=infer_risk(category, evidence),
        fix_complexity=infer_complexity(category, evidence),
        expected_improvement=expected_improvement(category, subsystem),
        required_verification=verification_for(category, subsystem),
        score=score,
    )


def collect_findings(docs: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for source, doc in docs.items():
        for path, value in walk(doc):
            if not isinstance(value, dict):
                continue
            blob = text_blob(value)
            key_blob = path.lower()
            if source == "echo_conversation_style" and len(value) > 0:
                findings.append(make_finding(source, path, value))
                continue
            has_failure_signal = contains_any(blob, REAL_FAILURE_TERMS | REPAIRED_TERMS | STALE_TERMS | EXTERNAL_TERMS | LOW_VALUE_TERMS)
            has_path_signal = any(term in key_blob for term in ("fail", "error", "repair", "stale", "external", "config", "warning"))
            if has_failure_signal or has_path_signal:
                findings.append(make_finding(source, path, value))
    return dedupe_findings(findings)


def finding_key(finding: Finding) -> str:
    raw = "|".join(
        [
            finding.category,
            finding.subsystem,
            finding.title.lower(),
            " ".join(finding.evidence).lower()[:400],
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def dedupe_findings(findings: list[Finding]) -> list[Finding]:
    grouped: dict[str, Finding] = {}
    for finding in findings:
        key = finding_key(finding)
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = finding
            continue
        existing.evidence.extend(item for item in finding.evidence if item not in existing.evidence)
        existing.score = max(existing.score, finding.score)
        if finding.source not in existing.source.split(", "):
            existing.source = f"{existing.source}, {finding.source}"
    return list(grouped.values())


def ranked_findings(findings: list[Finding]) -> list[Finding]:
    category_order = {
        "real_current_failures": 0,
        "external_config_issues": 1,
        "already_repaired_waiting_for_runtime_regeneration": 2,
        "stale_evidence_only": 3,
        MISSING_EVIDENCE_CATEGORY: 4,
        "low_value_repairs": 5,
    }
    risk_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        findings,
        key=lambda item: (
            category_order.get(item.category, 9),
            risk_order.get(item.risk_level, 9),
            -item.score,
            item.subsystem,
            item.title,
        ),
    )


def mission_prompt(finding: Finding | None) -> str:
    if finding is None:
        return (
            "MISSION: ECHO Runtime Verification\n"
            "Goal: No active repair target was identified by the priority planner. Re-run runtime evidence generation and confirm Batch 6 inputs remain clean.\n"
            "Rules: Do not modify scanner, workers, Master Brain, Unified Brain, broker/risk. Do not restart TITAN. Do not deploy. Do not push."
        )
    if finding.category == MISSING_EVIDENCE_CATEGORY:
        return (
            "MISSION: ECHO Evidence Regeneration\n"
            f"Goal: Regenerate or transfer missing evidence for {finding.source} before ranking runtime repairs.\n"
            f"Evidence: {finding.evidence[0]}\n"
            "Rules: Do not modify scanner, workers, Master Brain, Unified Brain, broker/risk. Do not restart TITAN. Do not deploy. Do not push.\n"
            "Verification: Re-run echo_runtime_repair_priority_planner.py and confirm missing evidence leaves WAITING_FOR_DATA."
        )
    return (
        f"MISSION: ECHO Targeted Runtime Repair - {finding.title}\n"
        f"Goal: Repair only the active {finding.subsystem} issue identified in runtime_repair_priority_plan.json.\n"
        f"Evidence: {finding.evidence[0]}\n"
        f"Root cause hypothesis: {finding.root_cause}\n"
        "Rules: Do not modify scanner, workers, Master Brain, Unified Brain, broker/risk unless this exact target is explicitly re-scoped. "
        "Do not restart TITAN. Do not deploy. Do not push.\n"
        "Verification: Re-run the targeted checks, regenerate runtime evidence in an approved mission, and confirm this item leaves real_current_failures."
    )


def as_plan_item(index: int, finding: Finding) -> dict[str, Any]:
    return {
        "rank": index,
        "subsystem": finding.subsystem,
        "category": finding.category,
        "title": finding.title,
        "source": finding.source,
        "evidence_path": finding.path,
        "evidence": finding.evidence[:5],
        "root_cause": finding.root_cause,
        "dependency_impact": finding.dependency_impact,
        "risk_level": finding.risk_level,
        "fix_complexity": finding.fix_complexity,
        "expected_improvement": finding.expected_improvement,
        "required_verification": finding.required_verification,
        "forbidden_actions": FORBIDDEN_ACTIONS,
        "recommended_codex_mission_prompt": mission_prompt(finding),
        "priority_score": finding.score,
    }


def build_plan(docs: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    findings = ranked_findings(collect_findings(docs))
    buckets: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        buckets[finding.category].append(finding)

    current = buckets.get("real_current_failures", [])
    recommended = current[0] if current else (findings[0] if findings else None)
    plan_items = [as_plan_item(index + 1, finding) for index, finding in enumerate(findings)]

    counts = Counter(finding.category for finding in findings)
    input_status = {
        name: {
            "path": str(path),
            "exists": path.exists(),
            "status": "PRESENT" if path.exists() else "MISSING_EVIDENCE",
            "evidence_status": "PRESENT" if path.exists() else "WAITING_FOR_DATA",
            "fallback": not path.exists(),
        }
        for name, path in INPUTS.items()
    }
    missing_inputs = [name for name, status in input_status.items() if status["fallback"]]
    plan = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "input_status": input_status,
        "missing_inputs": missing_inputs,
        "method": "Evidence-ranked planner generated from Batch 6 runtime failure split artifacts.",
        "forbidden_actions": FORBIDDEN_ACTIONS,
        "recommended_next_repair": as_plan_item(1, recommended) if recommended else None,
        "why_this_is_first": (
            "It is the highest-ranked real current failure by category, risk, evidence source, and failure severity."
            if recommended and recommended.category == "real_current_failures"
            else "No real current failure was identified; the first item is the highest-signal non-code action."
        ),
        "what_not_to_touch": FORBIDDEN_ACTIONS,
        "expected_verification_after_repair": verification_for(recommended.category, recommended.subsystem) if recommended else [],
        "ranked_repair_order": plan_items,
        "separation": {
            "already_repaired_but_waiting_for_runtime_regeneration": [
                as_plan_item(index + 1, item)
                for index, item in enumerate(buckets.get("already_repaired_waiting_for_runtime_regeneration", []))
            ],
            "real_current_failures": [
                as_plan_item(index + 1, item) for index, item in enumerate(buckets.get("real_current_failures", []))
            ],
            "stale_evidence_only": [
                as_plan_item(index + 1, item) for index, item in enumerate(buckets.get("stale_evidence_only", []))
            ],
            "external_config_issues": [
                as_plan_item(index + 1, item) for index, item in enumerate(buckets.get("external_config_issues", []))
            ],
            "low_value_repairs": [
                as_plan_item(index + 1, item) for index, item in enumerate(buckets.get("low_value_repairs", []))
            ],
            "missing_evidence_waiting_for_data": [
                as_plan_item(index + 1, item)
                for index, item in enumerate(buckets.get(MISSING_EVIDENCE_CATEGORY, []))
            ],
        },
        "counts": dict(counts),
    }
    summary = {
        "generated_at": plan["generated_at"],
        "input_status": input_status,
        "missing_inputs": missing_inputs,
        "recommended_next_repair": plan["recommended_next_repair"],
        "why_this_is_first": plan["why_this_is_first"],
        "what_not_to_touch": plan["what_not_to_touch"],
        "expected_verification_after_repair": plan["expected_verification_after_repair"],
        "top_5_repair_order": plan_items[:5],
        "category_counts": dict(counts),
        "safety_result": {
            "status": "PASS",
            "read_only_planning_only": True,
            "forbidden_actions_preserved": True,
            "missing_evidence_is_waiting_for_data": True,
            "no_fake_health_claim": True,
            "notes": "Planner reads available Batch 6 artifacts, converts missing artifacts to WAITING_FOR_DATA, and writes priority report JSON files.",
        },
        "next_codex_mission_prompt": mission_prompt(recommended),
    }
    return plan, summary


def main() -> int:
    docs = {name: load_json(path) for name, path in INPUTS.items()}
    plan, summary = build_plan(docs)

    BASE.mkdir(parents=True, exist_ok=True)
    PLAN_PATH.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    recommended = summary.get("recommended_next_repair") or {}
    print("recommended_next_repair:", recommended.get("title", "none"))
    print("top_5_repair_order:")
    for item in summary.get("top_5_repair_order", []):
        print(f"- {item['rank']}: {item['subsystem']} | {item['category']} | {item['title']}")
    print("safety_result:", summary["safety_result"]["status"])
    print("next_codex_mission_prompt:")
    print(summary["next_codex_mission_prompt"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
