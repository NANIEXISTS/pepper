# Changelog

All notable changes to this project will be tracked here.

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
