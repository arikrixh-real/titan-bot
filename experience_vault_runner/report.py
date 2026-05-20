from datetime import datetime, timedelta, timezone


IST = timezone(timedelta(hours=5, minutes=30))


def build_report(packet):
    stats = packet.get("run_stats", {})
    lines = [
        "TITAN External Experience Vault Report",
        f"Generated: {datetime.now(IST).isoformat()}",
        "",
        "Safety:",
        "- source_type: EXTERNAL_EXPERIENCE",
        "- trust_level: IMPORTED_UNVALIDATED",
        "- no native trades imported",
        "- evidence packet only; Core must validate before merge",
        "",
        "Run Stats:",
    ]
    for key in sorted(stats):
        lines.append(f"- {key}: {stats[key]}")
    lines.extend(["", "Top Lessons:"])
    for lesson in packet.get("lessons", [])[:20]:
        status = lesson.get("status", "UNVALIDATED")
        lines.append(f"- [{status}] {lesson.get('label')}: {lesson.get('value')}")
    if packet.get("extraction_warnings"):
        lines.extend(["", "Warnings:"])
        for warning in packet.get("extraction_warnings", [])[:20]:
            lines.append(f"- {warning.get('source_file')}: {warning.get('reason')}")
    return "\n".join(lines) + "\n"

