# HFT Mode Architecture

This batch creates an isolated package boundary:

- `hft_config.py` owns locked configuration constants.
- `hft_safety_gate.py` owns hard-deny integration checks.
- `hft_runtime_state.py` owns JSON reads and writes under `data/hft_mode/`.
- `data/hft_mode/*.json` stores sealed simulation state only.

No Classic runtime module imports HFT mode. HFT mode does not import broker,
Telegram, Master Brain, daemon, dashboard, scanner, setup engine, journal,
outcome tracker, or evolution modules.

Allowed behavior:

- Read HFT configuration.
- Read and write HFT JSON state under `data/hft_mode/`.
- Report that all external integrations are disabled.

Forbidden behavior:

- Live trade placement.
- Broker calls.
- Telegram messages.
- Classic journal writes.
- TITAN memory writes.
- TITAN evolution writes.
- Master Brain access.
- Daemon or active runtime connection.
