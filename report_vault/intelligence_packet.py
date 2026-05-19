from report_vault.report_schema import now_ist, report_sort_key, stable_hash


def _finding_key(finding):
    text = str(finding or "").strip().lower()
    return " ".join(text.split())


def merge_duplicate_findings(reports):
    merged = {}
    for report in reports:
        for finding in report.get("key_findings", []) or []:
            key = _finding_key(finding)
            if not key:
                continue
            item = merged.setdefault(
                key,
                {
                    "finding": str(finding),
                    "sources": [],
                    "severity": report.get("severity"),
                    "actionability_score": 0.0,
                    "evidence": [],
                },
            )
            item["sources"].append(report.get("source_worker"))
            item["actionability_score"] = max(
                float(item.get("actionability_score") or 0.0),
                float(report.get("actionability_score") or 0.0),
            )
            item["evidence"].extend((report.get("evidence") or [])[:3])
            if report_sort_key(report) > (
                {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}.get(str(item.get("severity")).upper(), 1),
                item["actionability_score"],
                "",
            ):
                item["severity"] = report.get("severity")
    findings = list(merged.values())
    for item in findings:
        item["sources"] = sorted({source for source in item["sources"] if source})
        item["evidence"] = item["evidence"][:5]
    return sorted(
        findings,
        key=lambda item: (
            {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}.get(str(item.get("severity")).upper(), 1),
            float(item.get("actionability_score") or 0.0),
        ),
        reverse=True,
    )


def detect_conflicts(reports):
    by_subject = {}
    conflicts = []
    for report in reports:
        subject = str(report.get("report_type") or report.get("source_worker") or "unknown").lower()
        by_subject.setdefault(subject, []).append(report)
    for subject, group in by_subject.items():
        statuses = {str(item.get("status") or "").upper() for item in group}
        severities = {str(item.get("severity") or "").upper() for item in group}
        if ("OK" in statuses and ({"ERROR", "WARNING", "STALE"} & statuses)) or (
            "LOW" in severities and ({"HIGH", "CRITICAL"} & severities)
        ):
            conflicts.append(
                {
                    "subject": subject,
                    "statuses": sorted(statuses),
                    "severities": sorted(severities),
                    "sources": sorted({item.get("source_worker") for item in group if item.get("source_worker")}),
                }
            )
    return conflicts


def identify_missing_data(reports):
    missing = []
    if not reports:
        return ["no structured reports available in report vault"]
    for report in reports:
        quality = str(report.get("data_quality") or "").upper()
        if quality in {"LOW", "MISSING", "UNKNOWN", "STALE"}:
            missing.append(
                {
                    "source_worker": report.get("source_worker"),
                    "report_type": report.get("report_type"),
                    "data_quality": report.get("data_quality"),
                    "summary": report.get("summary"),
                }
            )
    return missing[:20]


def build_intelligence_packet(reports, source_window_hours=24):
    reports = list(reports or [])
    ranked_reports = sorted(reports, key=report_sort_key, reverse=True)
    merged_findings = merge_duplicate_findings(ranked_reports)
    conflicts = detect_conflicts(ranked_reports)
    missing_data = identify_missing_data(ranked_reports)
    top_reports = ranked_reports[:20]
    summary = summarize_packet(top_reports, merged_findings, conflicts, missing_data)
    packet = {
        "packet_version": 1,
        "generated_at": now_ist(),
        "source_window_hours": source_window_hours,
        "report_count": len(reports),
        "source_workers": sorted({report.get("source_worker") for report in reports if report.get("source_worker")}),
        "summary": summary,
        "ranked_reports": [
            {
                "report_id": report.get("report_id"),
                "source_worker": report.get("source_worker"),
                "report_type": report.get("report_type"),
                "created_at": report.get("created_at"),
                "status": report.get("status"),
                "severity": report.get("severity"),
                "summary": report.get("summary"),
                "actionability_score": report.get("actionability_score"),
                "content_hash": report.get("content_hash"),
            }
            for report in top_reports
        ],
        "merged_findings": merged_findings[:50],
        "conflicts": conflicts[:20],
        "missing_data": missing_data,
        "trusted_summarized_input": True,
        "safety_scope": "summarized_context_only_no_live_execution_no_strategy_or_risk_mutation",
    }
    packet["packet_hash"] = stable_hash(packet)
    return packet


def summarize_packet(top_reports, merged_findings, conflicts, missing_data):
    if not top_reports:
        return "No recent structured reports were available in the report vault."
    highest = top_reports[0]
    parts = [
        f"{len(top_reports)} recent reports reviewed",
        f"top signal: {highest.get('severity')} {highest.get('source_worker')} - {highest.get('summary')}",
        f"{len(merged_findings)} unique findings after merge",
    ]
    if conflicts:
        parts.append(f"{len(conflicts)} report conflicts need review")
    if missing_data:
        parts.append(f"{len(missing_data)} missing or low-quality data areas detected")
    return "; ".join(parts) + "."


def packet_to_text(packet):
    lines = [
        "TITAN Report Vault Intelligence Packet",
        f"Generated: {packet.get('generated_at')}",
        f"Reports reviewed: {packet.get('report_count')}",
        "",
        "Summary:",
        packet.get("summary") or "No summary.",
        "",
        "Top ranked reports:",
    ]
    reports = packet.get("ranked_reports") or []
    if reports:
        lines.extend(
            f"- {item.get('severity')} {item.get('source_worker')} ({item.get('report_type')}): {item.get('summary')}"
            for item in reports[:10]
        )
    else:
        lines.append("- None.")
    lines.append("")
    lines.append("Merged findings:")
    findings = packet.get("merged_findings") or []
    if findings:
        lines.extend(
            f"- {item.get('severity')} score={item.get('actionability_score')}: {item.get('finding')} [{', '.join(item.get('sources', []))}]"
            for item in findings[:10]
        )
    else:
        lines.append("- None.")
    lines.append("")
    lines.append("Conflicts:")
    conflicts = packet.get("conflicts") or []
    if conflicts:
        lines.extend(
            f"- {item.get('subject')}: statuses={item.get('statuses')} severities={item.get('severities')}"
            for item in conflicts[:10]
        )
    else:
        lines.append("- None detected.")
    lines.append("")
    lines.append("Missing data:")
    missing = packet.get("missing_data") or []
    if missing:
        for item in missing[:10]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('source_worker')} ({item.get('report_type')}): {item.get('data_quality')}")
            else:
                lines.append(f"- {item}")
    else:
        lines.append("- None flagged.")
    lines.append("")
    lines.append("Safety: summarized context only; no live execution, strategy, risk, broker, Telegram, or Supabase mutation.")
    return "\n".join(lines) + "\n"
