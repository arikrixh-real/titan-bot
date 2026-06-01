# Cloudflare Tunnel Checklist

This is a manual checklist only. This repository package does not install Cloudflare, expose ports, edit firewall rules, start services, or deploy TITAN.

Prerequisites:
- Relay service package has passed `tools/echo_relay/relay_service_check.sh`.
- The relay binds to `127.0.0.1:8766` only.
- `/etc/titan/echo-relay.env` exists locally and contains real local keys.
- `ECHO_RELAY_ENABLED=true` appears only in the env file.
- No public firewall rule or open inbound port is required.

Tunnel constraints:
- Tunnel origin must target `http://127.0.0.1:8766`.
- Public hostname must be dedicated to the relay.
- TLS must terminate at Cloudflare.
- No wildcard route should point to the relay.
- No path outside `/relay/*` should be forwarded.
- Cloudflare Access or equivalent protection should be enabled before Custom GPT testing.

Manual verification before Custom GPT use:
- Confirm `curl http://127.0.0.1:8766/relay/health` never exposes secrets.
- Confirm requests without `X-ECHO-RELAY-KEY` are rejected when the relay is enabled.
- Confirm the public hostname reaches only the relay health endpoint with the correct key.
- Confirm blocked paths remain unavailable through the tunnel.

Stop condition:
- If any non-relay path is reachable, any secret appears in a response, or any blocked action path responds successfully, remove the public route and investigate locally.
