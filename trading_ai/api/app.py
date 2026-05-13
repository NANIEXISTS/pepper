from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from ..backtesting import BacktestEngine, EmaCrossoverStrategy, FeatureLeakageAnalyzer, LookAheadBiasError, WalkForwardOptimizer, WalkForwardValidator
from ..alerts import AlertService
from ..agents import AgentContext
from ..core.enums import OrderSide, OrderType, TradeSignal, TradingMode
from ..core.models import MarketDataRequest, OrderIntent, PortfolioSnapshot
from ..data import MarketDataService, build_market_data_provider
from ..data.exceptions import MarketDataUnavailableError
from ..execution import ExecutionEngine, PaperOrderRouter, build_live_order_router
from ..features import FeatureEngineer
from ..llm import LLMClient
from ..logging_config import configure_logging
from ..market_context import PolymarketHypeService
from ..orchestration import ManualPaperOrderRequest, PaperCycleJobCreate, PaperTradingScheduler, build_default_paper_trading_service
from ..persistence import LiveReadinessRecordView, TradeAuditStore
from ..portfolio import PortfolioService
from ..readiness import evaluate_paper_profitability
from ..reinforcement import ExecutionTimingCoordinator
from ..risk import PositionSizeRequest, PositionSizer, RiskAuditAgent, run_drawdown_breaker_selftest
from ..settings import get_settings
from ..strategy_builder import StrategyBacktestRequest, StrategyCompiler, StrategyDraftRequest, StrategyOptimizeRequest, StrategyValidateRequest
from ..venues import VenueCatalogService
from .security import AuthenticatedOperator, build_operator_auth


CREDENTIAL_AUDIT_KIND = "credential_audit"
DRAWDOWN_BREAKER_SELFTEST_KIND = "drawdown_breaker_selftest"
RAMP_PLAN_KIND = "ramp_plan"


class CredentialAuditAttestation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    venue: str = Field(min_length=1, max_length=64)
    scope: Literal["read_only", "trade", "trade_with_withdraw"]
    auditor: str = Field(min_length=1, max_length=64)
    notes: str = Field(default="", max_length=2048)


class RampPlanAttestation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_venue: str = Field(min_length=1, max_length=64)
    capital_cap_fraction: float = Field(gt=0.0, le=1.0)
    notes: str = Field(default="", max_length=2048)


class PaperOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: OrderIntent
    portfolio: PortfolioSnapshot
    agent_name: str = Field(default="manual", min_length=1, max_length=128)
    signal: TradeSignal = TradeSignal.HOLD
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = Field(default="Manual paper order", max_length=2048)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PositionSizeApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equity: float = Field(gt=0.0)
    entry_price: float = Field(gt=0.0)
    stop_loss_price: float = Field(gt=0.0)
    atr: float = Field(default=0.0, ge=0.0)
    available_cash: float = Field(default=0.0, ge=0.0)
    mode: Literal["fixed_fractional", "volatility_targeted"] = "fixed_fractional"
    target_daily_volatility_fraction: float = Field(default=0.01, gt=0.0, le=0.5)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.logging.level)

    audit_store = TradeAuditStore.from_database_url(settings.persistence.database_url)
    market_data_service = MarketDataService(
        build_market_data_provider(settings.data, settings.exchange, settings.alpaca),
        cache_max_staleness_seconds=settings.data.cache_max_staleness_seconds,
    )
    feature_engineer = FeatureEngineer()
    leakage_analyzer = FeatureLeakageAnalyzer()
    backtest_engine = BacktestEngine(settings.backtesting)
    walk_forward_validator = WalkForwardValidator(settings.backtesting, backtest_engine)
    walk_forward_optimizer = WalkForwardOptimizer(settings.backtesting, backtest_engine)
    position_sizer = PositionSizer(
        max_per_trade_risk_fraction=settings.risk.max_per_trade_risk_fraction,
    )
    alert_service = AlertService()
    portfolio_service = PortfolioService(starting_cash=settings.paper_trading.starting_cash)
    llm_client = LLMClient(settings.llm)
    strategy_compiler = StrategyCompiler()
    venue_catalog = VenueCatalogService(settings)
    polymarket_hype = PolymarketHypeService()
    execution_timing = ExecutionTimingCoordinator(settings.reinforcement)
    risk_agent = RiskAuditAgent(settings.risk)
    execution_engine = ExecutionEngine(
        settings=settings,
        risk_agent=risk_agent,
        audit_store=audit_store,
        paper_router=PaperOrderRouter(),
        live_router=build_live_order_router(settings),
    )
    paper_trading_service = build_default_paper_trading_service(
        market_data=market_data_service,
        feature_engineer=feature_engineer,
        execution_engine=execution_engine,
        portfolio_service=portfolio_service,
        alert_service=alert_service,
        llm_client=llm_client,
        paper_settings=settings.paper_trading,
        risk_settings=settings.risk,
        execution_timing=execution_timing,
    )
    paper_scheduler = PaperTradingScheduler(
        paper_trading_service=paper_trading_service,
        audit_store=audit_store,
        alert_service=alert_service,
    )
    auth = build_operator_auth(settings.auth, audit_store)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await audit_store.create_schema()
        saved_portfolio = await audit_store.load_portfolio_state()
        if saved_portfolio is not None:
            portfolio_service.restore_state(saved_portfolio)
        await paper_scheduler.initialize()
        try:
            yield
        finally:
            await paper_scheduler.close()
            await audit_store.close()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings = settings
    app.state.market_data_service = market_data_service
    app.state.feature_engineer = feature_engineer
    app.state.execution_engine = execution_engine
    app.state.backtest_engine = backtest_engine
    app.state.portfolio_service = portfolio_service
    app.state.alert_service = alert_service
    app.state.paper_trading_service = paper_trading_service
    app.state.paper_scheduler = paper_scheduler
    app.state.strategy_compiler = strategy_compiler
    app.state.venue_catalog = venue_catalog
    app.state.polymarket_hype = polymarket_hype
    app.state.auth_enabled = settings.auth.enabled

    dashboard_dir = Path(__file__).resolve().parent.parent / "dashboard"
    app.mount("/assets", StaticFiles(directory=dashboard_dir), name="dashboard-assets")

    def _backtest_lookback_bars() -> int:
        return max(
            settings.data.default_lookback_bars,
            settings.backtesting.train_bars + (settings.backtesting.test_bars * settings.backtesting.max_walk_forward_windows),
            settings.backtesting.trend_filter_window + 50,
        )

    async def _fetch_market_frame(
        request: MarketDataRequest,
        *,
        require_fresh: bool = False,
        action_name: str = "market data fetch",
    ):
        try:
            frame = await market_data_service.fetch_dataframe(request)
        except MarketDataUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        if require_fresh and frame.attrs.get("stale", False):
            cache_age_seconds = float(frame.attrs.get("cache_age_seconds", 0.0))
            raise HTTPException(
                status_code=503,
                detail=(
                    f"{action_name} requires fresh market data for {request.symbol} {request.timeframe}. "
                    f"Last good snapshot age: {cache_age_seconds:.1f}s."
                ),
            )
        return frame

    async def _polymarket_hype_report(*, symbol: str | None, limit: int = 12) -> dict:
        try:
            return (await polymarket_hype.fetch_hype(symbol=symbol, limit=limit)).model_dump(mode="json")
        except Exception as exc:
            return polymarket_hype.unavailable_report(symbol=symbol, error=str(exc)).model_dump(mode="json")

    async def _polymarket_terminal_report(*, symbol: str | None, limit: int = 8) -> dict:
        try:
            return (await polymarket_hype.fetch_terminal(symbol=symbol, limit=limit)).model_dump(mode="json")
        except Exception as exc:
            return polymarket_hype.unavailable_terminal_report(symbol=symbol, error=str(exc)).model_dump(mode="json")

    async def _record_operator_action(
        operator: AuthenticatedOperator,
        *,
        action: str,
        resource: str,
        outcome: str,
        details: dict | None = None,
    ) -> None:
        # Audit trail runs in dev mode too: "easy to audit" can't depend on auth being enabled,
        # so we still record the local-dev attribution rather than silently dropping the event.
        await audit_store.record_operator_action(
            username=operator.username,
            role=operator.role,
            action=action,
            resource=resource,
            outcome=outcome,
            details={**(details or {}), "auth_enabled": settings.auth.enabled},
        )

    async def _price_map_for_portfolio(*, symbol: str, timeframe: str, latest_price: float) -> dict[str, float]:
        tracked_symbols = {symbol, *portfolio_service.positions.keys()}
        price_map: dict[str, float] = {symbol: latest_price}
        tasks: list[tuple[str, asyncio.Task]] = []
        for tracked_symbol in tracked_symbols:
            if tracked_symbol == symbol:
                continue
            request = MarketDataRequest(
                symbol=tracked_symbol,
                timeframe=timeframe,
                lookback_bars=50,
            )
            tasks.append((tracked_symbol, asyncio.create_task(market_data_service.fetch_dataframe(request))))

        for tracked_symbol, task in tasks:
            try:
                frame = await task
            except Exception:
                continue
            if frame.attrs.get("stale", False):
                continue
            price_map[tracked_symbol] = float(frame.iloc[-1]["close"])

        return price_map

    async def _run_backtest_summary(symbol: str, timeframe: str, lookback_bars: int) -> dict:
        request = MarketDataRequest(symbol=symbol, timeframe=timeframe, lookback_bars=lookback_bars)
        raw_frame = await _fetch_market_frame(request, action_name="Backtest")
        try:
            leakage_check = leakage_analyzer.assert_no_lookahead(raw_frame, feature_engineer)
        except LookAheadBiasError as exc:
            raise HTTPException(status_code=500, detail=f"Look-ahead bias detected in engineered features: {exc}") from exc

        enriched = feature_engineer.enrich(raw_frame)
        strategy = EmaCrossoverStrategy(
            short_window=settings.backtesting.short_window,
            long_window=settings.backtesting.long_window,
            trend_filter_window=settings.backtesting.trend_filter_window,
            long_only=True,
        )
        backtest_result = backtest_engine.run(
            enriched,
            strategy=strategy,
            symbol=symbol,
            timeframe=timeframe,
        )
        try:
            walk_forward_payload = walk_forward_validator.run(
                enriched,
                strategy=strategy,
                symbol=symbol,
                timeframe=timeframe,
            ).model_dump(mode="json")
        except ValueError as exc:
            walk_forward_payload = {
                "strategy_name": strategy.name,
                "symbol": symbol,
                "timeframe": timeframe,
                "summary": {
                    "window_count": 0,
                    "compounded_return_fraction": 0.0,
                    "average_sharpe_ratio": 0.0,
                    "median_window_return_fraction": 0.0,
                    "worst_window_drawdown_fraction": 0.0,
                    "warnings": [str(exc)],
                },
                "windows": [],
            }
        return {
            "leakage_check": leakage_check.model_dump(mode="json"),
            "backtest": backtest_result.model_dump(mode="json"),
            "walk_forward": walk_forward_payload,
        }

    async def _run_graph_backtest(payload: StrategyBacktestRequest) -> dict:
        request = MarketDataRequest(
            symbol=payload.symbol,
            timeframe=payload.timeframe,
            lookback_bars=payload.lookback_bars,
        )
        raw_frame = await _fetch_market_frame(request, action_name="Strategy graph backtest")
        try:
            leakage_check = leakage_analyzer.assert_no_lookahead(raw_frame, feature_engineer)
        except LookAheadBiasError as exc:
            raise HTTPException(status_code=500, detail=f"Look-ahead bias detected in engineered features: {exc}") from exc

        validation = strategy_compiler.validate_graph(payload.graph)
        if not validation.passed:
            raise HTTPException(status_code=422, detail=validation.issues)

        strategy = strategy_compiler.compile_graph(payload.graph)
        enriched = feature_engineer.enrich(raw_frame)
        backtest_result = backtest_engine.run(
            enriched,
            strategy=strategy,
            symbol=payload.symbol,
            timeframe=payload.timeframe,
        )
        walk_forward_result = walk_forward_validator.run(
            enriched,
            strategy=strategy,
            symbol=payload.symbol,
            timeframe=payload.timeframe,
        )
        return {
            "graph": payload.graph.model_dump(mode="json"),
            "validation": validation.model_dump(mode="json"),
            "leakage_check": leakage_check.model_dump(mode="json"),
            "backtest": backtest_result.model_dump(mode="json"),
            "walk_forward": walk_forward_result.model_dump(mode="json"),
        }

    def _attestation_is_fresh(record: LiveReadinessRecordView | None, valid_days: int, now: datetime) -> bool:
        if record is None:
            return False
        recorded_at = record.recorded_at
        if recorded_at.tzinfo is None:
            # SQLite strips tz info on round-trip even when the column is declared with timezone=True.
            recorded_at = recorded_at.replace(tzinfo=UTC)
        age = now - recorded_at
        return age <= timedelta(days=valid_days)

    async def _paper_profitability_report(runs: list | None = None) -> dict:
        review_settings = settings.live_readiness
        evaluated_runs = runs if runs is not None else await paper_scheduler.list_runs(limit=5000)
        report = evaluate_paper_profitability(
            evaluated_runs,
            required_days=review_settings.profitability_review_days,
            min_total_return_fraction=review_settings.profitability_min_total_return_fraction,
        )
        return report.model_dump(mode="json")

    async def _live_gate_summary() -> dict:
        runs = await paper_scheduler.list_runs(limit=5000)
        trade_events = await audit_store.list_trade_events(limit=1000)
        latest_readiness = await audit_store.latest_live_readiness_events()
        completed_runs = [run for run in runs if run.status == "completed"]
        active_run_days = sorted({run.started_at.date().isoformat() for run in completed_runs})
        profitability_report = await _paper_profitability_report(runs)
        router_failures = sum(1 for run in runs if run.status == "failed")
        risk_vetoes = sum(1 for event in trade_events if not event.risk_check_passed)
        drawdown_breakers = sum(1 for event in trade_events if "drawdown" in event.risk_reason.lower())
        first_started_at = min((run.started_at for run in completed_runs), default=None)
        last_finished_at = max((run.finished_at for run in completed_runs if run.finished_at is not None), default=None)

        readiness_settings = settings.live_readiness
        required_burn_in_days = readiness_settings.required_burn_in_days
        now = datetime.now(UTC)

        credential_audit = latest_readiness.get(CREDENTIAL_AUDIT_KIND)
        drawdown_selftest = latest_readiness.get(DRAWDOWN_BREAKER_SELFTEST_KIND)
        ramp_plan = latest_readiness.get(RAMP_PLAN_KIND)

        credential_audit_fresh = _attestation_is_fresh(
            credential_audit, readiness_settings.credential_audit_valid_days, now
        )
        drawdown_selftest_fresh = _attestation_is_fresh(
            drawdown_selftest, readiness_settings.drawdown_breaker_test_valid_days, now
        )
        drawdown_selftest_passed = bool(
            drawdown_selftest and drawdown_selftest.payload.get("passed") is True
        )
        ramp_plan_recorded = ramp_plan is not None
        ramp_plan_within_cap = bool(
            ramp_plan
            and float(ramp_plan.payload.get("capital_cap_fraction", 1.0))
            <= readiness_settings.ramp_plan_max_capital_fraction
        )

        burn_in_passed = len(active_run_days) >= required_burn_in_days
        live_trading_enabled = settings.execution.live_trading_enabled
        live_capital_allowed = (
            burn_in_passed
            and profitability_report["passed"]
            and credential_audit_fresh
            and drawdown_selftest_fresh
            and drawdown_selftest_passed
            and ramp_plan_recorded
            and ramp_plan_within_cap
            and live_trading_enabled
        )
        blocking_reasons: list[str] = []
        if not burn_in_passed:
            blocking_reasons.append(
                f"paper_burn_in_incomplete:{len(active_run_days)}_of_{required_burn_in_days}_days"
            )
        blocking_reasons.extend(profitability_report["blocking_reasons"])
        if not credential_audit_fresh:
            blocking_reasons.append("credential_audit_missing_or_stale")
        if not drawdown_selftest_fresh:
            blocking_reasons.append("drawdown_breaker_selftest_missing_or_stale")
        if drawdown_selftest is not None and not drawdown_selftest_passed:
            blocking_reasons.append("drawdown_breaker_selftest_failed")
        if not ramp_plan_recorded:
            blocking_reasons.append("ramp_plan_not_recorded")
        elif not ramp_plan_within_cap:
            blocking_reasons.append("ramp_plan_exceeds_configured_cap")
        if not live_trading_enabled:
            blocking_reasons.append("live_trading_disabled_by_config")

        return {
            "runbook_documented": True,
            "verification_artifacts_persisted": bool(runs or trade_events),
            "paper_burn_in_days_observed": len(active_run_days),
            "paper_burn_in_dates": active_run_days,
            "required_burn_in_days": required_burn_in_days,
            "fourteen_day_gate_passed": len(active_run_days) >= 14,
            "fourteen_day_profitability_passed": profitability_report["passed"],
            "fourteen_day_profitability": profitability_report,
            "twenty_eight_day_gate_passed": len(active_run_days) >= 28,
            "risk_veto_count": risk_vetoes,
            "drawdown_breaker_count": drawdown_breakers,
            "router_failure_count": router_failures,
            "live_trading_enabled": live_trading_enabled,
            "configured_live_router": settings.execution.live_router,
            "first_completed_run_started_at": first_started_at.isoformat() if first_started_at is not None else None,
            "last_completed_run_finished_at": last_finished_at.isoformat() if last_finished_at is not None else None,
            "credential_audit": credential_audit.model_dump(mode="json") if credential_audit else None,
            "credential_audit_fresh": credential_audit_fresh,
            "credential_audit_valid_days": readiness_settings.credential_audit_valid_days,
            "drawdown_breaker_selftest": drawdown_selftest.model_dump(mode="json") if drawdown_selftest else None,
            "drawdown_breaker_selftest_fresh": drawdown_selftest_fresh,
            "drawdown_breaker_selftest_passed": drawdown_selftest_passed,
            "drawdown_breaker_selftest_valid_days": readiness_settings.drawdown_breaker_test_valid_days,
            "ramp_plan": ramp_plan.model_dump(mode="json") if ramp_plan else None,
            "ramp_plan_recorded": ramp_plan_recorded,
            "ramp_plan_within_cap": ramp_plan_within_cap,
            "ramp_plan_max_capital_fraction": readiness_settings.ramp_plan_max_capital_fraction,
            "live_capital_allowed": live_capital_allowed,
            "blocking_reasons": blocking_reasons,
        }

    @app.get("/", include_in_schema=False)
    async def index() -> RedirectResponse:
        return RedirectResponse(url="/dashboard")

    @app.get("/dashboard", include_in_schema=False)
    async def dashboard(_: AuthenticatedOperator = Depends(auth.require_viewer)) -> FileResponse:
        return FileResponse(dashboard_dir / "index.html")

    @app.get("/dashboard/data")
    async def dashboard_data(
        symbol: str | None = None,
        timeframe: str | None = None,
        lookback_bars: int | None = None,
        _: AuthenticatedOperator = Depends(auth.require_viewer),
    ) -> dict:
        active_symbol = symbol or settings.default_symbol
        active_timeframe = timeframe or settings.paper_trading.default_cycle_timeframe
        request = MarketDataRequest(
            symbol=active_symbol,
            timeframe=active_timeframe,
            lookback_bars=lookback_bars or max(settings.paper_trading.default_lookback_bars, settings.data.default_lookback_bars),
        )
        market_frame = await _fetch_market_frame(request, action_name="Dashboard refresh")
        enriched = feature_engineer.enrich(market_frame)
        recent_market = [
            {
                "timestamp": timestamp.isoformat(),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
            for timestamp, row in market_frame.tail(80).iterrows()
        ]
        indicator_columns = [
            "close",
            "ema_20",
            "ema_50",
            "ema_200",
            "rsi_14",
            "macd",
            "macd_signal",
            "atr_14",
            "volume_zscore_20",
        ]
        latest_features: dict[str, float] = {}
        for column in indicator_columns:
            if column not in enriched.columns:
                continue
            value = enriched.iloc[-1][column]
            if pd.notna(value):
                latest_features[column] = float(value)
        latest_price = float(market_frame.iloc[-1]["close"])
        price_map = await _price_map_for_portfolio(
            symbol=active_symbol,
            timeframe=active_timeframe,
            latest_price=latest_price,
        )
        backtest_summary = await _run_backtest_summary(
            symbol=active_symbol,
            timeframe=active_timeframe,
            lookback_bars=max(request.lookback_bars, _backtest_lookback_bars()),
        )
        portfolio_view = portfolio_service.mark_to_market(price_map)
        stop_loss_price = latest_price * 0.97
        atr = latest_features.get("atr_14", latest_price * 0.02)
        risk_size_preview = position_sizer.size(
            PositionSizeRequest(
                equity=max(portfolio_view.equity, 1.0),
                entry_price=latest_price,
                stop_loss_price=stop_loss_price,
                atr=max(atr, 0.0),
                available_cash=max(portfolio_view.cash, 0.0),
                mode="volatility_targeted",
            )
        )
        live_readiness = await _live_gate_summary()
        backtest_metrics = backtest_summary["backtest"]["metrics"]
        walk_forward_summary = backtest_summary["walk_forward"]["summary"]
        research_edge_positive = (
            backtest_metrics["total_return_fraction"] > 0.0
            and walk_forward_summary["average_sharpe_ratio"] > 0.0
            and backtest_summary["leakage_check"]["passed"]
        )
        paper_profitability = live_readiness["fourteen_day_profitability"]
        if paper_profitability["passed"] and research_edge_positive and live_readiness["live_capital_allowed"]:
            profit_headline = "Paper profit test passed and live gates are clear."
            profit_verdict = "review_for_live"
        elif not paper_profitability["complete"]:
            profit_headline = "14-day paper profit test is still collecting evidence."
            profit_verdict = "paper_profit_pending"
        elif not paper_profitability["passed"]:
            profit_headline = "14-day paper run is not profitable yet; keep live blocked."
            profit_verdict = "paper_not_profitable"
        elif research_edge_positive:
            profit_headline = "Paper run is profitable, but live gates still protect capital."
            profit_verdict = "paper_until_gates_clear"
        else:
            profit_headline = "No deployable edge yet; keep researching in paper."
            profit_verdict = "research_only"
        portfolio_breakdown = [
            {
                "symbol": position.symbol,
                "market_value": position.market_value,
                "unrealized_pnl": position.unrealized_pnl,
                "realized_pnl": position.realized_pnl,
                "weight_fraction": (position.market_value / portfolio_view.equity) if portfolio_view.equity else 0.0,
            }
            for position in portfolio_view.positions.values()
        ]
        walk_forward_windows = [
            {
                "train_start": window["train_start"],
                "train_end": window["train_end"],
                "test_start": window["test_start"],
                "test_end": window["test_end"],
                "total_return_fraction": window["result"]["metrics"]["total_return_fraction"],
                "sharpe_ratio": window["result"]["metrics"]["sharpe_ratio"],
                "max_drawdown_fraction": window["result"]["metrics"]["max_drawdown_fraction"],
                "warnings": window["result"]["metrics"]["warnings"],
            }
            for window in backtest_summary["walk_forward"]["windows"]
        ]

        return {
            "config": {
                "app_name": settings.app_name,
                "mode": settings.app_mode.value,
                "default_symbol": settings.default_symbol,
                "provider": settings.data.provider,
                "provider_routing": settings.data.provider_routing,
                "supported_timeframes": settings.data.supported_timeframes,
                "exchange_id": settings.exchange.exchange_id,
                "live_router": settings.execution.live_router,
                "live_trading_enabled": settings.execution.live_trading_enabled,
            },
            "market": {
                "symbol": active_symbol,
                "timeframe": active_timeframe,
                "provider": market_frame.attrs.get("provider"),
                "source_timeframe": market_frame.attrs.get("source_timeframe"),
                "gap_count": market_frame.attrs.get("gap_count", 0),
                "stale": market_frame.attrs.get("stale", False),
                "cache_age_seconds": market_frame.attrs.get("cache_age_seconds", 0.0),
                "provider_failures": market_frame.attrs.get("provider_failures", []),
                "latest_timestamp": market_frame.index[-1].isoformat(),
                "latest_price": float(market_frame.iloc[-1]["close"]),
                "recent_bars": recent_market,
            },
            "features": latest_features,
            "portfolio": portfolio_view.model_dump(mode="json"),
            "portfolio_breakdown": portfolio_breakdown,
            "profit_path": {
                "headline": profit_headline,
                "verdict": profit_verdict,
                "plain_english": (
                    "Pepper can only practically help profits by converting an idea into a tested edge, "
                    "rejecting it when held-out results are weak, and sizing any accepted trade so one loss "
                    "cannot dominate the account."
                ),
                "edge": {
                    "backtest_return_fraction": backtest_metrics["total_return_fraction"],
                    "walk_forward_sharpe_ratio": walk_forward_summary["average_sharpe_ratio"],
                    "walk_forward_window_count": walk_forward_summary["window_count"],
                    "worst_window_drawdown_fraction": walk_forward_summary["worst_window_drawdown_fraction"],
                    "leakage_check_passed": backtest_summary["leakage_check"]["passed"],
                    "trade_count": backtest_metrics["trade_count"],
                },
                "paper_profitability": paper_profitability,
                "risk_size_preview": {
                    "entry_price": latest_price,
                    "stop_loss_price": stop_loss_price,
                    "atr": atr,
                    **risk_size_preview.model_dump(mode="json"),
                },
                "capital_gate": {
                    "live_capital_allowed": live_readiness["live_capital_allowed"],
                    "blocking_reasons": live_readiness["blocking_reasons"],
                    "paper_burn_in_days_observed": live_readiness["paper_burn_in_days_observed"],
                    "required_burn_in_days": live_readiness["required_burn_in_days"],
                },
            },
            "alerts": [record.model_dump(mode="json") for record in alert_service.list_recent(limit=8)],
            "jobs": [job.model_dump(mode="json") for job in await paper_scheduler.list_jobs()],
            "runs": [run.model_dump(mode="json") for run in await paper_scheduler.list_runs(limit=8)],
            "trade_audit": [event.model_dump(mode="json") for event in await audit_store.list_trade_events(limit=8)],
            "venues": venue_catalog.describe().model_dump(mode="json"),
            "market_context": {
                "polymarket_hype": await _polymarket_hype_report(symbol=active_symbol, limit=10),
                "prediction_terminal": await _polymarket_terminal_report(symbol=active_symbol, limit=8),
            },
            "live_readiness": live_readiness,
            "strategy_builder": {
                "supported_indicators": ["ema", "rsi", "bollinger"],
                "supported_families": ["ema_crossover", "bollinger_mean_reversion"],
                "sample_prompt": (
                    "Buy when EMA 20 crosses above EMA 50, only when price is above EMA 200 "
                    "and RSI 14 is below 70, with stop loss 3%."
                ),
                "sample_mean_reversion_prompt": (
                    "Bollinger 20 mean reversion with 2 std bands, exit on revert to mid, "
                    "with stop loss 2%."
                ),
                "sample_optimization_grid": {
                    "fast_window": [10, 15, 20, 25],
                    "slow_window": [40, 50, 60, 80],
                },
            },
            "backtest": {
                "leakage_check": backtest_summary["leakage_check"],
                "metrics": backtest_summary["backtest"]["metrics"],
                "equity_curve": backtest_summary["backtest"]["equity_curve"][-80:],
                "walk_forward_summary": backtest_summary["walk_forward"]["summary"],
                "walk_forward_windows": walk_forward_windows,
                "trades": backtest_summary["backtest"]["trades"][-12:],
            },
            "last_cycle": (
                paper_trading_service.last_cycle.model_dump(mode="json")
                if paper_trading_service.last_cycle is not None
                else None
            ),
        }

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "mode": settings.app_mode.value}

    @app.get("/auth/session")
    async def auth_session(operator: AuthenticatedOperator = Depends(auth.require_viewer)) -> dict:
        return {
            "auth_enabled": settings.auth.enabled,
            "username": operator.username,
            "role": operator.role,
        }

    @app.get("/config")
    async def config_summary(_: AuthenticatedOperator = Depends(auth.require_viewer)) -> dict:
        return {
            "app_name": settings.app_name,
            "mode": settings.app_mode.value,
            "default_symbol": settings.default_symbol,
            "provider": settings.data.provider,
            "provider_routing": settings.data.provider_routing,
            "supported_timeframes": settings.data.supported_timeframes,
            "exchange_id": settings.exchange.exchange_id,
            "paper_trading_timeframe": settings.paper_trading.default_cycle_timeframe,
            "live_router": settings.execution.live_router,
            "live_trading_enabled": settings.execution.live_trading_enabled,
            "auth_enabled": settings.auth.enabled,
        }

    @app.get("/venues/capabilities")
    async def venue_capabilities(_: AuthenticatedOperator = Depends(auth.require_viewer)) -> dict:
        return venue_catalog.describe().model_dump(mode="json")

    @app.get("/market-context/polymarket/hype")
    async def polymarket_hype_context(
        symbol: str | None = None,
        limit: int = 12,
        _: AuthenticatedOperator = Depends(auth.require_viewer),
    ) -> dict:
        if limit < 1 or limit > 50:
            raise HTTPException(status_code=400, detail="limit must be between 1 and 50.")
        return await _polymarket_hype_report(symbol=symbol or settings.default_symbol, limit=limit)

    @app.get("/market-context/polymarket/terminal")
    async def polymarket_prediction_terminal(
        symbol: str | None = None,
        limit: int = 8,
        _: AuthenticatedOperator = Depends(auth.require_viewer),
    ) -> dict:
        if limit < 1 or limit > 25:
            raise HTTPException(status_code=400, detail="limit must be between 1 and 25.")
        return await _polymarket_terminal_report(symbol=symbol or settings.default_symbol, limit=limit)

    @app.get("/readiness/live-gate")
    async def live_gate_readiness(_: AuthenticatedOperator = Depends(auth.require_viewer)) -> dict:
        return await _live_gate_summary()

    @app.get("/readiness/paper-profitability")
    async def paper_profitability_readiness(_: AuthenticatedOperator = Depends(auth.require_viewer)) -> dict:
        return await _paper_profitability_report()

    @app.get("/readiness/history")
    async def readiness_history(
        kind: str | None = None,
        limit: int = 50,
        _: AuthenticatedOperator = Depends(auth.require_viewer),
    ) -> dict:
        if limit <= 0 or limit > 500:
            raise HTTPException(status_code=400, detail="limit must be between 1 and 500.")
        events = await audit_store.list_live_readiness_events(kind=kind, limit=limit)
        return {"events": [event.model_dump(mode="json") for event in events]}

    @app.post("/readiness/credential-audit")
    async def record_credential_audit(
        payload: CredentialAuditAttestation,
        operator: AuthenticatedOperator = Depends(auth.require_admin),
    ) -> dict:
        record = await audit_store.record_live_readiness_event(
            kind=CREDENTIAL_AUDIT_KIND,
            recorded_by=operator.username,
            payload=payload.model_dump(mode="json"),
        )
        await _record_operator_action(
            operator,
            action="record_credential_audit",
            resource=payload.venue,
            outcome="recorded",
            details={"scope": payload.scope},
        )
        return {
            "attestation": record.model_dump(mode="json"),
            "summary": await _live_gate_summary(),
        }

    @app.post("/readiness/drawdown-breaker/selftest")
    async def run_drawdown_breaker_selftest_endpoint(
        operator: AuthenticatedOperator = Depends(auth.require_admin),
    ) -> dict:
        result = await run_drawdown_breaker_selftest(settings.risk)
        record = await audit_store.record_live_readiness_event(
            kind=DRAWDOWN_BREAKER_SELFTEST_KIND,
            recorded_by=operator.username,
            payload=result.model_dump(mode="json"),
        )
        await _record_operator_action(
            operator,
            action="run_drawdown_breaker_selftest",
            resource="risk_agent",
            outcome="passed" if result.passed else "failed",
            details={"reason": result.reason},
        )
        return {
            "result": result.model_dump(mode="json"),
            "attestation": record.model_dump(mode="json"),
            "summary": await _live_gate_summary(),
        }

    @app.post("/readiness/ramp-plan")
    async def record_ramp_plan(
        payload: RampPlanAttestation,
        operator: AuthenticatedOperator = Depends(auth.require_admin),
    ) -> dict:
        cap = settings.live_readiness.ramp_plan_max_capital_fraction
        if payload.capital_cap_fraction > cap:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Ramp plan capital fraction {payload.capital_cap_fraction} exceeds "
                    f"configured maximum {cap}."
                ),
            )
        record = await audit_store.record_live_readiness_event(
            kind=RAMP_PLAN_KIND,
            recorded_by=operator.username,
            payload=payload.model_dump(mode="json"),
        )
        await _record_operator_action(
            operator,
            action="record_ramp_plan",
            resource=payload.target_venue,
            outcome="recorded",
            details={"capital_cap_fraction": payload.capital_cap_fraction},
        )
        return {
            "attestation": record.model_dump(mode="json"),
            "summary": await _live_gate_summary(),
        }

    @app.post("/strategies/draft")
    async def draft_strategy(
        payload: StrategyDraftRequest,
        _: AuthenticatedOperator = Depends(auth.require_viewer),
    ) -> dict:
        draft = strategy_compiler.draft_from_prompt(payload.prompt)
        return draft.model_dump(mode="json")

    @app.post("/strategies/validate")
    async def validate_strategy(
        payload: StrategyValidateRequest,
        _: AuthenticatedOperator = Depends(auth.require_viewer),
    ) -> dict:
        validation = strategy_compiler.validate_graph(payload.graph)
        return validation.model_dump(mode="json")

    @app.post("/strategies/backtests")
    async def backtest_strategy(
        payload: StrategyBacktestRequest,
        _: AuthenticatedOperator = Depends(auth.require_viewer),
    ) -> dict:
        return await _run_graph_backtest(payload)

    @app.post("/strategies/optimize")
    async def optimize_strategy(
        payload: StrategyOptimizeRequest,
        _: AuthenticatedOperator = Depends(auth.require_viewer),
    ) -> dict:
        request = MarketDataRequest(
            symbol=payload.symbol,
            timeframe=payload.timeframe,
            lookback_bars=payload.lookback_bars,
        )
        raw_frame = await _fetch_market_frame(request, action_name="Strategy optimization")
        try:
            leakage_check = leakage_analyzer.assert_no_lookahead(raw_frame, feature_engineer)
        except LookAheadBiasError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Look-ahead bias detected in engineered features: {exc}",
            ) from exc

        base_validation = strategy_compiler.validate_graph(payload.base_graph)
        if not base_validation.passed:
            raise HTTPException(status_code=422, detail=base_validation.issues)

        enriched = feature_engineer.enrich(raw_frame)

        def _factory(parameters: dict[str, float]):
            mutated = strategy_compiler.apply_parameter_overlay(payload.base_graph, parameters)
            validation = strategy_compiler.validate_graph(mutated)
            if not validation.passed:
                raise ValueError("; ".join(validation.issues))
            return strategy_compiler.compile_graph(mutated)

        try:
            result = walk_forward_optimizer.optimize(
                enriched,
                strategy_factory=_factory,
                parameter_grid={key: list(values) for key, values in payload.parameter_grid.items()},
                symbol=payload.symbol,
                timeframe=payload.timeframe,
                base_strategy_name=payload.base_graph.name,
                selection_metric=payload.selection_metric,
                max_combinations=payload.max_combinations,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        return {
            "leakage_check": leakage_check.model_dump(mode="json"),
            "base_graph": payload.base_graph.model_dump(mode="json"),
            "optimization": result.model_dump(mode="json"),
        }

    @app.post("/risk/size")
    async def risk_size(
        payload: PositionSizeApiRequest,
        _: AuthenticatedOperator = Depends(auth.require_viewer),
    ) -> dict:
        sizer = PositionSizer(
            max_per_trade_risk_fraction=settings.risk.max_per_trade_risk_fraction,
            target_daily_volatility_fraction=payload.target_daily_volatility_fraction,
        )
        result = sizer.size(
            PositionSizeRequest(
                equity=payload.equity,
                entry_price=payload.entry_price,
                stop_loss_price=payload.stop_loss_price,
                atr=payload.atr,
                available_cash=payload.available_cash,
                mode=payload.mode,
            )
        )
        return result.model_dump(mode="json")

    @app.get("/market-data/{symbol}")
    async def market_data(
        symbol: str,
        timeframe: str = "1d",
        lookback_bars: int | None = None,
        _: AuthenticatedOperator = Depends(auth.require_viewer),
    ) -> dict:
        request = MarketDataRequest(
            symbol=symbol,
            timeframe=timeframe,
            lookback_bars=lookback_bars or settings.data.default_lookback_bars,
        )
        frame = await _fetch_market_frame(request, action_name="Market data preview")
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "provider": frame.attrs.get("provider"),
            "source_timeframe": frame.attrs.get("source_timeframe"),
            "gap_count": frame.attrs.get("gap_count", 0),
            "stale": frame.attrs.get("stale", False),
            "cache_age_seconds": frame.attrs.get("cache_age_seconds", 0.0),
            "provider_failures": frame.attrs.get("provider_failures", []),
            "rows": len(frame),
            "columns": list(frame.columns),
            "latest": frame.tail(1).reset_index().to_dict(orient="records"),
        }

    @app.get("/features/{symbol}")
    async def features(
        symbol: str,
        timeframe: str = "1d",
        lookback_bars: int | None = None,
        _: AuthenticatedOperator = Depends(auth.require_viewer),
    ) -> dict:
        request = MarketDataRequest(
            symbol=symbol,
            timeframe=timeframe,
            lookback_bars=lookback_bars or settings.data.default_lookback_bars,
        )
        frame = await _fetch_market_frame(request, action_name="Feature preview")
        enriched = feature_engineer.enrich(frame)
        latest = enriched.tail(1).reset_index().to_dict(orient="records")
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "rows": len(enriched),
            "latest": latest,
        }

    @app.get("/backtests/ema/{symbol}")
    async def ema_backtest(
        symbol: str,
        timeframe: str = "1d",
        lookback_bars: int | None = None,
        _: AuthenticatedOperator = Depends(auth.require_viewer),
    ) -> dict:
        minimum_lookback = _backtest_lookback_bars()
        result = await _run_backtest_summary(
            symbol=symbol,
            timeframe=timeframe,
            lookback_bars=lookback_bars or minimum_lookback,
        )
        return {"symbol": symbol, "timeframe": timeframe, **result}

    @app.get("/portfolio")
    async def portfolio(_: AuthenticatedOperator = Depends(auth.require_viewer)) -> dict:
        view = portfolio_service.mark_to_market({})
        return view.model_dump(mode="json")

    @app.get("/alerts")
    async def alerts(limit: int = 20, _: AuthenticatedOperator = Depends(auth.require_viewer)) -> dict:
        records = [record.model_dump(mode="json") for record in alert_service.list_recent(limit=limit)]
        return {"alerts": records}

    @app.get("/audit/trades")
    async def trade_audit(limit: int = 20, _: AuthenticatedOperator = Depends(auth.require_viewer)) -> dict:
        events = [event.model_dump(mode="json") for event in await audit_store.list_trade_events(limit=limit)]
        return {"events": events}

    @app.get("/audit/operators")
    async def operator_audit(limit: int = 20, _: AuthenticatedOperator = Depends(auth.require_admin)) -> dict:
        events = [event.model_dump(mode="json") for event in await audit_store.list_operator_actions(limit=limit)]
        return {"events": events}

    @app.get("/paper/jobs")
    async def paper_jobs(_: AuthenticatedOperator = Depends(auth.require_viewer)) -> dict:
        jobs = [job.model_dump(mode="json") for job in await paper_scheduler.list_jobs()]
        return {"jobs": jobs}

    @app.post("/paper/jobs")
    async def create_paper_job(
        payload: PaperCycleJobCreate,
        operator: AuthenticatedOperator = Depends(auth.require_trader),
    ) -> dict:
        job = await paper_scheduler.create_job(payload)
        await _record_operator_action(
            operator,
            action="create_paper_job",
            resource=f"{payload.symbol}:{payload.timeframe}",
            outcome="success",
            details={"interval_seconds": payload.interval_seconds, "auto_start": payload.auto_start},
        )
        return {"job": job.model_dump(mode="json")}

    @app.post("/paper/jobs/{job_id}/start")
    async def start_paper_job(
        job_id: int,
        operator: AuthenticatedOperator = Depends(auth.require_trader),
    ) -> dict:
        job = await paper_scheduler.start_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Paper cycle job {job_id} not found.")
        await _record_operator_action(
            operator,
            action="start_paper_job",
            resource=str(job_id),
            outcome="success",
        )
        return {"job": job.model_dump(mode="json")}

    @app.post("/paper/jobs/{job_id}/pause")
    async def pause_paper_job(
        job_id: int,
        operator: AuthenticatedOperator = Depends(auth.require_trader),
    ) -> dict:
        job = await paper_scheduler.pause_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Paper cycle job {job_id} not found.")
        await _record_operator_action(
            operator,
            action="pause_paper_job",
            resource=str(job_id),
            outcome="success",
        )
        return {"job": job.model_dump(mode="json")}

    @app.post("/paper/jobs/{job_id}/run")
    async def run_paper_job_once(
        job_id: int,
        operator: AuthenticatedOperator = Depends(auth.require_trader),
    ) -> dict:
        try:
            cycle = await paper_scheduler.run_job_once(job_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except MarketDataUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await _record_operator_action(
            operator,
            action="run_paper_job_once",
            resource=str(job_id),
            outcome="success",
            details={"symbol": cycle.symbol, "execution_status": cycle.execution_report.status.value if cycle.execution_report else "none"},
        )
        return cycle.model_dump(mode="json")

    @app.get("/paper/runs")
    async def paper_runs(
        limit: int = 20,
        job_id: int | None = None,
        _: AuthenticatedOperator = Depends(auth.require_viewer),
    ) -> dict:
        runs = [run.model_dump(mode="json") for run in await paper_scheduler.list_runs(limit=limit, job_id=job_id)]
        return {"runs": runs}

    @app.post("/paper/cycles/{symbol}")
    async def run_paper_cycle(
        symbol: str,
        timeframe: str | None = None,
        lookback_bars: int | None = None,
        operator: AuthenticatedOperator = Depends(auth.require_trader),
    ) -> dict:
        try:
            cycle = await paper_scheduler.run_ad_hoc_cycle(
                symbol=symbol,
                timeframe=timeframe or settings.paper_trading.default_cycle_timeframe,
                lookback_bars=lookback_bars or settings.paper_trading.default_lookback_bars,
            )
        except MarketDataUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await _record_operator_action(
            operator,
            action="run_paper_cycle",
            resource=f"{symbol}:{timeframe or settings.paper_trading.default_cycle_timeframe}",
            outcome="success",
            details={"execution_status": cycle.execution_report.status.value if cycle.execution_report else "none"},
        )
        return cycle.model_dump(mode="json")

    @app.post("/paper/orders/manual")
    async def manual_paper_order(
        payload: ManualPaperOrderRequest,
        operator: AuthenticatedOperator = Depends(auth.require_trader),
    ) -> dict:
        if settings.app_mode != TradingMode.PAPER:
            raise HTTPException(status_code=409, detail="Manual paper orders are disabled in live mode.")

        request = MarketDataRequest(
            symbol=payload.symbol,
            timeframe=payload.timeframe,
            lookback_bars=payload.lookback_bars,
        )
        frame = await _fetch_market_frame(request, require_fresh=True, action_name="Manual paper order")
        latest_price = float(frame.iloc[-1]["close"])
        price_map = await _price_map_for_portfolio(
            symbol=payload.symbol,
            timeframe=payload.timeframe,
            latest_price=latest_price,
        )

        if payload.side.value == "sell":
            position = portfolio_service.positions.get(payload.symbol)
            if position is None or position.quantity + 1e-12 < payload.quantity:
                raise HTTPException(status_code=409, detail=f"Not enough {payload.symbol} position to sell.")

        order = OrderIntent(
            symbol=payload.symbol,
            side=payload.side,
            quantity=payload.quantity,
            entry_price=latest_price,
            stop_loss_price=payload.stop_loss_price,
            take_profit_price=payload.take_profit_price,
            order_type=payload.order_type,
            metadata={"source": "operator-dashboard", "operator_username": operator.username},
        )
        signal = TradeSignal.BUY if payload.side.value == "buy" else TradeSignal.SELL
        report = await execution_engine.place_order(
            agent_name="operator-dashboard",
            signal=signal,
            confidence=1.0,
            rationale=payload.rationale,
            order=order,
            portfolio=portfolio_service.snapshot(price_map),
            metadata={"source": "operator-dashboard", "timeframe": payload.timeframe, "operator_username": operator.username},
        )
        if report.status.value == "filled":
            portfolio_service.apply_fill(order, report)
            await audit_store.save_portfolio_state(portfolio_service.export_state())
        await _record_operator_action(
            operator,
            action="manual_paper_order",
            resource=payload.symbol,
            outcome=report.status.value,
            details={"side": payload.side.value, "quantity": payload.quantity, "timeframe": payload.timeframe},
        )
        return {
            "order": order.model_dump(mode="json"),
            "report": report.model_dump(mode="json"),
            "portfolio": portfolio_service.mark_to_market(price_map).model_dump(mode="json"),
        }

    @app.post("/orders/paper")
    async def paper_order(
        payload: PaperOrderRequest,
        operator: AuthenticatedOperator = Depends(auth.require_trader),
    ) -> dict:
        if settings.app_mode != TradingMode.PAPER:
            raise HTTPException(status_code=409, detail="Paper order endpoint is disabled in live mode.")

        report = await execution_engine.place_order(
            agent_name=payload.agent_name,
            signal=payload.signal,
            confidence=payload.confidence,
            rationale=payload.rationale,
            order=payload.order,
            portfolio=payload.portfolio,
            metadata=dict(payload.metadata),
        )
        await _record_operator_action(
            operator,
            action="paper_order_api",
            resource=payload.order.symbol,
            outcome=report.status.value,
            details={"agent_name": payload.agent_name},
        )
        return report.model_dump(mode="json")

    return app
