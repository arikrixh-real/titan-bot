import csv
from pathlib import Path

import data.active_trade_store as active_store


def _write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row.keys()} | {"symbol", "side", "status"})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _patch_active_store_paths(monkeypatch, tmp_path):
    canonical = tmp_path / "data" / "journals" / "active_trades.csv"
    legacy_old = tmp_path / "data" / "journals" / "active_trades_old.csv"
    legacy_backup = tmp_path / "data" / "journals" / "active_trades.backup.csv"
    legacy_journal = tmp_path / "data" / "trade_journal.csv"
    runtime = tmp_path / "data" / "runtime"
    monkeypatch.setattr(active_store, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(active_store, "ACTIVE_TRADES_CSV", canonical)
    monkeypatch.setattr(active_store, "RUNTIME_DIR", runtime)
    monkeypatch.setattr(active_store, "DEBUG_PATH", runtime / "active_trade_store_debug.json")
    monkeypatch.setattr(active_store, "JOURNAL_TRUTH_UNIFICATION_PATH", runtime / "journal_truth_unification.json")
    monkeypatch.setattr(
        active_store,
        "LEGACY_ACTIVE_TRADE_FILES",
        [legacy_old, legacy_backup, legacy_journal],
    )
    return canonical, legacy_old, legacy_backup, legacy_journal


def test_canonical_active_trades_csv_is_only_current_open_source(monkeypatch, tmp_path):
    canonical, legacy_old, legacy_backup, legacy_journal = _patch_active_store_paths(monkeypatch, tmp_path)
    _write_csv(canonical, [])
    _write_csv(legacy_old, [{"symbol": "OLD", "side": "LONG", "status": "OPEN"}])
    _write_csv(legacy_backup, [{"symbol": "BAK", "side": "LONG", "status": "OPEN"}])
    _write_csv(legacy_journal, [{"symbol": "ROOT", "side": "LONG", "status": "OPEN"}])

    assert active_store.load_canonical_open_trades() == []
    assert active_store.canonical_open_trade_count() == 0


def test_legacy_open_rows_are_reported_but_quarantined(monkeypatch, tmp_path):
    canonical, legacy_old, legacy_backup, legacy_journal = _patch_active_store_paths(monkeypatch, tmp_path)
    _write_csv(canonical, [{"symbol": "CANON", "side": "LONG", "status": "CLOSED"}])
    _write_csv(legacy_old, [{"symbol": "OLD", "side": "LONG", "status": "OPEN"}])
    _write_csv(legacy_backup, [{"symbol": "BAK", "side": "SHORT", "status": "ACTIVE"}])
    _write_csv(legacy_journal, [{"symbol": "ROOT", "side": "LONG", "status": "LIVE"}])

    payload = active_store.write_journal_truth_unification(
        readers_checked=["dashboard.py", "journal/outcome_tracker.py"],
        readers_patched=["dashboard.py", "journal/outcome_tracker.py"],
        unsafe_fallbacks_removed=["legacy active trade CSV fallbacks"],
    )

    assert payload["canonical_open_trade_count"] == 0
    assert payload["legacy_quarantined_file_count"] == 3
    assert payload["legacy_open_rows_warning"] is True
    assert set(payload["legacy_open_rows_by_file"].values()) == {1}
    assert payload["restart_blocker"] is False


def test_dashboard_does_not_count_legacy_open_rows_as_active_trades():
    source = Path("dashboard.py").read_text(encoding="utf-8")

    assert "from data.active_trade_store import load_canonical_open_trades" in source
    assert "return len([row for row in load_canonical_open_trades()" in source
    assert "open_outcome_trades = live_trades_count" in source
    assert '"journal/active_trades.csv"' not in source


def test_outcome_tracker_reads_canonical_active_store_only():
    source = Path("journal/outcome_tracker.py").read_text(encoding="utf-8")

    assert "load_canonical_open_trades" in source
    assert "load_open_trades" not in source


def test_master_brain_current_trade_context_ignores_legacy_files():
    source = Path("titan_master_brain/final_decision_engine.py").read_text(encoding="utf-8")

    assert "load_canonical_open_trades" in source
    assert 'Path("active_trades.csv")' not in source
    assert '"trade_results", "journal_open_trades"' not in source
    assert "return _supabase_open_trades()" not in source
