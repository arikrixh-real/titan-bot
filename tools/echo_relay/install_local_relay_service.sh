#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="echo-relay.service"
SERVICE_PATH="${SERVICE_PATH:-/etc/systemd/system/${SERVICE_NAME}}"
ENV_PATH="${ENV_PATH:-/etc/titan/echo-relay.env}"
TITAN_DIR="${TITAN_DIR:-/opt/TITAN}"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python}"
RUN_USER="${RUN_USER:-titan}"
RUN_GROUP="${RUN_GROUP:-titan}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "FAIL: run as root to install the systemd unit"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_EXAMPLE="${SCRIPT_DIR}/relay_env.example"

if [[ ! -f "${ENV_EXAMPLE}" ]]; then
  echo "FAIL: missing ${ENV_EXAMPLE}"
  exit 1
fi

mkdir -p "$(dirname "${ENV_PATH}")"
if [[ ! -f "${ENV_PATH}" ]]; then
  install -m 0600 "${ENV_EXAMPLE}" "${ENV_PATH}"
  echo "Created ${ENV_PATH}; replace placeholder keys before starting ${SERVICE_NAME}."
else
  chmod 0600 "${ENV_PATH}"
  echo "Preserved existing ${ENV_PATH}."
fi

cat > "${SERVICE_PATH}" <<EOF
[Unit]
Description=ECHO local relay API (127.0.0.1 only)
After=network.target

[Service]
Type=simple
WorkingDirectory=${TITAN_DIR}
EnvironmentFile=${ENV_PATH}
ExecStart=${PYTHON_BIN} -m uvicorn titan_echo.echo_relay_api:app --host 127.0.0.1 --port 8766 --workers 1
Restart=no
User=${RUN_USER}
Group=${RUN_GROUP}
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

chmod 0644 "${SERVICE_PATH}"
systemctl daemon-reload

echo "Installed ${SERVICE_PATH}"
echo "Relay bind is 127.0.0.1:8766 only."
echo "ECHO_RELAY_ENABLED is read only from ${ENV_PATH}."
echo "This script did not start, enable, expose, firewall, tunnel, deploy, or restart TITAN."
