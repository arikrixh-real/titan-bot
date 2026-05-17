# TITAN VPS Daemon Setup

## 1. Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv git
```

## 2. Clone TITAN repository

```bash
git clone <repository-url>
cd TITAN
```

## 3. Create virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 4. Install requirements

```bash
pip install -r requirements.txt
```

## 5. Test daemon manually

```bash
python titan_daemon.py
```

The master brain runtime wrapper defaults to safe read-only mode unless explicitly
enabled with an environment variable.

Supported master brain modes:

- `READ_ONLY` - default. Reads scanner status and writes
  `data/runtime/master_brain_status.json`; does not call the real master
  controller.
- `HEALTH` - calls the real master controller with `health_check=True`.
- `REAL` - calls `titan_master_brain.master_controller.run_master_brain()`.
  Off-market research mode remains allowed. During market alert hours, the real
  controller owns and enforces the global runtime lock.

To test read-only mode:

```bash
TITAN_RUNTIME_MASTER_BRAIN_MODE=READ_ONLY python runtime_master_brain.py
```

To test health mode:

```bash
TITAN_RUNTIME_MASTER_BRAIN_MODE=HEALTH python runtime_master_brain.py
```

To test real mode:

```bash
TITAN_RUNTIME_MASTER_BRAIN_MODE=REAL python runtime_master_brain.py
```

Currently safe registered tasks execute through:

- heartbeat
- runtime_status

Future engines should be added through:

```text
runtime_engine_registry.py
```

## 6. Create systemd service

Create a systemd service named `titan-daemon` using this service definition:

```ini
[Unit]
Description=TITAN Daemon
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/ubuntu/TITAN
Environment=TITAN_RUNTIME_MASTER_BRAIN_MODE=READ_ONLY
ExecStart=/home/ubuntu/TITAN/.venv/bin/python titan_daemon.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

To enable the real master brain on VPS, change the service environment line to:

```ini
Environment=TITAN_RUNTIME_MASTER_BRAIN_MODE=REAL
```

Then reload and restart the service:

```bash
sudo systemctl daemon-reload
sudo systemctl restart titan-daemon
```

## 7. Enable service

```bash
sudo systemctl daemon-reload
sudo systemctl enable titan-daemon
sudo systemctl start titan-daemon
```

## 8. Check service status

```bash
sudo systemctl status titan-daemon
```

## 9. View live logs

```bash
journalctl -u titan-daemon -f
```

## 10. Restart service

```bash
sudo systemctl restart titan-daemon
```

## 11. Stop service

```bash
sudo systemctl stop titan-daemon
```

## 12. Runtime files generated

The daemon generates runtime files under `data/runtime/`:

- `data/runtime/titan_heartbeat.json`
- `data/runtime/titan_runtime_status.json`
- `data/runtime/daemon_health.json`
- `data/runtime/dispatch_log.jsonl`
- `data/runtime/daemon_errors.jsonl`
