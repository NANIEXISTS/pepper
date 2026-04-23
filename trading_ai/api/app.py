from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import pandas as pd

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
from ..orchestration import PaperCycleJobCreate, PaperTradingScheduler, build_default_paper_trading_service
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
    paper_scheduler = PaperTradingScheduler(
        paper_trading_service=paper_trading_service,
        audit_store=audit_store,
        alert_service=alert_service,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await audit_store.create_schema()
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

    dashboard_dir = Path(__file__).resolve().parent.parent / "dashboard"
    app.mount("/assets", StaticFiles(directory=dashboard_dir), name="dashboard-assets")

    def _backtest_lookback_bars() -> int:
        return max(
            settings.data.default_lookback_bars,
            settings.backtesting.train_bars + (settings.backtesting.test_bars * settings.backtesting.max_walk_forward_windows),
            settings.backtesting.trend_filter_window + 50,
        )

    async def _run_backtest_summary(symbol: str, timeframe: str, lookback_bars: int) -> dict:
        request = MarketDataRequest(symbol=symbol, timeframe=timeframe, lookback_bars=lookback_bars)
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
            "leakage_check": leakage_check.model_dump(mode="json"),
            "backtest": backtest_result.model_dump(mode="json"),
            "walk_forward": walk_forward_result.model_dump(mode="json"),
        }

    @app.get("/", include_in_schema=False)
    async def index() -> RedirectResponse:
        return RedirectResponse(url="/dashboard")

    @app.get("/dashboard", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(dashboard_dir / "index.html")

    @app.get("/dashboard/data")
    async def dashboard_data(
        symbol: str | None = None,
        timeframe: str | None = None,
        lookback_bars: int | None = None,
    ) -> dict:
        active_symbol = symbol or settings.default_symbol
        active_timeframe = timeframe or settings.paper_trading.default_cycle_timeframe
        request = MarketDataRequest(
            symbol=active_symbol,
            timeframe=active_timeframe,
            lookback_bars=lookback_bars or max(settings.paper_trading.default_lookback_bars, settings.data.default_lookback_bars),
        )
        market_frame = await market_data_service.fetch_dataframe(request)
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
        backtest_summary = await _run_backtest_summary(
            symbol=active_symbol,
            timeframe=active_timeframe,
            lookback_bars=max(request.lookback_bars, _backtest_lookback_bars()),
        )

        return {
            "config": {
                "app_name": settings.app_name,
                "mode": settings.app_mode.value,
                "default_symbol": settings.default_symbol,
                "provider": settings.data.provider,
                "supported_timeframes": settings.data.supported_timeframes,
                "live_trading_enabled": settings.execution.live_trading_enabled,
            },
            "market": {
                "symbol": active_symbol,
                "timeframe": active_timeframe,
                "latest_timestamp": market_frame.index[-1].isoformat(),
                "latest_price": float(market_frame.iloc[-1]["close"]),
                "recent_bars": recent_market,
            },
            "features": latest_features,
            "portfolio": portfolio_service.mark_to_market({active_symbol: float(market_frame.iloc[-1]["close"])}).model_dump(mode="json"),
            "alerts": [record.model_dump(mode="json") for record in alert_service.list_recent(limit=8)],
            "jobs": [job.model_dump(mode="json") for job in await paper_scheduler.list_jobs()],
            "runs": [run.model_dump(mode="json") for run in await paper_scheduler.list_runs(limit=8)],
            "backtest": {
                "leakage_check": backtest_summary["leakage_check"],
                "metrics": backtest_summary["backtest"]["metrics"],
                "equity_curve": backtest_summary["backtest"]["equity_curve"][-80:],
                "walk_forward_summary": backtest_summary["walk_forward"]["summary"],
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
        minimum_lookback = _backtest_lookback_bars()
        result = await _run_backtest_summary(
            symbol=symbol,
            timeframe=timeframe,
            lookback_bars=lookback_bars or minimum_lookback,
        )
        return {"symbol": symbol, "timeframe": timeframe, **result}

    @app.get("/portfolio")
    async def portfolio() -> dict:
        view = portfolio_service.mark_to_market({})
        return view.model_dump(mode="json")

    @app.get("/alerts")
    async def alerts(limit: int = 20) -> dict:
        records = [record.model_dump(mode="json") for record in alert_service.list_recent(limit=limit)]
        return {"alerts": records}

    @app.get("/paper/jobs")
    async def paper_jobs() -> dict:
        jobs = [job.model_dump(mode="json") for job in await paper_scheduler.list_jobs()]
        return {"jobs": jobs}

    @app.post("/paper/jobs")
    async def create_paper_job(payload: PaperCycleJobCreate) -> dict:
        job = await paper_scheduler.create_job(payload)
        return {"job": job.model_dump(mode="json")}

    @app.post("/paper/jobs/{job_id}/start")
    async def start_paper_job(job_id: int) -> dict:
        job = await paper_scheduler.start_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Paper cycle job {job_id} not found.")
        return {"job": job.model_dump(mode="json")}

    @app.post("/paper/jobs/{job_id}/pause")
    async def pause_paper_job(job_id: int) -> dict:
        job = await paper_scheduler.pause_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Paper cycle job {job_id} not found.")
        return {"job": job.model_dump(mode="json")}

    @app.post("/paper/jobs/{job_id}/run")
    async def run_paper_job_once(job_id: int) -> dict:
        try:
            cycle = await paper_scheduler.run_job_once(job_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return cycle.model_dump(mode="json")

    @app.get("/paper/runs")
    async def paper_runs(limit: int = 20, job_id: int | None = None) -> dict:
        runs = [run.model_dump(mode="json") for run in await paper_scheduler.list_runs(limit=limit, job_id=job_id)]
        return {"runs": runs}

    @app.post("/paper/cycles/{symbol}")
    async def run_paper_cycle(
        symbol: str,
        timeframe: str | None = None,
        lookback_bars: int | None = None,
    ) -> dict:
        try:
            cycle = await paper_scheduler.run_ad_hoc_cycle(
                symbol=symbol,
                timeframe=timeframe or settings.paper_trading.default_cycle_timeframe,
                lookback_bars=lookback_bars or settings.paper_trading.default_lookback_bars,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
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
