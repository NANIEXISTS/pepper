# Operational Readiness

Pepper is code-complete for secured paper-mode operation. It is not live-money ready until every gate listed here is satisfied with real elapsed paper-trading evidence and real operator attestations.

The `GET /readiness/live-gate` endpoint is the single source of truth. It returns a composite `live_capital_allowed` verdict and a list of `blocking_reasons` that must be empty before any live capital is enabled.

The operator dashboard opens with a Live Launch Brief that shows the same verdict, burn-in progress, blockers, proof, and next action in plain language. The endpoint remains the authoritative machine-readable contract.

`GET /readiness/paper-profitability` is the 14-day profit checkpoint. It evaluates only persisted completed paper-cycle records that include portfolio equity, groups them by UTC day, and compares the first observed equity with the latest observed equity across the latest 14 equity days. Missing days or missing equity payloads make the result incomplete; they do not count as profit evidence.

## Gates

`live_capital_allowed` is only `true` when all of the following are satisfied:

1. Paper burn-in days observed meets `live_readiness.required_burn_in_days` (default 28 distinct UTC days)
2. The latest `live_readiness.profitability_review_days` paper-equity days (default 14) are net profitable
3. A credential audit attestation has been recorded and is within `live_readiness.credential_audit_valid_days`
4. A drawdown-breaker self-test has been recorded within `live_readiness.drawdown_breaker_test_valid_days` and returned `passed=true`
5. A ramp plan has been recorded with `capital_cap_fraction` at or below `live_readiness.ramp_plan_max_capital_fraction`
6. `execution.live_trading_enabled` is explicitly set to `true`

## Burn-in checklist

### 14-day paper gate

- Run scheduled paper cycles on the intended symbols and timeframes for at least 14 distinct UTC days
- Review `GET /readiness/paper-profitability` and require `passed=true`
- Review risk-agent vetoes daily
- Review scheduler failures and market-data `503` events daily
- Confirm no order path bypasses `ExecutionEngine.place_order()`

### 28-day live-readiness gate

- Extend the burn-in to at least 28 distinct UTC days
- Run the drawdown-breaker self-test and confirm it vetoes trading (`POST /readiness/drawdown-breaker/selftest`)
- Audit exchange or broker permissions before any live credential is enabled, then attest (`POST /readiness/credential-audit`)
- Define the first-capital ramp plan within the configured cap and record it (`POST /readiness/ramp-plan`)

## Evidence sources

Pepper stores the verification artifacts needed for burn-in review:

- `GET /paper/runs`: persisted run history
- `GET /audit/trades`: decision logs, vetoes, fills, and router outcomes
- `GET /alerts`: operator-facing failures and warnings
- `GET /readiness/live-gate`: composite verdict, gate status, blocking reasons, burn-in summary
- `GET /readiness/paper-profitability`: 14-day paper profit result, daily equity breakdown, drawdown, missing evidence
- `GET /readiness/history`: append-only attestation and self-test trail

`GET /market-context/polymarket/hype` and `GET /market-context/polymarket/terminal` are product intelligence surfaces, not readiness evidence sources. They can support research and operator review by exposing public prediction-market hype, wallet flow, rule risk, book quality, cross-venue comparisons, and source-watch queries. They do not authorize live capital or bypass execution/risk controls.

`POST /market-context/polymarket/terminal/snapshots` persists public terminal snapshots for trend review. Snapshot deltas can show wallet PnL movement, new whale trades, rule-risk changes, and book-quality movement, but those deltas remain research context until a separate strategy path explicitly consumes and validates them.

## Drawdown-breaker self-test

`POST /readiness/drawdown-breaker/selftest` (admin only) synthesises a portfolio whose daily PnL has just crossed the configured drawdown limit, runs the live `RiskAuditAgent`, and asserts it refuses the order and flags the circuit breaker. The outcome is persisted and time-bounded by `drawdown_breaker_test_valid_days`.

This replaces "operator promises they tested it" with an actual failing signal in the gate if the breaker stops working.

## Credential audit attestation

`POST /readiness/credential-audit` (admin only) records that an operator has actually reviewed the live exchange or broker credentials before enabling live routing. The attestation captures `venue`, `scope` (`read_only`, `trade`, or `trade_with_withdraw`), `auditor`, and optional `notes`. It is time-bounded by `credential_audit_valid_days`, which forces the audit to be refreshed periodically.

## Ramp plan attestation

`POST /readiness/ramp-plan` (admin only) records the first-capital ramp plan. The server rejects any `capital_cap_fraction` above `live_readiness.ramp_plan_max_capital_fraction`, so the ramp limit is a code-enforced invariant rather than a documentation hope.

## Operator review routine

1. Confirm scheduled jobs are active and symbols/timeframes match the intended burn-in plan.
2. Review the latest failed runs, if any.
3. Review recent vetoes and confirm the reasons make sense.
4. Review stale-data incidents and provider failures.
5. Before enabling live routing, pull `GET /readiness/live-gate` and confirm `live_capital_allowed` is `true` and `blocking_reasons` is empty.
