from pathlib import Path

from consciousness_core.state import atomic_write_json, now_ist


REPORT_JSON_PATH = Path("data") / "consciousness_core" / "latest_consciousness_report.json"
REPORT_TXT_PATH = Path("data") / "consciousness_core" / "latest_consciousness_report.txt"


def write_report(
    state,
    reflection,
    weaknesses,
    goals,
    beliefs,
    missions,
    proposals,
    safety_decisions,
    observation_packet=None,
    approved_queue=None,
    path_json=REPORT_JSON_PATH,
    path_txt=REPORT_TXT_PATH,
):
    observation_packet = observation_packet or {}
    approved_queue = approved_queue or []
    top_beliefs = sorted(
        beliefs.values(),
        key=lambda belief: float(belief.get("confidence") or 0),
        reverse=True,
    )[:10]
    report = {
        "generated_at": now_ist(),
        "current_understanding": state.get("latest_summary", ""),
        "real_evidence_found": observation_packet.get("observation_count", 0),
        "unchanged_observations_skipped": observation_packet.get("unchanged_observation_count", 0),
        "missing_data": observation_packet.get("missing_patterns", []),
        "weaknesses_detected": len(weaknesses),
        "beliefs_changed": len(top_beliefs),
        "proposals_approved_for_testing": approved_queue,
        "proposals_rejected": [
            proposal_id for proposal_id, decision in safety_decisions.items() if decision == "REJECTED"
        ],
        "insufficient_evidence_areas": [
            proposal_id for proposal_id, decision in safety_decisions.items() if decision == "NEEDS_MORE_EVIDENCE"
        ],
        "active_weaknesses": weaknesses[:20],
        "active_goals": goals[:20],
        "top_beliefs": top_beliefs,
        "research_missions": missions[:20],
        "improvement_proposals": proposals[:20],
        "safety_decisions": safety_decisions,
        "next_focus": state.get("current_focus"),
    }
    atomic_write_json(path_json, report)
    lines = [
        "TITAN Consciousness Core v1",
        f"Generated: {report['generated_at']}",
        "",
        "Current understanding:",
        report["current_understanding"] or "No summary yet.",
        "",
        "Evidence:",
        f"- New evidence observations processed: {report['real_evidence_found']}",
        f"- Unchanged observations skipped by hash: {report['unchanged_observations_skipped']}",
        f"- Missing data patterns: {len(report['missing_data'])}",
        "",
        "Active weaknesses:",
    ]
    if weaknesses:
        lines.extend(
            f"- {item.get('severity')} {item.get('type')} in {item.get('affected_engine')}: {item.get('recommended_investigation')}"
            for item in weaknesses[:10]
        )
    else:
        lines.append("- None detected from new evidence this cycle.")
    lines.append("")
    lines.append("Active goals:")
    lines.extend(f"- {goal.get('priority')}: {goal.get('title')}" for goal in goals[:10])
    lines.append("")
    lines.append("Top beliefs:")
    lines.extend(f"- {belief.get('confidence')}: {belief.get('statement')}" for belief in top_beliefs[:10])
    lines.append("")
    lines.append("Research missions:")
    lines.extend(f"- {mission.get('priority')}: {mission.get('title')}" for mission in missions[:10])
    lines.append("")
    lines.append("Improvement proposals:")
    lines.extend(
        f"- {proposal.get('proposal_id')}: {proposal.get('target_engine')} -> {proposal.get('suggested_action')}"
        for proposal in proposals[:10]
    )
    lines.append("")
    lines.append("Safety decisions:")
    lines.extend(f"- {proposal_id}: {decision}" for proposal_id, decision in safety_decisions.items())
    lines.append("")
    lines.append("Insufficient evidence areas:")
    if report["insufficient_evidence_areas"]:
        lines.extend(f"- {proposal_id}" for proposal_id in report["insufficient_evidence_areas"])
    else:
        lines.append("- None from this cycle.")
    lines.append("")
    lines.append("Missing data:")
    if report["missing_data"]:
        lines.extend(f"- {pattern}" for pattern in report["missing_data"][:20])
    else:
        lines.append("- No configured source patterns missing.")
    lines.append("")
    lines.append(f"Next focus: {report['next_focus']}")
    path_txt.parent.mkdir(parents=True, exist_ok=True)
    path_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
