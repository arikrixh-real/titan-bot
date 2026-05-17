# TITAN Runtime Live-Market Validation Checklist

## 1. PRE-MARKET CHECKS

- [ ] Daemon process is running.
- [ ] Dashboard is online and reachable.
- [ ] Runtime attention status reports OK.
- [ ] No stale runtime files are present.
- [ ] Live price monitor is active.
- [ ] Scanner is active.
- [ ] Paper engine is active.

## 2. MARKET OPEN VALIDATION

- [ ] Scanner generates valid trade candidates.
- [ ] Master brain evaluates detected setups.
- [ ] Trade levels are generated for approved setups.
- [ ] Paper positions open only inside the configured trade window.
- [ ] Duplicate prevention blocks repeated entries for the same setup.

## 3. LIVE SESSION VALIDATION

- [ ] Live prices refresh continuously.
- [ ] Unrealized PnL updates as prices move.
- [ ] TP/SL monitoring remains active.
- [ ] No runtime crashes occur.
- [ ] Daemon heartbeat updates on schedule.
- [ ] Dashboard runtime summary updates with current state.

## 4. TRADE LIFECYCLE VALIDATION

- [ ] TP exits close positions correctly.
- [ ] SL exits close positions correctly.
- [ ] Realized PnL updates after position close.
- [ ] Equity updates after realized PnL changes.
- [ ] Open position count reduces after exits.
- [ ] Closed position count increases after exits.

## 5. SAFETY VALIDATION

- [ ] No Telegram messages are sent.
- [ ] No broker orders are placed.
- [ ] No Supabase trades are created.
- [ ] No journal trade writes occur.
- [ ] Market-hour gating prevents out-of-window activity.
- [ ] Stale-price protection blocks invalid price-dependent actions.

## 6. END-OF-DAY VALIDATION

- [ ] Daemon remains stable through session close.
- [ ] No duplicate paper positions exist.
- [ ] Performance summary matches observed session activity.
- [ ] Runtime recovery diagnostics accurately reflect session health.

## 7. SUCCESS CRITERIA

### Stable Runtime

The runtime is stable when the daemon, dashboard, scanner, live price monitor, paper engine, heartbeat, and runtime summary remain active and current for the full validation period without crashes or stale state.

### Successful Autonomous Validation

Autonomous validation is successful when candidates are detected, evaluated, converted into trade levels, and managed through the paper engine only during valid market windows, with duplicate prevention and runtime diagnostics working as expected.

### Safe Paper Lifecycle

The paper lifecycle is safe when all trades remain paper-only, TP/SL exits update positions and PnL correctly, no external notifications or broker actions are triggered, and no production trade or journal records are written.
