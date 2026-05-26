import csv
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import trade_lifecycle_health
from utils.market_hours import IST


class TradeLifecycleReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "runtime"
        self.journal = self.root / "journals"
        self.runtime.mkdir(parents=True)
        self.journal.mkdir(parents=True)
        self.now = datetime(2026, 5, 26, 14, 0, tzinfo=IST)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_csv(self, path, rows):
        fields = [
            "trade_id",
            "opened_at",
            "symbol",
            "side",
            "entry",
            "sl",
            "target",
            "status",
            "outcome",
            "result",
            "last_checked_at",
            "paper_trade_id",
            "is_paper_trade",
            "alert_sent",
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fields})
        return path

    def test_reconciliation_separates_active_learning_stale_eod_and_closed(self):
        active = self._write_csv(
            self.journal / "active_trades.csv",
            [
                {
                    "trade_id": "LIVE1",
                    "opened_at": self.now.isoformat(),
                    "symbol": "ABC",
                    "side": "LONG",
                    "entry": "100",
                    "sl": "95",
                    "target": "110",
                    "status": "OPEN",
                    "last_checked_at": self.now.isoformat(),
                    "alert_sent": "YES",
                },
                {
                    "trade_id": "PAPER1",
                    "opened_at": self.now.isoformat(),
                    "symbol": "DEF",
                    "side": "LONG",
                    "entry": "100",
                    "sl": "95",
                    "target": "110",
                    "status": "OPEN",
                    "last_checked_at": self.now.isoformat(),
                    "is_paper_trade": "true",
                    "alert_sent": "NO",
                },
                {
                    "trade_id": "OLD1",
                    "opened_at": "2026-05-25T14:00:00+05:30",
                    "symbol": "GHI",
                    "side": "LONG",
                    "entry": "100",
                    "sl": "95",
                    "target": "110",
                    "status": "OPEN",
                    "last_checked_at": "2026-05-25T14:10:00+05:30",
                    "alert_sent": "YES",
                },
            ],
        )
        outcomes = self._write_csv(
            self.journal / "trade_outcomes.csv",
            [{"trade_id": "C1", "symbol": "XYZ", "status": "CLOSED", "outcome": "TP", "result": "WIN"}],
        )

        with patch.object(trade_lifecycle_health, "LEGACY_OPEN_TRADE_PATHS", []):
            status = trade_lifecycle_health.build_trade_lifecycle_health(
                now=self.now,
                active_trades_path=active,
                outcomes_path=outcomes,
                output_path=self.runtime / "trade_lifecycle_health.json",
            )

        reconciliation = json.loads((self.runtime / "trade_lifecycle_reconciliation.json").read_text(encoding="utf-8"))
        self.assertEqual(status["active_live_trades_count"], 1)
        self.assertEqual(status["learning_open_trades_count"], 1)
        self.assertEqual(reconciliation["active_live_trades"]["count"], 1)
        self.assertEqual(reconciliation["learning_open_trades"]["count"], 1)
        self.assertEqual(reconciliation["eod_unresolved_trades"]["count"], 1)
        self.assertEqual(reconciliation["closed_tp_sl_trades"]["count"], 1)
        self.assertTrue(reconciliation["manual_reconciliation_required"]["required"])


if __name__ == "__main__":
    unittest.main()
