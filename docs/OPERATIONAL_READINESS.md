# Operational Readiness

Pepper is code-complete for secured paper-mode operation. It is not live-money ready until the live gate is satisfied with real elapsed paper-trading evidence.

## Burn-in checklist

### 14-day paper gate

- Run scheduled paper cycles on the intended symbols and timeframes for at least 14 distinct UTC days
- Review risk-agent vetoes daily
- Review scheduler failures and market-data `503` events daily
- Confirm no order path bypasses `ExecutionEngine.place_order()`

### 28-day live-readiness gate

- Extend the burn-in to at least 28 distinct UTC days
- Confirm the daily drawdown breaker was tested and still halts trading correctly
- Audit exchange or broker permissions before any live credential is enabled
- Define the first-capital ramp plan and keep it capped to a small percentage of intended capital

## Evidence sources

Pepper stores the verification artifacts needed for burn-in review:

- `GET /paper/runs`: persisted run history
- `GET /audit/trades`: decision logs, vetoes, fills, and router outcomes
- `GET /alerts`: operator-facing failures and warnings
- `GET /readiness/live-gate`: summary of observed burn-in days, veto counts, and router failures

## Operator review routine

1. Confirm scheduled jobs are active and symbols/timeframes match the intended burn-in plan.
2. Review the latest failed runs, if any.
3. Review recent vetoes and confirm the reasons make sense.
4. Review stale-data incidents and provider failures.
5. Keep live routing disabled until the 28-day gate is satisfied and permissions are audited.
