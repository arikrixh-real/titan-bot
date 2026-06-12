# TITAN Runtime Supervisor

The supervisor runs the backend runtime writers on fixed intervals and keeps the dashboard reading real JSON outputs. The dashboard remains read-only; do not patch dashboard values to hide stale backend files.

## Stop Old Nohup Loops

Run this before starting the supervisor:

```bash
pgrep -af 'runtime_continuous_core.py|runtime_paper_engine.py|runtime_dashboard_sync.py|runtime_truth.py|runtime_snapshot_logger.py'
pgrep -af 'nohup.*runtime_(continuous_core|paper_engine|dashboard_sync|truth|snapshot_logger).py'
pkill -f 'runtime_continuous_core.py'
pkill -f 'runtime_paper_engine.py'
pkill -f 'runtime_dashboard_sync.py'
pkill -f 'runtime_truth.py'
pkill -f 'runtime_snapshot_logger.py'
```

Do not stop `titan_runtime_supervisor.py` with these commands unless you intend to shut down the single supervisor.

## Start Supervisor

Manual foreground run:

```bash
cd /opt/TITAN
python3 titan_runtime_supervisor.py
```

Systemd template install:

```bash
sudo cp deploy/titan-runtime-supervisor.service /etc/systemd/system/titan-runtime-supervisor.service
sudo systemctl daemon-reload
sudo systemctl enable --now titan-runtime-supervisor.service
```

## Check Logs

```bash
tail -f logs/titan_runtime_supervisor.log
cat data/runtime/titan_runtime_supervisor_status.json
systemctl status titan-runtime-supervisor.service
```

## Verify Dashboard Freshness

```bash
python3 runtime_truth.py
python3 runtime_snapshot_logger.py
cat data/runtime/active_runtime_snapshot.json
cat data/runtime/titan_runtime_supervisor_status.json
```

Expected safety fields remain:

```json
{
  "paper_only": true,
  "broker_orders": false,
  "live_order_placement": false
}
```
