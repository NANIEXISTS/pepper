from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from trading_ai.api.app import create_app
from trading_ai.market_context import PolymarketHypeService
from trading_ai.settings import (
    BacktestingSettings,
    ExecutionSettings,
    LoggingSettings,
    PersistenceSettings,
    TradingSettings,
    TradingMode,
)


class FakePolymarketHypeService(PolymarketHypeService):
    async def fetch_hype(self, *, symbol: str | None = None, limit: int = 12, scan_limit: int = 100):  # noqa: ANN001
        return self.build_report(
            [
                {
                    "title": "When will Bitcoin hit $150k?",
                    "slug": "when-will-bitcoin-hit-150k",
                    "volume24hr": 1_000_000,
                    "volume": 10_000_000,
                    "liquidity": 50_000,
                    "tags": [{"label": "Bitcoin"}],
                }
            ],
            symbol=symbol,
            limit=limit,
        )

    async def fetch_terminal(self, *, symbol: str | None = None, limit: int = 8, scan_limit: int = 100):  # noqa: ANN001
        return self.build_terminal(
            [
                {
                    "title": "When will Bitcoin hit $150k?",
                    "slug": "when-will-bitcoin-hit-150k",
                    "description": "Primary source is BTC/USD exchange pricing and credible reporting.",
                    "volume24hr": 1_000_000,
                    "volume": 10_000_000,
                    "liquidity": 50_000,
                    "tags": [{"label": "Bitcoin"}],
                    "markets": [
                        {
                            "active": True,
                            "closed": False,
                            "acceptingOrders": True,
                            "enableOrderBook": True,
                            "outcomes": '["Yes","No"]',
                            "outcomePrices": '["0.42","0.58"]',
                            "clobTokenIds": '["111","222"]',
                            "bestBid": 0.41,
                            "bestAsk": 0.43,
                            "spread": 0.02,
                        }
                    ],
                }
            ],
            leaderboard=[{"rank": "1", "proxyWallet": "0xabc", "userName": "top_trader", "pnl": 1000, "vol": 5000}],
            trades=[
                {
                    "proxyWallet": "0xabc",
                    "side": "BUY",
                    "title": "When will Bitcoin hit $150k?",
                    "slug": "when-will-bitcoin-hit-150k",
                    "outcome": "Yes",
                    "size": 50,
                    "price": 0.42,
                    "timestamp": 1_778_600_000,
                }
            ],
            kalshi_events={
                "events": [
                    {
                        "title": "Will Bitcoin reach 150k?",
                        "event_ticker": "KXBTC150",
                        "markets": [
                            {
                                "ticker": "KXBTC150-26",
                                "status": "active",
                                "yes_bid_dollars": "0.35",
                                "yes_ask_dollars": "0.37",
                            }
                        ],
                    }
                ]
            },
            books_by_token={"111": {"bids": [{"price": "0.41", "size": "500"}], "asks": [{"price": "0.43", "size": "600"}]}},
            symbol=symbol,
            limit=limit,
        )


def _market_frame(rows: int = 600) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=rows, freq="1h", tz="UTC")
    close = [100 + (i * 0.03) + (5 * math.sin(i / 12)) for i in range(rows)]
    frame = pd.DataFrame(
        {
            "symbol": ["BTC-USD"] * rows,
            "timeframe": ["1h"] * rows,
            "open": [price - 0.2 for price in close],
            "high": [price + 0.4 for price in close],
            "low": [price - 0.6 for price in close],
            "close": close,
            "volume": [1000 + (i % 15) * 50 for i in range(rows)],
        },
        index=index,
    )
    frame.index.name = "timestamp"
    return frame


def test_dashboard_route_serves_html(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module
    from trading_ai.data.service import MarketDataService

    settings = TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'dashboard.db').as_posix()}"),
        execution=ExecutionSettings(),
        backtesting=BacktestingSettings(train_bars=200, test_bars=80, max_walk_forward_windows=3),
        logging=LoggingSettings(level="INFO"),
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    monkeypatch.setattr(app_module, "PolymarketHypeService", FakePolymarketHypeService)

    async def fake_fetch_dataframe(self, request):  # noqa: ANN001
        return _market_frame(request.lookback_bars)

    monkeypatch.setattr(MarketDataService, "fetch_dataframe", fake_fetch_dataframe)

    with TestClient(create_app()) as client:
        response = client.get("/dashboard")

    assert response.status_code == 200
    assert "Pepper Trading Cockpit" in response.text
    assert "Trading Cockpit" in response.text
    assert "5-Min Buy/Sell Test" in response.text
    assert "Run 1h Hunter" in response.text
    assert "One-Click Edge Scan" in response.text
    assert "Prediction Market Deep Dive" in response.text
    assert "Whales, Rules, Books, Arb" in response.text
    assert "Client Brief" in response.text
    assert "Not ready for live capital" in response.text
    assert "Run Drawdown Self-Test" in response.text
    assert response.headers["content-type"].startswith("text/html")


def test_dashboard_data_route_returns_overview(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module
    from trading_ai.data.service import MarketDataService

    settings = TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'dashboard-overview.db').as_posix()}"),
        execution=ExecutionSettings(),
        backtesting=BacktestingSettings(train_bars=200, test_bars=80, max_walk_forward_windows=3),
        logging=LoggingSettings(level="INFO"),
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    monkeypatch.setattr(app_module, "PolymarketHypeService", FakePolymarketHypeService)

    async def fake_fetch_dataframe(self, request):  # noqa: ANN001
        return _market_frame(max(request.lookback_bars, 600))

    monkeypatch.setattr(MarketDataService, "fetch_dataframe", fake_fetch_dataframe)

    with TestClient(create_app()) as client:
        response = client.get("/dashboard/data?symbol=BTC-USD&timeframe=1h")

    assert response.status_code == 200
    payload = response.json()
    assert payload["config"]["mode"] == "paper"
    assert payload["market"]["symbol"] == "BTC-USD"
    assert len(payload["market"]["recent_bars"]) == 80
    assert "jobs" in payload
    assert "runs" in payload
    assert "trade_audit" in payload
    assert "venues" in payload
    assert "live_readiness" in payload
    assert "portfolio_breakdown" in payload
    assert "profit_path" in payload
    assert payload["market_context"]["polymarket_hype"]["requested_symbol"] == "BTC-USD"
    assert payload["market_context"]["polymarket_hype"]["direct_event_count"] == 1
    assert payload["market_context"]["prediction_terminal"]["wallets"]["leaderboard"][0]["user_name"] == "top_trader"
    assert payload["market_context"]["prediction_terminal"]["microstructure"]["items"]
    assert payload["market_context"]["prediction_terminal"]["cross_venue"]["candidates"]
    assert payload["market_context"]["prediction_terminal_history"]["delta"]["available"] is False
    assert payload["market_context"]["profit_hunter"]["mode"] == "paper"
    assert payload["market_context"]["profit_hunter"]["verdict"] in {"TRADE", "NO_TRADE", "INSUFFICIENT_EDGE"}
    assert "strategy_builder" in payload
    assert payload["profit_path"]["risk_size_preview"]["quantity"] >= 0
    assert payload["profit_path"]["edge"]["leakage_check_passed"] is True
    assert payload["profit_path"]["edge"]["walk_forward_window_count"] >= 0
    assert payload["profit_path"]["paper_profitability"]["required_days"] == 14
    assert "practically help profits" in payload["profit_path"]["plain_english"]
    assert payload["live_readiness"]["live_capital_allowed"] is False
    assert "fourteen_day_profitability" in payload["live_readiness"]
    assert "blocking_reasons" in payload["live_readiness"]
    assert payload["backtest"]["leakage_check"]["passed"] is True
    assert "equity_curve" in payload["backtest"]
    assert "walk_forward_windows" in payload["backtest"]
    assert "trades" in payload["backtest"]
