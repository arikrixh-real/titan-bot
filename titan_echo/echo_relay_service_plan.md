# ECHO Relay Localhost Service Plan

Status: design only. Do not install or start automatically.

## Purpose

Prepare a localhost-only relay process for a future ChatGPT Custom GPT Action path:

ChatGPT Custom GPT Action -> HTTPS secure relay -> VPS localhost ECHO API -> TITAN evidence

This phase does not expose ECHO publicly and does not enable the relay.

## Required Safety Defaults

- Bind address: `127.0.0.1`
- Relay port: `8766`
- Relay enabled: `ECHO_RELAY_ENABLED=false`
- ECHO internal base URL: `http://127.0.0.1:8765`
- Relay auth header: `X-ECHO-RELAY-KEY`
- Raw ECHO public exposure: disabled
- External API calls: disabled
- Codex execution: disabled
- TITAN runtime mutation: disabled

## Manual Commands For Later

Review static service file:

```bash
grep -n "127.0.0.1\\|8766\\|ECHO_RELAY_ENABLED=false" tools/echo_relay/echo-relay.service.example
```

Run local static check:

```bash
bash tools/echo_relay/run_relay_local_check.sh
```

Compile relay modules:

```bash
python -m py_compile titan_echo/echo_relay_api.py titan_echo/echo_relay_auth.py titan_echo/echo_relay_config.py titan_echo/echo_relay_check.py
```

Install later only after separate approval:

```bash
sudo cp tools/echo_relay/echo-relay.service.example /etc/systemd/system/echo-relay.service
sudo systemctl daemon-reload
sudo systemctl enable echo-relay.service
sudo systemctl start echo-relay.service
```

Do not run the install/start commands in this phase.

## Expected Disabled Output

When imported or queried with `ECHO_RELAY_ENABLED=false`, relay handlers return:

```json
{
  "status": "RELAY_DISABLED",
  "enabled": false,
  "public_exposure_allowed": false
}
```

## Notes

The relay skeleton forwards only allowlisted read-only ECHO evidence endpoints when enabled later. It blocks `/mission/*`, `/approval/*`, `/execution/*`, and anything outside the allowlist.
