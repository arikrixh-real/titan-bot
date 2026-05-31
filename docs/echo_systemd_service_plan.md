# ECHO systemd service plan

Plan only. Do not install until explicitly approved.

## Service file: /etc/systemd/system/echo-api.service

```ini
[Unit]
Description=ECHO read-only localhost API
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/titan-bot
EnvironmentFile=/home/ubuntu/titan-bot/.config/echo-api.env
ExecStart=/home/ubuntu/titan-bot/.venv/bin/python -m uvicorn titan_echo.echo_api:app --host 127.0.0.1 --port 8765
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=false

[Install]
WantedBy=multi-user.target
```

## Env file

Path: `/home/ubuntu/titan-bot/.config/echo-api.env`

```bash
# Create this file on the VPS only. Do not commit it.
# Replace the placeholder with a real strong secret on the VPS.
ECHO_API_KEY=replace-with-vps-only-secret
```

## Verification commands

- `systemctl cat echo-api.service`
- `systemctl status echo-api.service --no-pager`
- `ss -ltnp | grep 8765`
- `curl -s http://127.0.0.1:8765/health`
- `curl -s -H 'X-ECHO-API-KEY: <redacted>' http://127.0.0.1:8765/status`
- `curl -s -H 'X-ECHO-API-KEY: <redacted>' 'http://127.0.0.1:8765/query?intent=what_next'`

## Rollback commands

- `sudo systemctl stop echo-api.service`
- `sudo systemctl disable echo-api.service`
- `sudo rm /etc/systemd/system/echo-api.service`
- `sudo systemctl daemon-reload`
- `ss -ltnp | grep 8765 || true`

## Safety

- Binds only to `127.0.0.1:8765`.
- Requires `ECHO_API_KEY` from the env file.
- Does not start or restart TITAN.
- Does not expose a public port.
- Does not modify scanner, broker, risk, execution, Master Brain, Unified Brain, or runtime workers.
