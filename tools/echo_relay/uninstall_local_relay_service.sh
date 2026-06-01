#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="echo-relay.service"
SERVICE_PATH="${SERVICE_PATH:-/etc/systemd/system/${SERVICE_NAME}}"
ENV_PATH="${ENV_PATH:-/etc/titan/echo-relay.env}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "FAIL: run as root to uninstall the systemd unit"
  exit 1
fi

if systemctl list-unit-files "${SERVICE_NAME}" >/dev/null 2>&1; then
  systemctl disable --now "${SERVICE_NAME}" >/dev/null 2>&1 || true
fi

if [[ -f "${SERVICE_PATH}" ]]; then
  rm -f "${SERVICE_PATH}"
fi

systemctl daemon-reload
systemctl reset-failed "${SERVICE_NAME}" >/dev/null 2>&1 || true

echo "Removed ${SERVICE_PATH}"
if [[ -f "${ENV_PATH}" ]]; then
  echo "Preserved ${ENV_PATH}; remove it manually if the relay key should be destroyed."
fi
