# Changelog

All notable changes to this project will be tracked here.

## [0.8.2] - 2026-05-14

### Added

- Paper-only Polymarket Profit Hunter that ranks one-hour opportunities across CLOB spread/depth, volume, liquidity, wallet flow, source-watch context, negative-risk structure, and rule ambiguity
- `POST /market-context/polymarket/hunter/run` endpoint that returns `TRADE`, `NO_TRADE`, or `INSUFFICIENT_EDGE` plus exact blockers and a paper ticket only when all gates pass
- Dashboard "One-Hour Profit Hunter" panel with a client-readable verdict, paper-ticket area, and top candidate blockers

### Changed

- Moved the noisy prediction-market terminal detail behind a collapsible dashboard deep dive so the primary UI answers whether Pepper has a safe one-hour paper opportunity now
- Kept cross-venue matches as watchlist items only; unconfirmed rule matches cannot dominate the trade verdict or create tickets
- Negative-risk markets now require a computed basket edge or directional confirmation before a paper ticket can be issued

## [0.7.0] - 2026-04-23

### Added

- Alpaca market-data adapter for equities and crypto using async `httpx`
- Alpaca live-router foundation behind the same execution boundary as the existing ccxt router
- Venue capability catalog and `/venues/capabilities` API for provider/router inspection
- Deterministic strategy-builder package with typed strategy graphs, validation, and prompt compilation
- Strategy-builder API endpoints for draft, validate, and backtest flows
- Live-gate readiness summary endpoint and operational runbook in `docs/OPERATIONAL_READINESS.md`
- Dashboard build/validate/run strategy workflow, venue capability review, walk-forward inspection, and richer trade/run drill-downs
- Tests for Alpaca provider/router integration, strategy compilation, and the new API surfaces

## [0.6.0] - 2026-04-23

### Added

- Optional operator authentication with `viewer`, `trader`, and `admin` roles for dashboard/API access
- Operator-audit event persistence for auth failures, authorization failures, and privileged paper-mode actions
- Last-good market-data snapshot fallback for read paths during transient provider failures
- Explicit stale-data metadata in dashboard and market-data API payloads
- Tests covering auth gating, operator audit, stale-data rejection on writable paths, and `503` behavior when no provider or cache is available

### Changed

- Writable paper-mode endpoints now require trader access when auth is enabled
- Admin-only endpoint added for operator audit inspection
- Manual paper orders and paper cycles reject stale market snapshots instead of trading on cached data silently
- Market-data failures now degrade predictably instead of bubbling opaque backend exceptions

## [0.5.0] - 2026-04-23

### Added

- Routed market-data provider stack with `ccxt` primary and Yahoo fallback
- `ccxt` OHLCV provider with exchange capability checks and symbol normalization
- Market-data validation for malformed OHLCV rows, duplicate timestamps, and intraday gap surfacing
- Market-data tests for provider fallback, candle validation, hourly-to-4h resampling, and `ccxt` capability checks

### Changed

- Default runtime data mode now uses routed providers instead of Yahoo-only fetching
- Dashboard and config payloads now expose provider routing metadata
- Market-data endpoints now report provider, source timeframe, and detected gap count

## [0.4.0] - 2026-04-23

### Added

- Durable paper portfolio restore across restarts
- Manual paper-order endpoint for the operator console
- Trade-audit listing endpoint and dashboard trade-history view
- Writable dashboard controls for creating, starting, pausing, and running paper jobs
- Dashboard forms for manual paper orders and scheduled job creation
- Multi-symbol price refresh before paper risk checks so held positions do not go stale during normal operation

### Changed

- Dashboard overview now includes trade-audit history
- Paper-trading scheduler persists portfolio state after completed runs

## [0.3.1] - 2026-04-23

### Fixed

- Rejected sells without an existing long position instead of fabricating realized PnL
- Removed closed positions cleanly even when they closed at a loss
- Counted `bars_held` using bars with actual exposure only
- Guarded analyst confidence math against zero or invalid close prices
- Rejected order placement when portfolio valuation contains stale position prices
- Logged scheduler loop failures explicitly and hardened task cleanup

### Added

- Regression tests for portfolio accounting, stale-price rejection, bars-held counting, analyst zero-price handling, and paper sell slippage direction
- Regression assertion that walk-forward results end exactly at each test-window boundary

## [0.3.0] - 2026-04-23

### Added

- Persistent paper-cycle jobs and run-history tables
- Background paper-trading scheduler with startup restore for active jobs
- API endpoints for creating, starting, pausing, running, and listing paper jobs
- API endpoint for listing persisted paper-cycle runs
- Dashboard views for scheduled jobs and recent runs
- Scheduler and API tests covering job history and overlap protection

### Changed

- Manual paper cycles now persist run history through the same control-plane path as scheduled cycles
- Paper-trading service rejects overlapping cycles for the same symbol

## [0.2.0] - 2026-04-23

### Added

- Operator console served at `/dashboard`
- Aggregated dashboard read model at `/dashboard/data`
- In-memory last-cycle state for the paper-trading service
- Dashboard-specific API tests

### Changed

- Bumped project version to `0.2.0`
- Updated README to document the console and new endpoints
- Packaged static dashboard assets with the Python distribution

## [0.1.0] - 2026-04-23

### Added

- Production-oriented backend foundation for market data, feature engineering, risk-gated execution, and FastAPI delivery
- EMA backtesting, leakage checks, and walk-forward validation
- Paper-trading orchestration, portfolio accounting, alerts, multi-agent seams, and RL execution-timing primitives
- CI workflow for `pytest`
