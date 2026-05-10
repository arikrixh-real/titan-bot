"""
TITAN Phase 6 shadow observation reporting.

This module only aggregates Phase 6 metadata that was already attached to
evaluated setups. It does not scan symbols, fetch data, send alerts, create
trades, or influence ranking/execution.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")

REPORT_PATH = Path("reports/phase6_shadow_report.txt")
MEMORY_PATH = Path("data/memory/phase6_shadow_memory.json")
PHASE6_REPORT_REFRESH_SECONDS = 3600
MAX_OBSERVED_SETUPS = 15
MAX_PATTERN_ITEMS = 8


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _average(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _top_items(counter: Counter, limit: int = MAX_PATTERN_ITEMS) -> List[Dict[str, Any]]:
    return [
        {"pattern": str(pattern), "count": int(count)}
        for pattern, count in counter.most_common(limit)
        if pattern
    ]


def _is_refresh_throttled(report_path: Path, now: datetime) -> bool:
    if not report_path.exists():
        return False

    try:
        if "not yet refreshed" in report_path.read_text(encoding="utf-8")[:500]:
            return False
    except Exception:
        pass

    age_seconds = now.timestamp() - report_path.stat().st_mtime
    return age_seconds < PHASE6_REPORT_REFRESH_SECONDS


def build_phase6_shadow_summary(evaluated_setups: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Summarize already-generated Phase 6 metadata.

    Fail-open behavior is handled by the caller. This function intentionally
    limits itself to the same small candidate set Phase 6 studies.
    """

    observed = [
        setup
        for setup in (evaluated_setups or [])[:MAX_OBSERVED_SETUPS]
        if isinstance(setup, dict) and setup.get("phase6_applied") is True
    ]

    consensus_scores = []
    conflict_scores = []
    agreement_scores = []
    contradiction_types = Counter()
    weak_patterns = Counter()
    agreement_patterns = Counter()
    stance_distribution: Dict[str, Counter] = defaultdict(Counter)
    setups_with_contradictions = 0

    for setup in observed:
        consensus_scores.append(_safe_float(setup.get("consensus_score")))
        conflict_scores.append(_safe_float(setup.get("conflict_score")))
        agreement_scores.append(_safe_float(setup.get("agreement_confidence")))

        contradictions = setup.get("contradictions") or []
        if isinstance(contradictions, list) and contradictions:
            setups_with_contradictions += 1
            contradiction_types.update(str(item) for item in contradictions if item)

        opinions = setup.get("agent_opinions") or []
        if not isinstance(opinions, list):
            opinions = []

        for opinion in opinions:
            if not isinstance(opinion, dict):
                continue

            agent = str(opinion.get("agent") or "unknown_agent")
            stance = str(opinion.get("stance") or "UNKNOWN").upper()
            stance_distribution[agent][stance] += 1

            for warning in opinion.get("warnings") or []:
                weak_patterns[str(warning)] += 1

            if _safe_float(setup.get("agreement_confidence")) >= 65.0:
                for evidence in opinion.get("evidence") or []:
                    agreement_patterns[str(evidence)] += 1

    total_observed = len(observed)
    contradiction_frequency = (
        round(setups_with_contradictions / total_observed, 4)
        if total_observed
        else 0.0
    )

    return {
        "generated_at": datetime.now(IST).isoformat(),
        "observed_setup_count": total_observed,
        "average_consensus_score": _average(consensus_scores),
        "average_conflict_score": _average(conflict_scores),
        "contradiction_frequency": contradiction_frequency,
        "top_contradiction_types": _top_items(contradiction_types),
        "most_common_weak_setup_patterns": _top_items(weak_patterns),
        "strongest_agreement_patterns": _top_items(agreement_patterns),
        "average_agreement_confidence": _average(agreement_scores),
        "agent_stance_distributions": {
            agent: dict(counter)
            for agent, counter in sorted(stance_distribution.items())
        },
    }


def render_phase6_shadow_report(summary: Dict[str, Any]) -> str:
    lines = [
        "TITAN Phase 6 Shadow Observation Report",
        "======================================",
        "",
        "Safety",
        "- Shadow observation only.",
        "- Rankings, Telegram, alert caps, and execution are unchanged.",
        "- Aggregates only already-generated Phase 6 metadata.",
        "",
        f"Generated At: {summary.get('generated_at')}",
        f"Observed Setups: {summary.get('observed_setup_count', 0)}",
        f"Average Consensus Score: {summary.get('average_consensus_score', 0.0)}",
        f"Average Conflict Score: {summary.get('average_conflict_score', 0.0)}",
        f"Contradiction Frequency: {summary.get('contradiction_frequency', 0.0)}",
        f"Average Agreement Confidence: {summary.get('average_agreement_confidence', 0.0)}",
        "",
        "Top Contradiction Types:",
    ]

    for item in summary.get("top_contradiction_types", []) or []:
        lines.append(f"- {item.get('pattern')}: {item.get('count')}")
    if not summary.get("top_contradiction_types"):
        lines.append("- None observed")

    lines.append("")
    lines.append("Most Common Weak Setup Patterns:")
    for item in summary.get("most_common_weak_setup_patterns", []) or []:
        lines.append(f"- {item.get('pattern')}: {item.get('count')}")
    if not summary.get("most_common_weak_setup_patterns"):
        lines.append("- None observed")

    lines.append("")
    lines.append("Strongest Agreement Patterns:")
    for item in summary.get("strongest_agreement_patterns", []) or []:
        lines.append(f"- {item.get('pattern')}: {item.get('count')}")
    if not summary.get("strongest_agreement_patterns"):
        lines.append("- None observed")

    lines.append("")
    lines.append("Agent Stance Distributions:")
    distributions = summary.get("agent_stance_distributions", {}) or {}
    if distributions:
        for agent, counts in distributions.items():
            parts = ", ".join(f"{stance}: {count}" for stance, count in sorted(counts.items()))
            lines.append(f"- {agent}: {parts}")
    else:
        lines.append("- None observed")

    return "\n".join(lines) + "\n"


def refresh_phase6_shadow_report(evaluated_setups: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Throttled, fail-open Phase 6 report refresh.
    """

    try:
        now = datetime.now(IST)
        if _is_refresh_throttled(REPORT_PATH, now):
            return {"skipped": "CACHE_FRESH"}

        summary = build_phase6_shadow_summary(evaluated_setups or [])
        report = render_phase6_shadow_report(summary)

        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)

        REPORT_PATH.write_text(report, encoding="utf-8")
        MEMORY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

        return summary

    except Exception as exc:
        return {"error": str(exc)}
