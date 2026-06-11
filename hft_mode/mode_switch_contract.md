# HFT Mode Switch Contract

There is no active mode switch in this batch.

The current contract is a sealed default:

- HFT remains OFF.
- HFT remains `SIMULATION_ONLY`.
- Dashboard controls are not connected.
- Runtime scheduler entries are not added.
- Daemon workers are not started.
- Classic runtime remains authoritative and unchanged.

Any future switch must first change the explicit constants in `hft_config.py`
and add tests proving that broker, Telegram, Classic journal, memory, evolution,
Master Brain, and daemon access remain controlled by safety gates.
