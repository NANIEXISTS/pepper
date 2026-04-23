# Repo Guide

## How to handle this repository

Treat this repository as one product with one active backend architecture. Do not let it turn into a pile of experiments, one-off bots, or duplicate subsystems.

## Directory rules

- Put API code in `trading_ai/api/`.
- Put shared typed models in `trading_ai/core/`.
- Put data providers and normalization in `trading_ai/data/`.
- Put venue capability metadata and symbol/timeframe normalization helpers in `trading_ai/venues/`.
- Put feature engineering in `trading_ai/features/`.
- Put baseline strategies, leakage checks, and validation logic in `trading_ai/backtesting/`.
- Put typed strategy graph compilation in `trading_ai/strategy_builder/`.
- Put agent logic in `trading_ai/agents/`.
- Put portfolio accounting in `trading_ai/portfolio/`.
- Put orchestration services in `trading_ai/orchestration/`.
- Put alerting in `trading_ai/alerts/`.
- Put optional LLM adapters in `trading_ai/llm/`.
- Put RL execution primitives in `trading_ai/reinforcement/`.
- Put risk policies in `trading_ai/risk/`.
- Put execution routing in `trading_ai/execution/`.
- Put persistence code in `trading_ai/persistence/`.
- Put tests in `tests/`.
- Put operator documentation in `docs/`.
- Put helper scripts in `scripts/`.

## Contribution rules

- Add one logical unit of work at a time.
- Add tests with the code change, not later.
- Prefer replacing stubs over creating parallel implementations.
- Keep top-level clutter low. New top-level files need a good reason.
- Remove dead scaffold code once the replacement is verified.

## Risk rules for code review

- Reject any order path that bypasses `ExecutionEngine`.
- Reject synchronous HTTP calls in async paths.
- Reject hardcoded thresholds that belong in `config.yaml`.
- Reject features that use future data.
- Reject strategy-authoring flows that jump straight from prompt text to order placement.
- Reject live trading changes without paper-trading coverage and tests.

## Security rules

- Do not keep credentials in the repo root.
- Keep `.env` local only.
- Ignore `*.pem`, `*.db`, and cache artifacts.
- Treat exchange permissions as read-plus-trade only.

## Definition of a clean repo

A clean repo means:

- one active architecture
- no stale scaffold directories
- no generated cache folders committed
- clear placement rules for new code
- tests and docs evolving with the implementation
