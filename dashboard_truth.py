import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from data.active_trade_store import canonical_open_trade_count


IST = ZoneInfo("Asia/Kolkata")
AUTHORITATIVE_RUNTIME_TRUTH_PATH = Path("data") / "runtime" / "authoritative_runtime_truth.json"
JOURNAL_TRUTH_UNIFICATION_PATH = Path("data") / "runtime" / "journal_truth_unification.json"
DASHBOARD_TRUTH_CONSOLIDATION_PATH = Path("data") / "runtime" / "dashboard_truth_consolidation.json"

RESTART_COMPONENTS = {
    "scanner": "scanner stale",
    "ohlc_health": "OHLC stale",
    "setup_engine": "setup stale/marker-only",
    "master_brain": "master brain stale/guard pending",
}
NON_LIVE_BLOCKING_STATUSES = {"STALE", "STOPPED", "UNKNOWN", "DEGRADED", "MARKER_ONLY", "REAL_BLOCKED"}


def _now_ist():
    return datetime.now(IST).isoformat()


def _read_json(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _component_map(authoritative_truth):
    components = authoritative_truth.get("components") if isinstance(authoritative_truth, dict) else {}
    return components if isinstance(components, dict) else {}


def _component_record(authoritative_truth, component):
    record = _component_map(authoritative_truth).get(component)
    return record if isinstance(record, dict) else {}


def component_display(authoritative_truth, component):
    record = _component_record(authoritative_truth, component)
    status = str(record.get("status") or "UNKNOWN").upper()
    return {
        "component": component,
        "status": status,
        "source_file": record.get("source_file"),
        "source_timestamp": record.get("source_timestamp"),
        "age_seconds": record.get("age_seconds"),
        "reason": record.get("reason") or "authoritative_runtime_truth_missing_component",
        "confidence": record.get("confidence"),
        "restart_blocker": bool(record.get("restart_blocker")),
    }


def master_brain_display_status(authoritative_truth):
    status = component_display(authoritative_truth, "master_brain")["status"]
    return "ACTIVE" if status == "LIVE" else status


def shadow_command_status(authoritative_truth):
    master = component_display(authoritative_truth, "master_brain")
    if master["status"] == "LIVE":
        return "ACTIVE"
    if master["status"] == "MARKER_ONLY":
        return "READ_ONLY"
    return master["status"]


def _summary(authoritative_truth):
    summary = authoritative_truth.get("summary") if isinstance(authoritative_truth, dict) else {}
    return summary if isinstance(summary, dict) else {}


def _restart_blockers(authoritative_truth, journal_truth):
    blockers = []
    components = _component_map(authoritative_truth)
    for component, label in RESTART_COMPONENTS.items():
        record = components.get(component)
        status = str((record or {}).get("status") or "UNKNOWN").upper()
        if status in NON_LIVE_BLOCKING_STATUSES:
            blockers.append(label)

    summary = _summary(authoritative_truth)
    for component in summary.get("restart_blockers") or []:
        label = f"{component} restart blocker"
        if label not in blockers:
            blockers.append(label)

    if isinstance(journal_truth, dict) and journal_truth.get("legacy_open_rows_warning"):
        blockers.append("journal legacy warning")

    return list(dict.fromkeys(blockers))


def _overall_status(authoritative_truth, journal_truth, blockers):
    summary = _summary(authoritative_truth)
    authoritative_status = str(summary.get("overall_status") or "UNKNOWN").upper()
    if authoritative_status == "STOPPED":
        return "STOPPED"
    if blockers or (isinstance(journal_truth, dict) and journal_truth.get("restart_blocker")):
        return "RESTART_BLOCKED"
    if authoritative_status in {"DEGRADED", "STALE"}:
        return authoritative_status
    if any(component["status"] == "STALE" for component in _rendered_components(authoritative_truth).values()):
        return "STALE"
    if authoritative_status == "LIVE":
        return "CLEAN"
    return authoritative_status if authoritative_status in {"CLEAN", "UNKNOWN"} else "DEGRADED"


def _rendered_components(authoritative_truth):
    return {
        component: component_display(authoritative_truth, component)
        for component in sorted(_component_map(authoritative_truth).keys())
    }


def build_dashboard_truth_consolidation(
    authoritative_truth=None,
    journal_truth=None,
    *,
    write=False,
    output_path=DASHBOARD_TRUTH_CONSOLIDATION_PATH,
):
    authoritative_truth = (
        authoritative_truth
        if isinstance(authoritative_truth, dict)
        else _read_json(AUTHORITATIVE_RUNTIME_TRUTH_PATH)
    )
    journal_truth = (
        journal_truth
        if isinstance(journal_truth, dict)
        else _read_json(JOURNAL_TRUTH_UNIFICATION_PATH)
    )
    active_trade_count = int(
        journal_truth.get("canonical_open_trade_count")
        if isinstance(journal_truth, dict) and journal_truth.get("canonical_open_trade_count") is not None
        else canonical_open_trade_count()
    )
    components = _rendered_components(authoritative_truth)
    blockers = _restart_blockers(authoritative_truth, journal_truth)
    stale_components = [
        name
        for name, record in components.items()
        if record["status"] in {"STALE", "MARKER_ONLY", "UNKNOWN", "STOPPED", "DEGRADED"}
    ]
    overall = _overall_status(authoritative_truth, journal_truth, blockers)
    payload = {
        "generated_at": _now_ist(),
        "authoritative_runtime_truth_loaded": bool(authoritative_truth),
        "journal_truth_loaded": bool(journal_truth),
        "dashboard_overall_status": overall,
        "active_trade_count_source": "data/runtime/journal_truth_unification.json:canonical_open_trade_count",
        "active_trade_count": active_trade_count,
        "legacy_warning_visible": bool(journal_truth.get("legacy_open_rows_warning")) if isinstance(journal_truth, dict) else False,
        "stale_components_visible": stale_components,
        "components_rendered_from_authoritative_truth": components,
        "fallback_sources_disabled": [
            "supabase_runtime_status",
            "github_runtime_health",
            "dashboard_sync_active_flags",
            "legacy_active_trade_files",
            "trade_results_open_rows",
            "engine_development_progress_runtime_health",
        ],
        "supabase_runtime_override_disabled": True,
        "restart_allowed": False if blockers or overall in {"STOPPED", "STALE", "DEGRADED", "RESTART_BLOCKED", "UNKNOWN"} else True,
        "restart_blockers": blockers,
        "remaining_unknowns": [] if authoritative_truth and journal_truth else [
            "authoritative_runtime_truth_missing" if not authoritative_truth else "",
            "journal_truth_unification_missing" if not journal_truth else "",
        ],
        "master_brain_display_status": master_brain_display_status(authoritative_truth),
        "shadow_command_center_status": shadow_command_status(authoritative_truth),
    }
    payload["remaining_unknowns"] = [item for item in payload["remaining_unknowns"] if item]
    if write:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    return payload
