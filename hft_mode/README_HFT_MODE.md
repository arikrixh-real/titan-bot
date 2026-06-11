# HFT Mode Foundation

HFT mode is sealed off from TITAN Classic runtime in this batch.

Current state:

- `HFT_ENABLED = False`
- `MODE = "SIMULATION_ONLY"`
- No broker access
- No Telegram access
- No Classic journal writes
- No TITAN memory writes
- No TITAN evolution writes
- No Master Brain access
- No daemon or runtime connection

HFT data files live only under `data/hft_mode/`. The helper in
`hft_runtime_state.py` rejects absolute paths, parent-directory traversal, and
subdirectory writes.

This foundation does not start a worker, expose a dashboard switch, or connect
HFT mode to any live TITAN runtime component.
