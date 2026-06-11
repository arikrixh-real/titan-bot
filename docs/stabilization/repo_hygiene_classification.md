# TITAN Repo Hygiene Classification

This classifies files by ownership so generated runtime state does not mix with source. Runtime values must remain real only: unavailable data is represented as `0`, `null`, `UNKNOWN`, `STALE`, or `DEGRADED` with a blocker reason.

## SOURCE_TO_KEEP

- Python source under the repo root, `engines/`, `hft_mode/`, `intelligence/`, `journal/`, `runtime_*.py`, `scanners/`, `titan_alpha_math/`, `titan_alpha_data/`, `titan_echo/`, `tools/`, `unified_brain/`, and `utils/`.
- Tests under `tests/`.
- Source configuration and docs under `.github/`, `.devcontainer/`, `config/`, `docs/`, `reports/`, and `*.md`.
- `data/universe_selectors.py`, `data/live_price.py`, `data/price_cache.py`, `data/upstox_ohlc.py`, `data/upstox_auth.py`, and `data/upstox_broker_auth.py` when they contain code, not captured runtime payloads.

## GENERATED_RUNTIME_IGNORE

- `data/runtime/`
- `data/classic_mode/`
- `data/hft_mode/`
- `data/journals/`
- `data/paper_trading/`
- `data/live_price_cache.json`
- `data/live_price_cache_meta.json`
- `data/live_price_status.json`
- `data/common_market_snapshot.json`
- `data/universe_master.json`
- `data/upstox_nse_eq_instruments.json`
- `active_trades.csv`
- `*.jsonl`

## CACHE_IGNORE

- `data/cache/`
- `data/yfinance_cache/`
- `.pytest_cache/`
- `__pycache__/`
- `*.pyc`
- `.chrome-td-shot/`
- `.tmp_edge*/`

## ARCHIVE_OR_REMOVE

- Dashboard one-off backups such as `dashboard_backup_before_command_center_v4.py`.
- Extracted local review artifacts such as `blueprint_extracted.txt`.
- Local UI verification logs matching `streamlit_verify_*.log`.
- Superseded dashboard audit documents after the final retained report is chosen.

## DANGEROUS_REVIEW

- `.env` and any secret-bearing token or broker auth payload.
- Any file that can place live broker orders or mutate broker state.
- Any source path that writes scanner counts, candidates, trades, outcomes, bid/ask, spread, or alpha.
- Legacy Classic paths gated by `LEGACY_CLASSIC_FILTERS`.

## Current Ownership Decisions

- `runtime_continuous_core.py` is the canonical writer for active scanner/runtime/feed snapshots.
- `tools/refresh_mode_scanner_status.py` is retained only as a compatibility entrypoint and delegates to `runtime_continuous_core.py`.
- `dashboard.py` is read-only and must not refresh or mutate scanner/runtime state.

## Tracked Runtime Cleanup Still Required

The ignore rules stop new generated artifacts from being added, but already tracked generated files still need an index-only cleanup. Do not delete local runtime files until the operator confirms they are disposable.

Tracked generated/runtime paths currently visible in `git status` include:

- `data/cache/*.csv`
- `data/runtime/*.json`
- `data/runtime/*.jsonl`
- `data/journals/trade_outcomes.csv`
- `data/paper_trading/paper_account.json`
- `data/live_price_cache.json`
- `data/live_price_status.json`

Recommended cleanup after review:

- Keep files on disk for runtime continuity.
- Remove generated artifacts from source control with index-only removal.
- Commit `.gitignore` and this ownership document in the same cleanup commit.
