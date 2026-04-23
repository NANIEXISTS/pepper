# Changelog

All notable changes to this project will be tracked here.

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
