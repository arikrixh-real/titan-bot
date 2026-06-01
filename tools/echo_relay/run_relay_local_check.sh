#!/usr/bin/env bash
set -euo pipefail

SERVICE_FILE="tools/echo_relay/echo-relay.service.example"

python -m py_compile \
  titan_echo/echo_relay_api.py \
  titan_echo/echo_relay_auth.py \
  titan_echo/echo_relay_config.py \
  titan_echo/echo_relay_check.py

grep -q -- "--host 127.0.0.1" "$SERVICE_FILE"
grep -q -- "--port 8766" "$SERVICE_FILE"
grep -q "ECHO_RELAY_ENABLED=false" "$SERVICE_FILE"
grep -q "ECHO_INTERNAL_BASE_URL=http://127.0.0.1:8765" "$SERVICE_FILE"

PUBLIC_BIND_PATTERN="--host 0[.]0[.]0[.]0|--host [][:][:]|--host [*]"
if grep -Eq -- "$PUBLIC_BIND_PATTERN" "$SERVICE_FILE"; then
  echo "FAIL: service file contains a public bind"
  exit 1
fi

python - <<'PY'
from titan_echo.echo_relay_api import relay_health
payload = relay_health()
print(payload["status"])
if payload["status"] != "RELAY_DISABLED":
    raise SystemExit(1)
PY

echo "PASS: relay service plan is localhost-only and disabled by default"
