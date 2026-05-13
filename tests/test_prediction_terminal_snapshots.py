from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from trading_ai.api.app import create_app
from trading_ai.market_context import PolymarketHypeService
from trading_ai.settings import LoggingSettings, PersistenceSettings, TradingMode, TradingSettings


class ChangingTerminalService(PolymarketHypeService):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def fetch_hype(self, *, symbol: str | None = None, limit: int = 12, scan_limit: int = 100):  # noqa: ANN001
        return self.build_report(self._events(), symbol=symbol, limit=limit)

    async def fetch_terminal(self, *, symbol: str | None = None, limit: int = 8, scan_limit: int = 100):  # noqa: ANN001
        self.calls += 1
        return self.build_terminal(
            self._events(),
            leaderboard=[
                {
                    "rank": "1",
                    "proxyWallet": "0xabc",
                    "userName": "top_trader",
                    "pnl": 1_000 + (self.calls * 125),
                    "vol": 5_000 + (self.calls * 250),
                }
            ],
            trades=[
                {
                    "proxyWallet": "0xabc",
                    "side": "BUY",
                    "title": "Will Bitcoin hit $150k?",
                    "slug": "bitcoin-150k",
                    "outcome": "Yes",
                    "size": 50 + self.calls,
                    "price": 0.4 + (self.calls * 0.01),
                    "timestamp": 1_778_600_000 + self.calls,
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
            books_by_token={
                "111": {
                    "bids": [{"price": "0.41", "size": str(500 + self.calls)}],
                    "asks": [{"price": "0.43", "size": str(600 + self.calls)}],
                }
            },
            symbol=symbol,
            limit=limit,
        )

    def _events(self) -> list[dict]:
        return [
            {
                "title": "Will Bitcoin hit $150k?",
                "slug": "bitcoin-150k",
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
        ]


def test_prediction_terminal_snapshots_persist_and_report_deltas(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module

    settings = TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'snapshots.db').as_posix()}"),
        logging=LoggingSettings(level="INFO"),
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    monkeypatch.setattr(app_module, "PolymarketHypeService", ChangingTerminalService)

    with TestClient(create_app()) as client:
        first = client.post("/market-context/polymarket/terminal/snapshots?symbol=BTC-USD&limit=3")
        second = client.post("/market-context/polymarket/terminal/snapshots?symbol=BTC-USD&limit=3")
        history = client.get("/market-context/polymarket/terminal/snapshots?symbol=BTC-USD&limit=5")
        delta = client.get("/market-context/polymarket/terminal/delta?symbol=BTC-USD")

    assert first.status_code == 200
    assert first.json()["delta"]["available"] is False
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["delta"]["available"] is True
    assert second_payload["delta"]["summary"]["wallet_delta_count"] == 1
    assert second_payload["delta"]["wallet_deltas"][0]["pnl_change"] == 125
    assert second_payload["delta"]["summary"]["new_whale_trade_count"] == 1
    assert history.status_code == 200
    assert len(history.json()["snapshots"]) == 2
    assert delta.status_code == 200
    assert delta.json()["available"] is True
