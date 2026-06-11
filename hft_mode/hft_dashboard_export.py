"""Read-only export adapter for HFT JSON visibility."""

from __future__ import annotations

from hft_mode.hft_runtime_state import read_hft_json

EXPORT_FILES = {
    "health": "hft_health.json",
    "stats": "hft_stats.json",
    "active_trades": "hft_active_trades.json",
    "closed_summary": "hft_closed_summary.json",
    "outcomes": "hft_outcomes.json",
    "daily_pnl": "hft_daily_pnl.json",
    "rejected_count": "hft_rejected_count.json",
}


def read_hft_dashboard_export() -> dict[str, object]:
    export: dict[str, object] = {}
    for key, file_name in EXPORT_FILES.items():
        try:
            export[key] = read_hft_json(file_name)
        except FileNotFoundError:
            export[key] = {}
    export["connected_to_titan_runtime"] = False
    export["read_only"] = True
    return export
