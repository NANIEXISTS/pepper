from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import pandas as pd

from ..backtesting import BacktestEngine, EmaCrossoverStrategy, FeatureLeakageAnalyzer, LookAheadBiasError, WalkForwardValidator
from ..alerts import AlertService
from ..agents import AgentContext
from ..core.enums import TradeSignal, TradingMode
from ..core.models import MarketDataRequest, OrderIntent, PortfolioSnapshot
from ..data import MarketDataService, build_market_data_provider
from ..data.exceptions import MarketDataUnavailableError
from ..execution import ExecutionEngine, PaperOrderRouter, build_live_order_router
from ..features import FeatureEngineer
from ..llm import LLMClient
from ..logging_config import configure_logging
from ..orchestration import ManualPaperOrderRequest, PaperCycleJobCreate, PaperTradingScheduler, build_default_paper_trading_service
from ..persistence import TradeAuditStore
from ..portfolio import PortfolioService
from ..reinforcement import ExecutionTimingCoordinator
from ..risk import RiskAuditAgent
from ..settings import get_settings
from ..strategy_builder import StrategyBacktestRequest, StrategyCompiler, StrategyDraftRequest, StrategyValidateRequest
from ..venues import VenueCatalogService
from .security import AuthenticatedOperator, build_operator_auth


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
    alert_service = AlertService()
    portfolio_service = PortfolioService(starting_cash=settings.paper_trading.starting_cash)
    llm_client = LLMClient(settings.llm)
    strategy_compiler = StrategyCompiler()
    venue_catalog = VenueCatalogService(settings)
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

    async def _record_operator_action(
        operator: AuthenticatedOperator,
        *,
        action: str,
        resource: str,
        outcome: str,
        details: dict | None = None,
    ) -> None:
        if not settings.auth.enabled:
            return
        await audit_store.record_operator_action(
            username=operator.username,
            role=operator.role,
            action=action,
            resource=resource,
            outcome=outcome,
            details=details,
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
        walk_forward_result = walk_forward_validator.run(
            enriched,
            strategy=strategy,
            symbol=symbol,
            timeframe=timeframe,
        )
        return {
            "leakage_check": leakage_check.model_dump(mode="json"),
            "backtest": backtest_result.model_dump(mode="json"),
            "walk_forward": walk_forward_result.model_dump(mode="json"),
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

    async def _live_gate_summary() -> dict:
        runs = await paper_scheduler.list_runs(limit=1000)
        trade_events = await audit_store.list_trade_events(limit=1000)
        completed_runs = [run for run in runs if run.status == "completed"]
        active_run_days = sorted({run.started_at.date().isoformat() for run in completed_runs})
        router_failures = sum(1 for run in runs if run.status == "failed")
        risk_vetoes = sum(1 for event in trade_events if not event.risk_check_passed)
        drawdown_breakers = sum(1 for event in trade_events if "drawdown" in event.risk_reason.lower())
        first_started_at = min((run.started_at for run in completed_runs), default=None)
        last_finished_at = max((run.finished_at for run in completed_runs if run.finished_at is not None), default=None)
        return {
            "runbook_documented": True,
            "verification_artifacts_persisted": bool(runs or trade_events),
            "paper_burn_in_days_observed": len(active_run_days),
            "paper_burn_in_dates": active_run_days,
            "fourteen_day_gate_passed": len(active_run_days) >= 14,
            "twenty_eight_day_gate_passed": len(active_run_days) >= 28,
            "risk_veto_count": risk_vetoes,
            "drawdown_breaker_count": drawdown_breakers,
            "router_failure_count": router_failures,
            "live_trading_enabled": settings.execution.live_trading_enabled,
            "configured_live_router": settings.execution.live_router,
            "first_completed_run_started_at": first_started_at.isoformat() if first_started_at is not None else None,
            "last_completed_run_finished_at": last_finished_at.isoformat() if last_finished_at is not None else None,
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
        price_map = await _price_map_for_portfolio(
            symbol=active_symbol,
            timeframe=active_timeframe,
            latest_price=float(market_frame.iloc[-1]["close"]),
        )
        backtest_summary = await _run_backtest_summary(
            symbol=active_symbol,
            timeframe=active_timeframe,
            lookback_bars=max(request.lookback_bars, _backtest_lookback_bars()),
        )
        portfolio_view = portfolio_service.mark_to_market(price_map)
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
            "alerts": [record.model_dump(mode="json") for record in alert_service.list_recent(limit=8)],
            "jobs": [job.model_dump(mode="json") for job in await paper_scheduler.list_jobs()],
            "runs": [run.model_dump(mode="json") for run in await paper_scheduler.list_runs(limit=8)],
            "trade_audit": [event.model_dump(mode="json") for event in await audit_store.list_trade_events(limit=8)],
            "venues": venue_catalog.describe().model_dump(mode="json"),
            "strategy_builder": {
                "supported_indicators": ["ema", "rsi"],
                "sample_prompt": (
                    "Buy when EMA 20 crosses above EMA 50, only when price is above EMA 200 "
                    "and RSI 14 is below 70, with stop loss 3%."
                ),
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

    @app.get("/readiness/live-gate")
    async def live_gate_readiness(_: AuthenticatedOperator = Depends(auth.require_viewer)) -> dict:
        return await _live_gate_summary()

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
        payload: dict,
        operator: AuthenticatedOperator = Depends(auth.require_trader),
    ) -> dict:
        if settings.app_mode != TradingMode.PAPER:
            raise HTTPException(status_code=409, detail="Paper order endpoint is disabled in live mode.")

        try:
            order = OrderIntent.model_validate(payload["order"])
            portfolio = PortfolioSnapshot.model_validate(payload["portfolio"])
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"Missing payload key: {exc}") from exc

        report = await execution_engine.place_order(
            agent_name=payload.get("agent_name", "manual"),
            signal=TradeSignal(payload.get("signal", "HOLD")),
            confidence=float(payload.get("confidence", 0.0)),
            rationale=payload.get("rationale", "Manual paper order"),
            order=order,
            portfolio=portfolio,
            metadata=payload.get("metadata", {}),
        )
        await _record_operator_action(
            operator,
            action="paper_order_api",
            resource=order.symbol,
            outcome=report.status.value,
            details={"agent_name": payload.get("agent_name", "manual")},
        )
        return report.model_dump(mode="json")

    return app
