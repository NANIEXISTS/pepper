from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from ..agents import AnalystAgent, BearAgent, BullAgent, DebateLayer, StrategyAgent, TraderAgent
from ..agents.models import AgentContext
from ..alerts import AlertService
from ..core.enums import OrderStatus, TradeSignal
from ..core.models import MarketDataRequest
from ..data.service import MarketDataService
from ..execution import ExecutionEngine
from ..features import FeatureEngineer
from ..portfolio import PortfolioService
from ..reinforcement import ExecutionTimingCoordinator
from ..settings import PaperTradingSettings, RiskSettings
from .models import PaperTradingCycleResult


@dataclass(slots=True)
class PaperTradingService:
    market_data: MarketDataService
    feature_engineer: FeatureEngineer
    execution_engine: ExecutionEngine
    portfolio_service: PortfolioService
    alert_service: AlertService
    analyst_agent: AnalystAgent
    strategy_agent: StrategyAgent
    trader_agent: TraderAgent
    debate_layer: DebateLayer
    paper_settings: PaperTradingSettings
    last_cycle: Optional[PaperTradingCycleResult] = None
    _symbol_locks: dict[str, asyncio.Lock] = field(default_factory=dict)

    async def run_cycle(self, symbol: str, timeframe: str, lookback_bars: int) -> PaperTradingCycleResult:
        lock = self._symbol_locks.setdefault(symbol, asyncio.Lock())
        if lock.locked():
            raise RuntimeError(f"Paper cycle already running for {symbol}.")

        async with lock:
            request = MarketDataRequest(symbol=symbol, timeframe=timeframe, lookback_bars=lookback_bars)
            frame = await self.market_data.fetch_dataframe(request)
            if frame.attrs.get("stale", False):
                cache_age_seconds = float(frame.attrs.get("cache_age_seconds", 0.0))
                raise RuntimeError(
                    f"Paper cycle requires fresh market data for {symbol} {timeframe}. "
                    f"Last good snapshot age: {cache_age_seconds:.1f}s."
                )
            enriched = self.feature_engineer.enrich(frame)
            latest_price = float(enriched.iloc[-1]["close"])
            price_map = await self._price_map_for_cycle(symbol=symbol, timeframe=timeframe, latest_price=latest_price)
            portfolio_view = self.portfolio_service.mark_to_market(price_map)

            context = AgentContext(
                symbol=symbol,
                timeframe=timeframe,
                market_frame=frame,
                features=enriched,
                portfolio_equity=portfolio_view.equity,
                available_cash=portfolio_view.cash,
                positions=portfolio_view.positions,
                metadata={"latest_price": latest_price},
            )
            analysis = await self.analyst_agent.run(context)
            debate = await self.debate_layer.run(context, analysis)
            strategy = await self.strategy_agent.run(context, analysis, debate)
            order = await self.trader_agent.run(context, strategy)

            report = None
            if order is not None:
                report = await self.execution_engine.place_order(
                    agent_name="trader-agent",
                    signal=strategy.signal,
                    confidence=strategy.confidence,
                    rationale=strategy.rationale,
                    order=order,
                    portfolio=self.portfolio_service.snapshot(price_map),
                    metadata={
                        **strategy.metadata,
                        **order.metadata,
                        "analysis_confidence": analysis.confidence,
                    },
                )
                if report.status == OrderStatus.FILLED:
                    self.portfolio_service.apply_fill(order, report)

            updated_portfolio = self.portfolio_service.mark_to_market(price_map)
            alert_level = "info"
            alert_message = "No trade executed."
            if report is not None and report.status == OrderStatus.FILLED:
                alert_message = f"Paper trade filled for {symbol}."
            elif report is not None and report.status == OrderStatus.REJECTED:
                alert_level = "warning"
                alert_message = f"Trade rejected for {symbol}."

            alert = self.alert_service.emit(
                alert_level,
                alert_message,
                symbol=symbol,
                signal=strategy.signal.value,
                confidence=strategy.confidence,
                execution_status=report.status.value if report is not None else "none",
            )

            result = PaperTradingCycleResult(
                symbol=symbol,
                timeframe=timeframe,
                latest_price=latest_price,
                portfolio=updated_portfolio,
                analysis=analysis,
                debate=debate,
                strategy=strategy,
                execution_report=report,
                alert=alert,
                metadata={
                    "trade_executed": report is not None and report.status == OrderStatus.FILLED,
                    "trade_rejected": report is not None and report.status == OrderStatus.REJECTED,
                },
            )
            self.last_cycle = result
            return result

    async def _price_map_for_cycle(self, *, symbol: str, timeframe: str, latest_price: float) -> dict[str, float]:
        tracked_symbols = {symbol, *self.portfolio_service.positions.keys()}
        price_map: dict[str, float] = {symbol: latest_price}
        fetch_tasks: list[tuple[str, asyncio.Task]] = []

        for tracked_symbol in tracked_symbols:
            if tracked_symbol == symbol:
                continue
            request = MarketDataRequest(
                symbol=tracked_symbol,
                timeframe=timeframe,
                lookback_bars=50,
            )
            fetch_tasks.append((tracked_symbol, asyncio.create_task(self.market_data.fetch_dataframe(request))))

        for tracked_symbol, task in fetch_tasks:
            try:
                frame = await task
            except Exception:
                continue
            if frame.attrs.get("stale", False):
                continue
            price_map[tracked_symbol] = float(frame.iloc[-1]["close"])

        return price_map


def build_default_paper_trading_service(
    *,
    market_data: MarketDataService,
    feature_engineer: FeatureEngineer,
    execution_engine: ExecutionEngine,
    portfolio_service: PortfolioService,
    alert_service: AlertService,
    llm_client,
    paper_settings: PaperTradingSettings,
    risk_settings: RiskSettings,
    execution_timing: ExecutionTimingCoordinator,
) -> PaperTradingService:
    analyst_agent = AnalystAgent(llm_client=llm_client)
    strategy_agent = StrategyAgent()
    trader_agent = TraderAgent(
        risk_settings=risk_settings,
        paper_settings=paper_settings,
        execution_timing=execution_timing,
    )
    debate_layer = DebateLayer(bull_agent=BullAgent(), bear_agent=BearAgent())
    return PaperTradingService(
        market_data=market_data,
        feature_engineer=feature_engineer,
        execution_engine=execution_engine,
        portfolio_service=portfolio_service,
        alert_service=alert_service,
        analyst_agent=analyst_agent,
        strategy_agent=strategy_agent,
        trader_agent=trader_agent,
        debate_layer=debate_layer,
        paper_settings=paper_settings,
    )
