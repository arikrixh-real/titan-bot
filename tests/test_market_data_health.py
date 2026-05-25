import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import market_data_health
from data import live_price
from utils.market_hours import IST


class MarketDataHealthTests(unittest.TestCase):
    def test_stale_ohlc_becomes_warning_or_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            old_ts = datetime(2026, 5, 22, 9, 15, tzinfo=IST)
            (cache_dir / "ABC.csv").write_text(
                "Datetime,Open,High,Low,Close,Volume\n"
                f"{old_ts.isoformat()},1,2,1,1.5,100\n",
                encoding="utf-8",
            )
            now = datetime(2026, 5, 25, 10, 0, tzinfo=IST)

            result = market_data_health.inspect_ohlc_freshness(now=now, cache_dir=cache_dir)

            self.assertEqual(result["status"], "WARNING")
            self.assertTrue(result["stale_ohlc_detected"])
            self.assertEqual(result["stale_symbol_count"], 1)

    def test_stale_cache_detected_correctly(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "live_price_cache.json"
            meta_path = Path(tmp) / "live_price_cache_meta.json"
            status_path = Path(tmp) / "live_price_status.json"
            runtime_meta_path = Path(tmp) / "runtime_live_price_cache_meta.json"
            now = datetime(2026, 5, 25, 10, 0, tzinfo=IST)
            old = now - timedelta(minutes=10)
            cache_path.write_text(json.dumps({"ABC": 100.0}), encoding="utf-8")
            meta_path.write_text(
                json.dumps({"ABC": {"price": 100.0, "updated_at_ist": old.isoformat(), "source": "UPSTOX"}}),
                encoding="utf-8",
            )

            with patch.object(market_data_health, "RUNTIME_LIVE_PRICE_CACHE_META_PATH", runtime_meta_path):
                result = market_data_health.inspect_live_price_cache(
                    now=now,
                    cache_path=cache_path,
                    meta_path=meta_path,
                    status_path=status_path,
                )

            self.assertTrue(result["cache_stale"])
            self.assertEqual(result["status"], "WARNING")

    def test_fresh_cache_becomes_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "live_price_cache.json"
            meta_path = Path(tmp) / "live_price_cache_meta.json"
            status_path = Path(tmp) / "live_price_status.json"
            runtime_meta_path = Path(tmp) / "runtime_live_price_cache_meta.json"
            now = datetime(2026, 5, 25, 10, 0, tzinfo=IST)
            fresh = now - timedelta(seconds=30)
            cache_path.write_text(json.dumps({"ABC": 100.0}), encoding="utf-8")
            meta_path.write_text(
                json.dumps({"ABC": {"price": 100.0, "updated_at_ist": fresh.isoformat(), "source": "UPSTOX"}}),
                encoding="utf-8",
            )
            status_path.write_text(
                json.dumps({"source": "UPSTOX", "status": "ACTIVE", "token_type_used": "ACCESS_TOKEN"}),
                encoding="utf-8",
            )

            with patch.object(market_data_health, "RUNTIME_LIVE_PRICE_CACHE_META_PATH", runtime_meta_path):
                result = market_data_health.inspect_live_price_cache(
                    now=now,
                    cache_path=cache_path,
                    meta_path=meta_path,
                    status_path=status_path,
                )

            self.assertFalse(result["cache_stale"])
            self.assertEqual(result["status"], "PASS")
            self.assertTrue(result["token_type_visible"])

    def test_fallback_state_visible(self):
        scanner = {
            "status": "WARNING",
            "scanner_status": "SCAN_ONLY_STALE_OHLC",
            "scanner_mode": "SCAN_ONLY_CACHED_50",
            "scan_only": True,
            "fallback_reason": "OHLC_STALE",
            "stale_ohlc_detected": True,
            "stale_symbol_count": 50,
        }
        ohlc = {
            "status": "WARNING",
            "stale_ohlc_detected": True,
            "stale_symbol_count": 50,
        }
        cache = {
            "status": "PASS",
            "cache_present": True,
            "meta_present": True,
            "cache_stale": False,
            "source": "UPSTOX",
            "runtime_visible": True,
            "token_type_visible": True,
            "token_type_used": "ACCESS_TOKEN",
        }
        with tempfile.TemporaryDirectory() as tmp:
            ohlc_status_path = Path(tmp) / "ohlc_freshness_status.json"
            with patch.object(market_data_health, "OHLC_FRESHNESS_STATUS_PATH", ohlc_status_path), patch.object(
                market_data_health, "inspect_scanner_freshness", return_value=scanner
            ), patch.object(market_data_health, "inspect_ohlc_freshness", return_value=ohlc), patch.object(
                market_data_health, "inspect_live_price_cache", return_value=cache
            ), patch.object(
                market_data_health,
                "_refresh_stale_ohlc_if_needed",
                return_value={"refresh_attempted": False, "refresh_success": False, "refresh_status": "NOT_REQUIRED"},
            ):
                result = market_data_health.build_market_data_health(now=datetime(2026, 5, 25, 10, 0, tzinfo=IST))

        self.assertTrue(result["fallback_active"])
        self.assertEqual(result["fallback_reason"], "OHLC_STALE")
        self.assertEqual(result["overall_status"], "FAIL")

    def test_cache_meta_generated_when_root_meta_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "live_price_cache.json"
            meta_path = Path(tmp) / "missing_meta.json"
            status_path = Path(tmp) / "live_price_status.json"
            runtime_meta_path = Path(tmp) / "runtime_live_price_cache_meta.json"
            now = datetime(2026, 5, 25, 10, 0, tzinfo=IST)
            cache_path.write_text(json.dumps({"ABC": 100.0}), encoding="utf-8")

            with patch.object(market_data_health, "RUNTIME_LIVE_PRICE_CACHE_META_PATH", runtime_meta_path):
                result = market_data_health.inspect_live_price_cache(
                    now=now,
                    cache_path=cache_path,
                    meta_path=meta_path,
                    status_path=status_path,
                )

            runtime_meta = json.loads(runtime_meta_path.read_text(encoding="utf-8"))
            self.assertTrue(result["meta_present"])
            self.assertFalse(result["root_meta_present"])
            self.assertEqual(runtime_meta["cache_source"], "cache_file_mtime")
            self.assertIn("ABC", runtime_meta["metadata"])

    def test_stale_ohlc_repaired_after_refresh_and_contradiction_removed(self):
        stale_ohlc = {
            "status": "WARNING",
            "symbols_checked": 2,
            "latest_candle_timestamp": "2026-05-20T15:15:00+05:30",
            "stale_ohlc_detected": True,
            "stale_symbol_count": 2,
        }
        fresh_ohlc = {
            "status": "PASS",
            "symbols_checked": 2,
            "latest_candle_timestamp": "2026-05-25T09:45:00+05:30",
            "stale_ohlc_detected": False,
            "stale_symbol_count": 0,
        }
        scanner = {
            "status": "PASS",
            "scanner_status": "FULL_RUNTIME_PIPELINE_COMPLETE",
            "scanner_mode": "SCAN_ONLY_CACHED_50",
            "scan_only": False,
            "fallback_reason": None,
            "stale_ohlc_detected": False,
            "stale_symbol_count": 0,
        }
        cache = {
            "status": "PASS",
            "cache_present": True,
            "meta_present": True,
            "cache_stale": False,
            "source": "UPSTOX",
            "cache_source": "live_price_cache_meta",
            "cache_age_seconds": 10,
            "cache_last_updated": "2026-05-25T09:59:50+05:30",
            "runtime_visible": True,
            "token_type_visible": True,
            "token_type_used": "ACCESS_TOKEN",
            "live_source_status": "ACTIVE",
        }
        with tempfile.TemporaryDirectory() as tmp:
            ohlc_status_path = Path(tmp) / "ohlc_freshness_status.json"
            with patch.object(market_data_health, "OHLC_FRESHNESS_STATUS_PATH", ohlc_status_path), patch.object(
                market_data_health, "inspect_scanner_freshness", return_value=scanner
            ), patch.object(
                market_data_health, "inspect_ohlc_freshness", side_effect=[stale_ohlc, fresh_ohlc]
            ), patch.object(
                market_data_health,
                "_refresh_stale_ohlc_if_needed",
                return_value={"refresh_attempted": True, "refresh_success": True, "refresh_status": "COMPLETED"},
            ), patch.object(
                market_data_health, "inspect_live_price_cache", return_value=cache
            ):
                result = market_data_health.build_market_data_health(now=datetime(2026, 5, 25, 10, 0, tzinfo=IST))

            ohlc_status = json.loads(ohlc_status_path.read_text(encoding="utf-8"))

        self.assertEqual(result["overall_status"], "PASS")
        self.assertEqual(result["stale_symbol_count"], 0)
        self.assertEqual(result["fresh_symbol_count"], 2)
        self.assertEqual(result["latest_market_candle"], "2026-05-25T09:45:00+05:30")
        self.assertEqual(result["contradiction_flags"], [])
        self.assertTrue(ohlc_status["refresh_attempted"])
        self.assertTrue(ohlc_status["refresh_success"])

    def test_no_secrets_exposed_in_live_price_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            status_file = Path(tmp) / "live_price_status.json"
            with patch.object(live_price, "STATUS_FILE", str(status_file)):
                live_price._write_status(
                    "ABC",
                    "TOKEN_INVALID",
                    "Upstox token invalid/expired; using cache if available",
                    price=100.0,
                    source="CACHE",
                    token_type_used="ACCESS_TOKEN",
                )
            payload_text = status_file.read_text(encoding="utf-8")
            payload = json.loads(payload_text)

        self.assertIn("token_type_used", payload)
        self.assertNotIn("secret-token-value", payload_text)
        self.assertNotIn("Bearer", payload_text)
        self.assertNotIn("Authorization", payload_text)

    def test_no_live_ranking_mutation_enabled(self):
        self.assertTrue(market_data_health.SAFETY_FLAGS["advisory_only"])
        self.assertFalse(market_data_health.SAFETY_FLAGS["affects_live_ranking"])
        self.assertFalse(market_data_health.SAFETY_FLAGS["affects_execution"])
        self.assertFalse(market_data_health.SAFETY_FLAGS["broker_mutation"])
        self.assertFalse(market_data_health.SAFETY_FLAGS["telegram_mutation"])
        self.assertFalse(market_data_health.SAFETY_FLAGS["supabase_mutation"])
        self.assertFalse(market_data_health.SAFETY_FLAGS["live_order_behavior"])
        self.assertEqual(market_data_health.SAFETY_FLAGS["recommended_live_weight"], 0.0)
        self.assertEqual(market_data_health.SAFETY_FLAGS["rank_adjustment"], 0.0)


if __name__ == "__main__":
    unittest.main()
