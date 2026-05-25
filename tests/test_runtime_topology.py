import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import runtime_dependency_graph
import runtime_topology
from utils.market_hours import IST


class RuntimeTopologyTests(unittest.TestCase):
    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_runtime_hierarchy_deterministic(self):
        self.assertEqual(
            runtime_topology.RUNTIME_PRIORITY_ORDER,
            [
                "runtime_health",
                "market_data_health",
                "scanner_status",
                "master_brain_status",
                "dashboard_sync_status",
                "roadmap_sidecars",
            ],
        )

    def test_duplicate_source_detection_works(self):
        sources = {
            "runtime_health": {"present": True},
            "daemon_health": {"present": True},
            "heartbeat": {"present": True},
            "market_data_health": {"present": True},
            "scanner_status": {"present": True},
        }

        duplicates = runtime_topology._duplicate_source_detection(sources)

        groups = {item["group"] for item in duplicates}
        self.assertIn("runtime_owner", groups)
        self.assertIn("market_data", groups)

    def test_stale_runtime_writer_detection_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fresh = datetime(2026, 5, 25, 10, 0, tzinfo=IST)
            old = fresh - timedelta(hours=2)
            runtime_health = root / "runtime_health.json"
            market = root / "market.json"
            scanner = root / "scanner.json"
            heartbeat = root / "heartbeat.json"
            daemon = root / "daemon.json"
            lock = root / "lock.json"
            for path, timestamp in (
                (runtime_health, fresh),
                (market, fresh),
                (scanner, old),
                (heartbeat, old),
                (daemon, old),
                (lock, old),
            ):
                self._write_json(path, {"status": "OK", "timestamp_ist": timestamp.isoformat()})
            sources = {
                "runtime_health": runtime_health,
                "market_data_health": market,
                "scanner_status": scanner,
                "heartbeat": heartbeat,
                "daemon_health": daemon,
                "daemon_lock": lock,
            }
            records = {
                name: runtime_topology._source_record(name, path, fresh)
                for name, path in sources.items()
            }

        stale = [name for name, record in records.items() if record["stale"]]
        self.assertIn("scanner_status", stale)
        self.assertIn("heartbeat", stale)
        self.assertNotIn("runtime_health", stale)

    def test_disconnected_engine_detection_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            now = datetime(2026, 5, 25, 10, 0, tzinfo=IST)
            scanner = root / "scanner.json"
            execution = root / "execution.json"
            self._write_json(scanner, {"status": "OK", "timestamp_ist": now.isoformat()})
            specs = {
                "scanner": {
                    "path": scanner,
                    "mode": "live_signal_input",
                    "upstream": [],
                    "downstream": ["execution_engine"],
                },
                "execution_engine": {
                    "path": execution,
                    "mode": "execution_visibility_only",
                    "upstream": ["scanner"],
                    "downstream": [],
                },
            }
            graph_path = root / "graph.json"
            with patch.object(runtime_dependency_graph, "CORE_NODES", specs), patch.object(
                runtime_dependency_graph, "_discover_memory_nodes", return_value={}
            ), patch.object(runtime_dependency_graph, "_discover_roadmap_phase_nodes", return_value={}):
                graph = runtime_dependency_graph.build_runtime_dependency_graph(path=graph_path, now=now)

            self.assertIn("execution_engine", graph["disconnected_engines"])
            self.assertEqual(graph["dependency_status"], "WARNING")
            self.assertTrue(graph_path.exists())

    def test_runtime_topology_generated_correctly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            now = datetime(2026, 5, 25, 10, 0, tzinfo=IST)
            paths = {
                "runtime_health": root / "runtime_health.json",
                "market_data_health": root / "market.json",
                "scanner_status": root / "scanner.json",
                "master_brain_status": root / "master.json",
                "dashboard_sync_status": root / "dashboard.json",
                "runtime_status": root / "runtime_status.json",
                "daemon_health": root / "daemon.json",
                "heartbeat": root / "heartbeat.json",
                "daemon_lock": root / "lock.json",
            }
            for name, path in paths.items():
                self._write_json(path, {"status": "OK", "timestamp_ist": now.isoformat(), "mode": "MARKET_MODE"})
            self._write_json(paths["runtime_health"], {"overall_status": "PASS", "generated_at_ist": now.isoformat(), "runtime_owner": "runtime_health"})
            topology_path = root / "topology.json"
            audit_path = root / "audit.json"
            fake_graph = {
                "dependency_status": "PASS",
                "dependency_integrity_score": 100.0,
                "nodes": {"scanner": {"connected": True, "fresh": True, "status": "OK", "mode": "live_signal_input"}},
                "connected_engines": ["scanner"],
                "disconnected_engines": [],
                "stale_engines": [],
            }
            with patch.object(runtime_topology, "RUNTIME_SOURCES", paths), patch.object(
                runtime_topology, "TOPOLOGY_PATH", topology_path
            ), patch.object(runtime_topology, "VISIBILITY_AUDIT_PATH", audit_path), patch.object(
                runtime_topology, "build_runtime_dependency_graph", return_value=fake_graph
            ), patch.object(runtime_topology, "_roadmap_sidecar_sources", return_value={}), patch.object(
                runtime_topology, "_memory_visibility", return_value={}
            ):
                topology = runtime_topology.build_runtime_topology(path=topology_path, now=now)

            self.assertEqual(topology["runtime_priority_order"][0], "runtime_health")
            self.assertEqual(topology["topology_health"], "PASS")
            self.assertTrue(topology_path.exists())
            self.assertTrue(audit_path.exists())
            self.assertTrue(topology["safety_flags"]["advisory_only"])
            self.assertFalse(topology["safety_flags"]["affects_execution"])
            self.assertFalse(topology["safety_flags"]["affects_live_ranking"])

    def test_no_live_mutation_enabled(self):
        self.assertTrue(runtime_dependency_graph.SAFETY_FLAGS["advisory_only"])
        self.assertFalse(runtime_dependency_graph.SAFETY_FLAGS["affects_execution"])
        self.assertFalse(runtime_dependency_graph.SAFETY_FLAGS["affects_live_ranking"])
        self.assertFalse(runtime_dependency_graph.SAFETY_FLAGS["broker_mutation"])
        self.assertFalse(runtime_dependency_graph.SAFETY_FLAGS["telegram_mutation"])
        self.assertFalse(runtime_dependency_graph.SAFETY_FLAGS["supabase_mutation"])
        self.assertFalse(runtime_dependency_graph.SAFETY_FLAGS["live_order_behavior"])
        self.assertEqual(runtime_dependency_graph.SAFETY_FLAGS["recommended_live_weight"], 0.0)
        self.assertEqual(runtime_dependency_graph.SAFETY_FLAGS["rank_adjustment"], 0.0)


if __name__ == "__main__":
    unittest.main()
