import json
from datetime import datetime, timedelta

import runtime_truth
from utils.market_hours import IST


NOW = datetime(2026, 6, 7, 12, 0, tzinfo=IST)


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_controlled_worker_proof_overrides_stale_historical_workers(tmp_path, monkeypatch):
    worker_health = tmp_path / "worker_health.json"
    fresh = NOW.isoformat()
    old = (NOW - timedelta(days=10)).isoformat()
    _write_json(
        worker_health,
        {
            "heartbeat": {"status": "OK", "proof_mode": True, "last_finished_at": fresh},
            "runtime_status": {"status": "OK", "proof_mode": True, "last_finished_at": fresh},
            "dashboard_sync": {"status": "OK", "proof_mode": True, "last_finished_at": fresh},
            "legacy_full_worker": {"status": "OK", "last_finished_at": old},
        },
    )
    monkeypatch.setattr(runtime_truth, "WORKER_HEALTH_PATH", worker_health)

    result = runtime_truth.classify_workers(now=NOW)

    assert result["status"] == "LIVE"
    assert result["reason"] == "fresh_controlled_worker_proof_tasks"
    assert result["restart_blocker"] is False
    assert set(result["fresh_proof_workers"]) == {"heartbeat", "runtime_status", "dashboard_sync"}
