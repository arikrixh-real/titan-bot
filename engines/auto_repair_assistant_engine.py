"""
TITAN Phase 37 - Auto-Repair Assistant Engine

Diagnostic-only assistant for runtime errors, GitHub run issues, dependency
problems, and maintenance recommendations. It never edits or deletes files.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List


REPORT_PATH = os.path.join("data", "auto_repair", "latest_auto_repair_report.json")


def safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return float(default)
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        return float(value)
    except Exception:
        return float(default)


def safe_text(value, default=""):
    try:
        if value is None:
            return str(default)
        return str(value).strip()
    except Exception:
        return str(default)


def safe_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    return [value]


def clamp(value, min_value=0.0, max_value=100.0):
    try:
        value = safe_float(value, min_value)
        return max(float(min_value), min(float(max_value), value))
    except Exception:
        return float(min_value)


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def normalize_error_logs(error_logs=None, runtime_context=None):
    logs = []
    for item in safe_list(error_logs):
        text = safe_text(item)
        if text:
            logs.append(text)
    context = _as_dict(runtime_context)
    for key in ("errors", "runtime_errors", "last_error", "warnings"):
        value = context.get(key)
        for item in safe_list(value):
            text = safe_text(item)
            if text:
                logs.append(text)
    seen = set()
    deduped = []
    for text in logs:
        if text not in seen:
            seen.add(text)
            deduped.append(text)
    return deduped


def classify_error(error_text=None):
    text = safe_text(error_text)
    lower = text.lower()
    if not text:
        category = "NONE"
    elif "syntaxerror" in lower or "indentationerror" in lower:
        category = "SYNTAX_ERROR"
    elif "modulenotfounderror" in lower or "importerror" in lower or "no module named" in lower:
        category = "IMPORT_ERROR"
    elif "permissionerror" in lower or "winerror 10013" in lower or "access permissions" in lower:
        category = "PERMISSION_OR_SOCKET"
    elif "timeout" in lower or "cancelled" in lower or "canceled" in lower:
        category = "TIMEOUT_OR_CANCELLED"
    elif "supabase" in lower or "socket" in lower or "connection" in lower:
        category = "NETWORK_OR_SERVICE"
    elif "keyerror" in lower or "typeerror" in lower or "attributeerror" in lower or "valueerror" in lower:
        category = "RUNTIME_EXCEPTION"
    elif "failed" in lower or "error" in lower or "exception" in lower:
        category = "GENERAL_ERROR"
    else:
        category = "INFO_OR_WARNING"
    return {"category": category, "error_excerpt": text[:240]}


def detect_suspected_module(error_text=None, runtime_context=None):
    text = safe_text(error_text)
    lower = text.lower()
    modules = []
    known = [
        "master_controller",
        "final_decision_engine",
        "alert_execution_filter",
        "daily_alert_manager",
        "news_engine",
        "market_close",
        "supabase",
        "telegram",
        "execution_engine",
        "outcome_tracker",
    ]
    for name in known:
        if name in lower:
            modules.append(name)
    if "winerror 10013" in lower or "socket" in lower or "access permissions" in lower:
        modules.extend(["market_close", "supabase", "socket"])
    context = _as_dict(runtime_context)
    active = safe_text(context.get("active_module") or context.get("module"))
    if active:
        modules.append(active)
    deduped = []
    for module in modules:
        if module not in deduped:
            deduped.append(module)
    return deduped or ["UNKNOWN"]


def calculate_error_severity(error_text=None, runtime_context=None):
    classification = classify_error(error_text)
    category = classification.get("category")
    context = _as_dict(runtime_context)
    blocked = bool(context.get("cycle_blocked") or context.get("blocking") or context.get("failed"))
    text = safe_text(error_text).lower()
    severity = 0.0
    if category == "SYNTAX_ERROR":
        severity = 95.0
    elif category == "IMPORT_ERROR":
        severity = 72.0
    elif category == "PERMISSION_OR_SOCKET":
        severity = 38.0
    elif category == "TIMEOUT_OR_CANCELLED":
        severity = 62.0
    elif category == "NETWORK_OR_SERVICE":
        severity = 48.0
    elif category == "RUNTIME_EXCEPTION":
        severity = 58.0
    elif category == "GENERAL_ERROR":
        severity = 45.0
    elif category == "INFO_OR_WARNING":
        severity = 20.0
    if blocked:
        severity += 18.0
    if "winerror 10013" in text and not blocked:
        severity = min(severity, 42.0)
    return round(clamp(severity), 2)


def classify_urgent_vs_ignorable(error_text=None, severity_score=0):
    severity = safe_float(severity_score, 0.0)
    category = classify_error(error_text).get("category")
    if category == "SYNTAX_ERROR" or severity >= 75.0:
        return "URGENT"
    if severity >= 35.0:
        return "REVIEW"
    return "IGNORABLE"


def diagnose_github_run(github_logs=None, runtime_context=None):
    logs = "\n".join(safe_text(item) for item in safe_list(github_logs) if safe_text(item))
    lower = logs.lower()
    status = "UNKNOWN"
    issues = []
    if not logs:
        status = "NO_GITHUB_LOGS"
    elif ("cancelled" in lower or "canceled" in lower) and "not cancelled" not in lower and "not canceled" not in lower:
        status = "CANCELLED"
        issues.append("GitHub run appears cancelled.")
    elif "timed out" in lower or "timeout" in lower or "exceeded" in lower:
        status = "TIMEOUT"
        issues.append("GitHub run appears to have timed out.")
    elif "modulenotfounderror" in lower or "no module named" in lower:
        status = "DEPENDENCY_FAILURE"
        issues.append("GitHub run likely missing dependency or package path.")
    elif "syntaxerror" in lower:
        status = "CODE_FAILURE"
        issues.append("GitHub run has syntax-level failure.")
    elif "error" in lower or "failed" in lower:
        status = "FAILED_REVIEW"
        issues.append("GitHub run contains failure markers.")
    else:
        status = "NO_BLOCKING_FAILURE_DETECTED"
    return {"status": status, "issues": issues, "log_length": len(logs)}


def detect_dependency_issue(error_logs=None):
    logs = normalize_error_logs(error_logs)
    missing = []
    dependency_markers = []
    for text in logs:
        lower = text.lower()
        if "modulenotfounderror" in lower or "no module named" in lower:
            dependency_markers.append(text[:240])
            parts = text.replace('"', "'").split("'")
            if len(parts) >= 2:
                missing.append(parts[1])
        elif "importerror" in lower or "pip" in lower or "requirements" in lower:
            dependency_markers.append(text[:240])
    return {
        "dependency_issue_detected": bool(dependency_markers),
        "missing_modules": sorted(set(missing)),
        "evidence": dependency_markers[:10],
    }


def build_debug_summary(error_logs=None, runtime_context=None):
    logs = normalize_error_logs(error_logs, runtime_context)
    if not logs:
        return "No runtime error logs were provided. System appears healthy from available diagnostic input."
    classifications = [classify_error(log).get("category") for log in logs]
    worst = max(calculate_error_severity(log, runtime_context) for log in logs)
    modules = []
    for log in logs:
        modules.extend(detect_suspected_module(log, runtime_context))
    modules = sorted(set(modules))
    return (
        f"Detected {len(logs)} diagnostic log item(s). "
        f"Categories: {', '.join(sorted(set(classifications)))}. "
        f"Suspected modules: {', '.join(modules)}. "
        f"Highest severity: {round(worst, 2)}."
    )


def generate_recommended_fixes(error_logs=None, runtime_context=None):
    logs = normalize_error_logs(error_logs, runtime_context)
    fixes = []
    if not logs:
        return ["No code change recommended. Continue normal monitoring."]
    for log in logs:
        category = classify_error(log).get("category")
        lower = log.lower()
        if category == "SYNTAX_ERROR":
            fixes.append("Human review: run py_compile on the reported file and fix the syntax location.")
        elif category == "IMPORT_ERROR":
            fixes.append("Human review: confirm module path, package install, and requirements entry before deployment.")
        elif "winerror 10013" in lower:
            fixes.append("Human review: inspect market-close/Supabase/socket permissions; keep as REVIEW if cycle completes.")
        elif category == "TIMEOUT_OR_CANCELLED":
            fixes.append("Human review: inspect GitHub runner duration, caching, and slow network calls.")
        elif category == "NETWORK_OR_SERVICE":
            fixes.append("Human review: validate service credentials, socket/network policy, and retry behavior.")
        elif category == "RUNTIME_EXCEPTION":
            fixes.append("Human review: add defensive parsing around the suspected runtime field or module.")
    deduped = []
    for fix in fixes:
        if fix not in deduped:
            deduped.append(fix)
    return deduped or ["Human review: inspect logs and reproduce locally before making changes."]


def generate_maintenance_recommendations(error_logs=None, runtime_context=None):
    logs = normalize_error_logs(error_logs, runtime_context)
    recommendations = [
        "Keep diagnostic fixes human-reviewed; auto_file_changes_allowed remains false.",
        "Preserve fail-open behavior for TITAN orchestration and fail-closed behavior for live execution.",
    ]
    if logs:
        recommendations.append("Archive recurring non-blocking warnings separately from blocking failures.")
        recommendations.append("Add targeted compile/import checks for modules named in suspected_modules.")
    else:
        recommendations.append("No immediate maintenance action required from available logs.")
    return recommendations


def _data_mode(error_logs, runtime_context, github_logs):
    logs = normalize_error_logs(error_logs, runtime_context)
    github = [safe_text(item) for item in safe_list(github_logs) if safe_text(item)]
    context = _as_dict(runtime_context)
    if logs or github:
        return "REAL_ERRORS"
    if context:
        return "PROXY"
    return "INSUFFICIENT"


def _save_report(report):
    try:
        os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
    except Exception:
        pass


def build_auto_repair_report(error_logs=None, runtime_context=None, github_logs=None):
    runtime_context = _as_dict(runtime_context)
    logs = normalize_error_logs(error_logs, runtime_context)
    mode = _data_mode(error_logs, runtime_context, github_logs)
    explanations: List[str] = []

    classifications = [classify_error(log) for log in logs]
    severities = [calculate_error_severity(log, runtime_context) for log in logs]
    severity = max(severities or [0.0])
    modules = []
    for log in logs:
        modules.extend(detect_suspected_module(log, runtime_context))
    suspected_modules = sorted(set(modules)) if modules else []
    urgency = classify_urgent_vs_ignorable(logs[0] if logs else "", severity)
    github = diagnose_github_run(github_logs, runtime_context)
    dependency = detect_dependency_issue(logs)
    debug_summary = build_debug_summary(logs, runtime_context)
    fixes = generate_recommended_fixes(logs, runtime_context)
    maintenance = generate_maintenance_recommendations(logs, runtime_context)

    github_status = safe_text(github.get("status"))
    if github_status in {"TIMEOUT", "CANCELLED", "DEPENDENCY_FAILURE", "CODE_FAILURE"}:
        severity = max(severity, 62.0)
        urgency = "REVIEW" if severity < 75.0 else "URGENT"
    if dependency.get("dependency_issue_detected"):
        severity = max(severity, 68.0)
        urgency = "REVIEW" if severity < 75.0 else "URGENT"

    if not logs and mode == "INSUFFICIENT":
        repair_status = "HEALTHY"
        auto_repair_score = 100.0
        urgency = "IGNORABLE"
        explanations.append("No diagnostic logs available; healthy insufficient-mode report created.")
    else:
        auto_repair_score = 100.0 - severity
        if severity >= 85.0:
            repair_status = "CRITICAL"
        elif severity >= 60.0:
            repair_status = "ATTENTION"
        elif severity >= 30.0:
            repair_status = "REVIEW"
        else:
            repair_status = "HEALTHY"
        explanations.append(f"{mode} repair diagnosis completed with human-review recommendations only.")

    if "winerror 10013" in " ".join(logs).lower() and repair_status != "CRITICAL":
        explanations.append("WinError 10013 classified as REVIEW unless it blocks the cycle.")

    report = {
        "advisory_only": True,
        "diagnostic_only": True,
        "shadow_mode": True,
        "live_order_allowed": False,
        "live_rank_mutation_allowed": False,
        "pyramid_placement": "master_controller_diagnostic_sidecar",
        "repair_data_mode": mode,
        "error_classification": {
            "count": len(classifications),
            "items": classifications,
        },
        "suspected_modules": suspected_modules,
        "severity_score": round(clamp(severity), 2),
        "urgency": urgency if urgency in {"URGENT", "REVIEW", "IGNORABLE"} else "REVIEW",
        "github_run_diagnosis": github,
        "dependency_issues": dependency,
        "debug_summary": debug_summary,
        "recommended_fixes": fixes,
        "maintenance_recommendations": maintenance,
        "auto_repair_score": round(clamp(auto_repair_score), 2),
        "repair_status": repair_status,
        "live_order_allowed": False,
        "auto_file_changes_allowed": False,
        "explanations": explanations,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    _save_report(report)
    return report


if __name__ == "__main__":
    sample_errors = [
        "[MarketClose ERROR] [WinError 10013] An attempt was made to access a socket in a way forbidden by its access permissions",
        "ModuleNotFoundError: No module named 'example_missing_package'",
    ]
    sample_github = "Run completed but one dependency check failed; job was not cancelled."
    print(
        json.dumps(
            build_auto_repair_report(
                error_logs=sample_errors,
                runtime_context={"cycle_blocked": False, "active_module": "master_controller"},
                github_logs=sample_github,
            ),
            indent=2,
            sort_keys=True,
        )
    )
