# End-to-End Test Checklist

This checklist is manual and local-first. Do not run it from ECHO automation.

Local package checks:
- Run `bash tools/echo_relay/relay_service_check.sh`.
- Confirm the output includes `OpenAPI safe path check PASS`.
- Confirm the output includes `PASS: relay package static checks passed`.

Local relay checks:
- Confirm the service unit uses `--host 127.0.0.1 --port 8766`.
- Confirm the service unit uses `EnvironmentFile=/etc/titan/echo-relay.env`.
- Confirm the env file contains `ECHO_RELAY_ENABLED=true`.
- Confirm relay requests require `X-ECHO-RELAY-KEY` when enabled.
- Confirm no wildcard/public bind appears in relay service files.

Custom GPT Action checks:
- Import `docs/chatgpt_bridge/custom_gpt_openapi.yaml`.
- Confirm the schema contains only:
  - `/relay/health`
  - `/relay/jarvis/ask`
  - `/relay/titan/status`
  - `/relay/chatgpt/integration/status`
  - `/relay/chatgpt/evidence/contract`
  - `/relay/chatgpt/evidence/catalog`
- Confirm the auth header is `X-ECHO-RELAY-KEY`.
- Confirm no mission, approval, shell, Codex, deploy, restart, rollback, broker, trading, or runtime worker action is available.

Response checks:
- Ask for relay health and verify no secrets are returned.
- Ask for TITAN status and verify the response is evidence-only.
- Ask Jarvis a status question and verify the answer cites evidence fields.
- Ask for a blocked action and verify the assistant refuses instead of calling an action.

Stop condition:
- Stop testing if a blocked action is reachable, auth is bypassed, public exposure is broader than the tunnel hostname, or any TITAN runtime behavior changes.
