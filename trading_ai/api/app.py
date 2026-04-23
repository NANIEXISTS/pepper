from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from ..backtesting import BacktestEngine, EmaCrossoverStrategy, FeatureLeakageAnalyzer, LookAheadBiasError, WalkForwardValidator
from ..alerts import AlertService
from ..agents import AgentContext
from ..core.enums import TradeSignal, TradingMode
from ..core.models import MarketDataRequest, OrderIntent, PortfolioSnapshot
from ..data.providers import YahooFinanceProvider
from ..data.service import MarketDataService
from ..execution import CcxtLiveOrderRouter, ExecutionEngine, PaperOrderRouter
from ..features import FeatureEngineer
from ..llm import LLMClient
from ..logging_config import configure_logging
from ..orchestration import build_default_paper_trading_service
from ..persistence import TradeAuditStore
from ..portfolio import PortfolioService
from ..reinforcement import ExecutionTimingCoordinator
from ..risk import RiskAuditAgent
from ..settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.logging.level)

    audit_store = TradeAuditStore.from_database_url(settings.persistence.database_url)
    market_data_service = MarketDataService(YahooFinanceProvider(settings.data))
    feature_engineer = FeatureEngineer()
    leakage_analyzer = FeatureLeakageAnalyzer()
    backtest_engine = BacktestEngine(settings.backtesting)
    walk_forward_validator = WalkForwardValidator(settings.backtesting, backtest_engine)
    alert_service = AlertService()
    portfolio_service = PortfolioService(starting_cash=settings.paper_trading.starting_cash)
    llm_client = LLMClient(settings.llm)
    execution_timing = ExecutionTimingCoordinator(settings.reinforcement)
    risk_agent = RiskAuditAgent(settings.risk)
    execution_engine = ExecutionEngine(
        settings=settings,
        risk_agent=risk_agent,
        audit_store=audit_store,
        paper_router=PaperOrderRouter(),
        live_router=CcxtLiveOrderRouter(settings=settings.exchange, enabled=settings.execution.live_trading_enabled),
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

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await audit_store.create_schema()
        try:
            yield
        finally:
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

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "mode": settings.app_mode.value}

    @app.get("/config")
    async def config_summary() -> dict:
        return {
            "app_name": settings.app_name,
            "mode": settings.app_mode.value,
            "default_symbol": settings.default_symbol,
            "provider": settings.data.provider,
            "supported_timeframes": settings.data.supported_timeframes,
            "paper_trading_timeframe": settings.paper_trading.default_cycle_timeframe,
            "live_trading_enabled": settings.execution.live_trading_enabled,
        }

    @app.get("/market-data/{symbol}")
    async def market_data(symbol: str, timeframe: str = "1d", lookback_bars: int | None = None) -> dict:
        request = MarketDataRequest(
            symbol=symbol,
            timeframe=timeframe,
            lookback_bars=lookback_bars or settings.data.default_lookback_bars,
        )
        frame = await market_data_service.fetch_dataframe(request)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "rows": len(frame),
            "columns": list(frame.columns),
            "latest": frame.tail(1).reset_index().to_dict(orient="records"),
        }

    @app.get("/features/{symbol}")
    async def features(symbol: str, timeframe: str = "1d", lookback_bars: int | None = None) -> dict:
        request = MarketDataRequest(
            symbol=symbol,
            timeframe=timeframe,
            lookback_bars=lookback_bars or settings.data.default_lookback_bars,
        )
        frame = await market_data_service.fetch_dataframe(request)
        enriched = feature_engineer.enrich(frame)
        latest = enriched.tail(1).reset_index().to_dict(orient="records")
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "rows": len(enriched),
            "latest": latest,
        }

    @app.get("/backtests/ema/{symbol}")
    async def ema_backtest(symbol: str, timeframe: str = "1d", lookback_bars: int | None = None) -> dict:
        minimum_lookback = max(
            settings.data.default_lookback_bars,
            settings.backtesting.train_bars + (settings.backtesting.test_bars * settings.backtesting.max_walk_forward_windows),
            settings.backtesting.trend_filter_window + 50,
        )
        request = MarketDataRequest(
            symbol=symbol,
            timeframe=timeframe,
            lookback_bars=lookback_bars or minimum_lookback,
        )
        raw_frame = await market_data_service.fetch_dataframe(request)
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
            "symbol": symbol,
            "timeframe": timeframe,
            "leakage_check": leakage_check.model_dump(mode="json"),
            "backtest": backtest_result.model_dump(mode="json"),
            "walk_forward": walk_forward_result.model_dump(mode="json"),
        }

    @app.get("/portfolio")
    async def portfolio() -> dict:
        view = portfolio_service.mark_to_market({})
        return view.model_dump(mode="json")

    @app.get("/alerts")
    async def alerts(limit: int = 20) -> dict:
        records = [record.model_dump(mode="json") for record in alert_service.list_recent(limit=limit)]
        return {"alerts": records}

    @app.post("/paper/cycles/{symbol}")
    async def run_paper_cycle(
        symbol: str,
        timeframe: str | None = None,
        lookback_bars: int | None = None,
    ) -> dict:
        cycle = await paper_trading_service.run_cycle(
            symbol=symbol,
            timeframe=timeframe or settings.paper_trading.default_cycle_timeframe,
            lookback_bars=lookback_bars or settings.paper_trading.default_lookback_bars,
        )
        return cycle.model_dump(mode="json")

    @app.post("/orders/paper")
    async def paper_order(payload: dict) -> dict:
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
        return report.model_dump(mode="json")

    return app
