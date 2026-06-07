from pathlib import Path

from dashboard_truth import build_dashboard_truth_consolidation


def _truth(overall="LIVE", **component_statuses):
    components = {}
    for name, status in component_statuses.items():
        components[name] = {
            "component": name,
            "status": status,
            "source_file": f"data/runtime/{name}.json",
            "source_timestamp": "2026-06-07T12:00:00+05:30",
            "age_seconds": 120,
            "reason": f"{name}_{status.lower()}",
            "confidence": "HIGH",
            "restart_blocker": status in {"STOPPED", "STALE", "MARKER_ONLY"},
        }
    return {
        "components": components,
        "summary": {
            "overall_status": overall,
            "restart_blockers": [
                name for name, status in component_statuses.items() if status in {"STOPPED", "STALE", "MARKER_ONLY"}
            ],
        },
    }


def test_master_brain_stale_renders_stale():
    payload = build_dashboard_truth_consolidation(
        _truth(master_brain="STALE"),
        {"canonical_open_trade_count": 0},
    )

    assert payload["master_brain_display_status"] == "STALE"
    assert payload["components_rendered_from_authoritative_truth"]["master_brain"]["status"] == "STALE"


def test_runtime_stopped_renders_stopped():
    payload = build_dashboard_truth_consolidation(
        _truth("STOPPED", daemon="STOPPED"),
        {"canonical_open_trade_count": 0},
    )

    assert payload["dashboard_overall_status"] == "STOPPED"
    assert payload["restart_allowed"] is False


def test_active_live_trades_come_from_canonical_journal_count_only():
    payload = build_dashboard_truth_consolidation(
        _truth("LIVE", daemon="LIVE", scanner="LIVE", ohlc_health="LIVE", setup_engine="LIVE", master_brain="LIVE"),
        {
            "canonical_open_trade_count": 0,
            "legacy_open_rows_by_file": {"data/journals/active_trades_old.csv": 99},
            "legacy_open_rows_warning": True,
        },
    )

    assert payload["active_trade_count"] == 0
    assert payload["legacy_warning_visible"] is True


def test_supabase_runtime_fallback_cannot_override_local_stopped():
    payload = build_dashboard_truth_consolidation(
        _truth("STOPPED", daemon="STOPPED"),
        {"canonical_open_trade_count": 0},
    )

    assert payload["supabase_runtime_override_disabled"] is True
    assert "supabase_runtime_status" in payload["fallback_sources_disabled"]
    assert payload["dashboard_overall_status"] == "STOPPED"


def test_capability_progress_is_not_runtime_health():
    source = Path("dashboard.py").read_text(encoding="utf-8")

    assert "Capability Progress" in source
    assert "Engine Development Progress" not in source
    assert "it is not runtime health" in source


def test_shadow_command_center_cannot_show_active_without_fresh_proof():
    payload = build_dashboard_truth_consolidation(
        _truth(master_brain="STALE"),
        {"canonical_open_trade_count": 0},
    )

    assert payload["shadow_command_center_status"] == "STALE"


def test_restart_banner_blocked_while_core_inputs_stale():
    payload = build_dashboard_truth_consolidation(
        _truth(
            "LIVE",
            daemon="LIVE",
            scanner="STALE",
            ohlc_health="STALE",
            setup_engine="MARKER_ONLY",
            master_brain="STALE",
        ),
        {"canonical_open_trade_count": 0},
    )

    assert payload["restart_allowed"] is False
    assert payload["dashboard_overall_status"] == "RESTART_BLOCKED"
    assert "scanner stale" in payload["restart_blockers"]
    assert "OHLC stale" in payload["restart_blockers"]
    assert "setup stale/marker-only" in payload["restart_blockers"]
    assert "master brain stale/guard pending" in payload["restart_blockers"]
