import time


def build_report(packet):
    stats = packet.get("run_stats", {})
    lines = [
        "TITAN Knowledge Vault Runner",
        f"Generated at: {time.ctime(packet.get('generated_at', time.time()))}",
        "",
        "Safety: evidence-only packet. No broker, Telegram, Supabase, live risk, live strategy, or report vault mutation.",
        "",
        "Run summary:",
        f"- scanned_files: {stats.get('scanned_files', 0)}",
        f"- changed_files: {stats.get('changed_files', 0)}",
        f"- skipped_unchanged_files: {stats.get('skipped_unchanged_files', 0)}",
        f"- processed_chunks: {stats.get('processed_chunks', 0)}",
        f"- skipped_unchanged_chunks: {stats.get('skipped_unchanged_chunks', 0)}",
        f"- new_findings: {stats.get('new_findings', 0)}",
        "",
    ]
    warnings = packet.get("extraction_warnings", [])
    if warnings:
        lines.append("Insufficient extraction / warnings:")
        for warning in warnings[:20]:
            lines.append(f"- {warning.get('source_file')}: {warning.get('reason')}")
        lines.append("")
    lines.append("Top knowledge items:")
    top_items = packet.get("top_knowledge_items", [])[:20]
    if not top_items:
        lines.append("- Insufficient extraction: no strong concepts, lessons, or hypotheses were found.")
    for item in top_items:
        evidence = item.get("evidence", [{}])[0]
        lines.append(f"- [{item.get('type')}] importance={item.get('importance')} {item.get('text')}")
        lines.append(f"  evidence: {evidence.get('source_file')} chunk={evidence.get('chunk_id')}")
    lines.append("")
    lines.append("Research ideas:")
    for idea in packet.get("research_ideas", [])[:10]:
        lines.append(f"- {idea.get('text')}")
    if not packet.get("research_ideas"):
        lines.append("- None with enough evidence yet.")
    return "\n".join(lines) + "\n"

