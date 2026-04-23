# Architecture

## Current phase

The repository now covers Phase 1 through the code architecture for Phase 5. The goal is still to make future trading logic safe to add, not to rush into live trading.

Implemented layers:

- `trading_ai/settings.py`: typed settings loaded once from `config.yaml` and `.env`
- `trading_ai/core/`: shared enums and pydantic models
- `trading_ai/data/`: async market-data fetching and normalization
- `trading_ai/venues/`: venue capability metadata and normalization helpers
- `trading_ai/features/`: deterministic, bar-close feature engineering
- `trading_ai/backtesting/`: EMA baseline strategy, leakage checks, and walk-forward validation
- `trading_ai/strategy_builder/`: typed strategy graphs, validation, and deterministic NL compilation
- `trading_ai/portfolio/`: cash, positions, equity, and daily anchor tracking
- `trading_ai/alerts/`: operator-facing alert history
- `trading_ai/agents/`: analyst, debate, strategy, and trader agents
- `trading_ai/orchestration/`: paper-trading cycle orchestration
- `trading_ai/llm/`: optional LLM integration with deterministic fallback
- `trading_ai/reinforcement/`: execution-timing environment and order-type coordinator
- `trading_ai/risk/`: mandatory risk-audit step
- `trading_ai/execution/`: single order entry point plus paper/live router split
- `trading_ai/persistence/`: async audit storage for trade decisions and outcomes
- `trading_ai/api/`: FastAPI service exposing the backend safely

## Hard invariants

- Data layer returns data only. No strategy decisions there.
- Venue metadata is inspectable, but capability inspection itself must not place orders.
- Feature engineering runs on ordered, timezone-aware bars only.
- Backtests execute on the next bar after a signal, never on the same bar that generated it.
- Walk-forward test windows must remain out-of-sample relative to their training windows.
- Strategy prompts compile into typed graphs first. They do not execute directly.
- `RiskAuditAgent.run()` must execute before every order.
- `ExecutionEngine.place_order()` is the only order entry point.
- Paper and live trading must share the same execution engine.
- Portfolio state must be updated from execution reports, not from strategy predictions.
- RL execution timing may influence order type, but not market direction.
- Live routing stays disabled until the paper-trading and backtesting gates are met.

## Next phases

### Phase 2

- Expand the backtesting harness beyond the EMA baseline
- Add richer experiment logging
- Add parameter studies without contaminating the holdout windows

### Phase 3

- Add scheduled runners and durable operator workflows around the paper-trading loop
- Persist portfolio snapshots and alerts if needed

### Phase 4

- Expand the multi-agent analysis stack
- Add richer explainable decision traces and memory

### Phase 5

- Add offline training for the execution-timing environment
- Compare RL fills against naive execution benchmarks with held-out data

### Phase 6

- Add real exchange connectors only after paper-trading gates pass
- Verify real-world paper-trading duration and live capital ramp-up before calling Phase 6 complete
- Keep the live-gate checklist reviewable through the API and operator docs

## What not to do

- Do not add LLM strategy generation before a trustworthy backtest harness exists.
- Do not add live exchange code paths that bypass the paper/live router interface.
- Do not let research notebooks or ad hoc scripts become production dependencies.
