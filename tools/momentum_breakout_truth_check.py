import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNER_STATUS_PATH = ROOT / "data" / "runtime" / "scanner_status.json"
AUDIT_PATH = ROOT / "data" / "runtime" / "momentum_breakout_counter_audit.json"
DASHBOARD_PATH = ROOT / "dashboard.py"
RUNTIME_SCANNER_PATH = ROOT / "runtime_scanner.py"
SCANNER_FILTER_TRUTH_PATH = ROOT / "scanner_filter_truth.py"


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def read_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def first_int(payload, *keys):
    for key in keys:
        value = payload.get(key) if isinstance(payload, dict) else None
        if value in (None, ""):
            continue
        try:
            return int(float(value))
        except Exception:
            continue
    return 0


def dashboard_mapping_correct():
    text = read_text(DASHBOARD_PATH)
    momentum_pattern = r'"momentum_passed":\s*int\(first_number\(preferred_payload\.get\("momentum_passed"\)'
    raw_breakout_pattern = r'"raw_breakout_ready_count":\s*int\(first_number\(preferred_payload\.get\("raw_breakout_ready_count"\),\s*preferred_payload\.get\("raw_breakout_ready"\)'
    qualified_breakout_pattern = r'"qualified_breakout_ready_count":\s*int\(first_number\(preferred_payload\.get\("qualified_breakout_ready_count"\),\s*preferred_payload\.get\("breakout_ready_count"\)'
    compatibility_breakout_pattern = r'"breakout_ready_count":\s*int\(first_number\(preferred_payload\.get\("breakout_ready_count"\),\s*preferred_payload\.get\("qualified_breakout_ready_count"\)'
    bad_breakout_patterns = [
        r'"breakout_ready_count":\s*int\(first_number\(preferred_payload\.get\("momentum_passed"',
        r'"breakout_ready_count":\s*int\(first_number\(preferred_payload\.get\("breakout_ready_count"\),\s*preferred_payload\.get\("entry_passed"\)',
        r"latest_breakout_ready\s*=\s*scan_breakdown\.get\(\"breakout_ready_count\",\s*latest_entry_passed\)",
    ]
    return (
        bool(re.search(momentum_pattern, text))
        and bool(re.search(raw_breakout_pattern, text))
        and bool(re.search(qualified_breakout_pattern, text))
        and bool(re.search(compatibility_breakout_pattern, text))
        and "Raw Breakout Ready" in text
        and "Qualified Breakout" in text
        and not any(re.search(pattern, text) for pattern in bad_breakout_patterns)
    )


def exact_same_source(scanner_status):
    sources = scanner_status.get("counter_sources") if isinstance(scanner_status.get("counter_sources"), dict) else {}
    momentum_source = sources.get("momentum_passed")
    breakout_source = sources.get("breakout_ready")
    if not momentum_source or not breakout_source:
        return False
    return momentum_source == breakout_source


def scanner_increment_alias_detected():
    text = read_text(RUNTIME_SCANNER_PATH)
    alias_patterns = [
        r"breakout_ready_count\s*=\s*momentum_passed",
        r"breakout_ready_count\s*\+=\s*momentum_passed",
        r"breakout_ready_count\s*=\s*momentum_passed_count",
        r'"breakout_ready_count":\s*momentum_passed',
    ]
    return any(re.search(pattern, text) for pattern in alias_patterns)


def fallback_maps_breakout_to_momentum():
    text = read_text(SCANNER_FILTER_TRUTH_PATH)
    bad_patterns = [
        r'"breakout_ready":\s*\("momentum_passed',
        r"breakout_ready.*momentum_passed_count",
    ]
    return any(re.search(pattern, text) for pattern in bad_patterns)


def summarize_from_audit(audit, scanner_status):
    records = audit.get("records") if isinstance(audit.get("records"), list) else []
    if records:
        overlap = sum(1 for row in records if row.get("momentum_passed") and row.get("breakout_ready"))
        raw_breakout_only = sum(1 for row in records if row.get("breakout_ready") and not row.get("momentum_passed"))
        qualified_breakout_only = sum(
            1
            for row in records
            if row.get("counted_breakout_ready") and not row.get("counted_momentum_passed")
        )
        neither = sum(1 for row in records if not row.get("momentum_passed") and not row.get("breakout_ready"))
    else:
        overlap = int(audit.get("overlap_count") or 0)
        raw_breakout_only = int(audit.get("raw_breakout_only_count") or audit.get("breakout_only_count") or 0)
        qualified_breakout_only = int(audit.get("qualified_breakout_only_count") or 0)
        neither = int(audit.get("neither_count") or 0)

    return {
        "momentum_passed_count": first_int(scanner_status, "momentum_passed", "momentum_passed_count")
        or int(audit.get("momentum_passed_count") or 0),
        "raw_breakout_ready_count": first_int(scanner_status, "raw_breakout_ready_count", "raw_breakout_ready")
        or int(audit.get("raw_breakout_ready_count") or 0),
        "qualified_breakout_ready_count": first_int(scanner_status, "qualified_breakout_ready_count", "breakout_ready_count", "breakout_ready")
        or int(audit.get("breakout_ready_count") or 0),
        "overlap_count": overlap,
        "raw_breakout_only_count": raw_breakout_only,
        "qualified_breakout_only_count": qualified_breakout_only,
        "neither_count": neither,
    }


def suspicious_reason(summary, scanner_status, audit):
    reasons = []
    if summary["momentum_passed_count"] == summary["qualified_breakout_ready_count"]:
        reasons.append("QUALIFIED_COUNTS_IDENTICAL")
    if scanner_increment_alias_detected():
        reasons.append("RUNTIME_SCANNER_ALIAS_PATTERN_FOUND")
    if exact_same_source(scanner_status):
        reasons.append("SCANNER_STATUS_SAME_COUNTER_SOURCE")
    if fallback_maps_breakout_to_momentum():
        reasons.append("FALLBACK_MAPS_BREAKOUT_TO_MOMENTUM")
    if not dashboard_mapping_correct():
        reasons.append("DASHBOARD_MAPPING_SUSPECT")
    audit_reason = audit.get("suspicious_identical_reason")
    if audit_reason and audit_reason != "NOT_IDENTICAL_OR_NATURAL_DIVERGENCE":
        reasons.append(f"AUDIT:{audit_reason}")
    if not reasons:
        return "NOT_IDENTICAL_OR_NATURAL_DIVERGENCE"
    return ";".join(dict.fromkeys(reasons))


def main():
    scanner_status = read_json(SCANNER_STATUS_PATH)
    audit = read_json(AUDIT_PATH)
    summary = summarize_from_audit(audit, scanner_status)
    same_source = exact_same_source(scanner_status) or scanner_increment_alias_detected() or fallback_maps_breakout_to_momentum()
    mapping_ok = dashboard_mapping_correct()

    print(f"momentum_passed_count: {summary['momentum_passed_count']}")
    print(f"raw_breakout_ready_count: {summary['raw_breakout_ready_count']}")
    print(f"qualified_breakout_ready_count: {summary['qualified_breakout_ready_count']}")
    print(f"overlap_count: {summary['overlap_count']}")
    print(f"raw_breakout_only_count: {summary['raw_breakout_only_count']}")
    print(f"qualified_breakout_only_count: {summary['qualified_breakout_only_count']}")
    print(f"dashboard_mapping_correct? {'YES' if mapping_ok else 'NO'}")
    print(f"exact_same_source: {'YES' if same_source else 'NO'}")
    print(f"suspicious_identical_reason: {suspicious_reason(summary, scanner_status, audit)}")


if __name__ == "__main__":
    main()
