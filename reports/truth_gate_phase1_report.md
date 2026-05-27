# TITAN Truth Gate Phase 1 Report

## Result

FAIL

The truth gate is installed and now reports unsafe runtime conditions instead of allowing silent fake success.

## Files Changed

- `core/truth_gate.py`
- `tools/truth_gate_check.py`
- `data/runtime/truth_gate_status.json`
- `runtime_scanner.py`
- `setup_engine.py`
- `journal/trade_journal.py`
- `journal/trade_execution_layer.py`
- `journal/outcome_tracker.py`
- `reports/truth_gate_phase1_report.md`
- `reports/truth_gate_phase1_report.json`

## Exact Gates Added

- Market data gate: requires Upstox live LTP during market hours, marks cache/fallback unsafe, validates instrument key, validates OHLC columns, and detects stale OHLC.
- Scanner path gate: runtime path must prove `SCORED_DYNAMIC_50`; `CACHED_RANDOM_FALLBACK` fails live scan/trade mode with `RUNTIME_NOT_USING_SCORED_DYNAMIC_50`.
- Trade setup gate: validates symbol, side, entry, stop loss, target, level ordering, RR near 2.0, `final_score`, and reason before journal/save paths.
- Outcome gate: validates OPEN trade fields, known source table, and real live current price before TP/SL closure.
- Status writer: writes `data/runtime/truth_gate_status.json` with PASS/FAIL/DEGRADED, blocked reason, unsafe sources, stale data, and next action.

## What Is Now Blocked

- Real setup generation when runtime path is `CACHED_RANDOM_FALLBACK`.
- Real setup generation when live LTP is not proven as Upstox live during market hours.
- Setup journaling and active trade insertion when setup structure is invalid.
- TP/SL closure when current price is stale, cached, fallback, not live, or the trade row is malformed.

## What Still Needs Fixing Next

- Wire runtime scanner/setup selection to the real scored dynamic selector path and stamp `SCORED_DYNAMIC_50`.
- Renew/fix Upstox token so market-hours LTP returns live `UPSTOX`/`ACTIVE`.
- Refresh or rebuild OHLC cache with valid fresh `Open, High, Low, Close, Volume` data.
- Backfill or migrate older journal samples that do not have `final_score`.
- Create or map missing Supabase tables if the dashboard still expects `trade_journal`, `signals`, and `alerts`.

## Proof Command Output

### `python -m py_compile core/truth_gate.py`

```text
<no output; exit code 0>
```

### `python -m py_compile tools/truth_gate_check.py`

```text
<no output; exit code 0>
```

### `python tools/truth_gate_check.py`

```text
TRUTH GATE STATUS: FAIL

Market data
- LTP and instrument source: FAIL | LTP_NOT_UPSTOX_LIVE_DURING_MARKET

OHLC freshness
- OHLC sample freshness: FAIL | ONE_OR_MORE_OHLC_SAMPLES_INVALID
- Cache dir: D:\TITAN\data\cache

Dynamic selector wiring
- SCORED_DYNAMIC_50 wiring: FAIL | RUNTIME_NOT_USING_SCORED_DYNAMIC_50
- Safe selector required: SCORED_DYNAMIC_50

Scanner runtime path
- Runtime path proof: FAIL | RUNTIME_NOT_USING_SCORED_DYNAMIC_50
- Detected path: CACHED_RANDOM_FALLBACK
- Selection state: D:\TITAN\data\scan_selection_state.json

Trade validation sample
- Trade setup sample: FAIL | FINAL_SCORE_MISSING

Outcome validation sample
- Outcome sample: DEGRADED | NO_OUTCOME_SAMPLE

Supabase reachable tables
- Supabase read-only table check: DEGRADED | ONE_OR_MORE_TABLES_UNREACHABLE
- trades: REACHABLE
- trade_results: REACHABLE
- scan_health_logs: REACHABLE
- scans: REACHABLE
- trade_journal: UNREACHABLE:APIError:{'message': "Could not find the table 'public.trade_journal' in the schema cache", 'code': 'PGRST205', 'hint': "Perhaps you meant the table 'public.trade_results'", 'details': None}
- signals: UNREACHABLE:APIError:{'message': "Could not find the table 'public.signals' in the schema cache", 'code': 'PGRST205', 'hint': "Perhaps you meant the table 'public.scan_symbols'", 'details': None}
- alerts: UNREACHABLE:APIError:{'message': "Could not find the table 'public.alerts' in the schema cache", 'code': 'PGRST205', 'hint': "Perhaps you meant the table 'public.trade_results'", 'details': None}

Status file: D:\TITAN\data\runtime\truth_gate_status.json
```

### `python tools/audit_titan_clean_pipeline.py`

```text
[UpstoxStatus] symbol=RELIANCE | status=TOKEN_INVALID | source=LIVE_PRICE_CACHE | reason=Upstox token invalid/expired; using cache if available
TITAN CLEAN PIPELINE AUDIT
Overall: FAIL
A_environment_and_tokens: PASS
B_upstox_live_price: FAIL
C_ohlc_history: FAIL
D_dynamic_50_stock_selection: PASS
E_scanner_filter_engines: PASS
F_final_setups_trade_creation: FAIL
G_duplicate_open_trade_protection: PASS
H_trade_journaling: PASS
I_outcome_tracker: PASS
J_closed_trades_saving: PASS
Supabase_read_only_schema: FAIL
K_dashboard_reading: PASS
Reports: reports\titan_clean_pipeline_audit.md | reports\titan_clean_pipeline_audit.json
```

## Scope Confirmation

- Broker execution was not touched.
- Telegram code was not touched.
- Supabase cleanup/delete code was not touched.
- Dashboard layout/theme was not touched.
- Learning/evolution reset was not touched.
- Cached/fallback mode was not deleted; it is now visible and unsafe for live scanning/trading.
