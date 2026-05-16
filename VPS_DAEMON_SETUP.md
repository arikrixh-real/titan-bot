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

Currently only safe registered tasks execute:

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
ExecStart=/home/ubuntu/TITAN/.venv/bin/python titan_daemon.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
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
