from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from trading_ai.api.app import create_app
from trading_ai.market_context import PolymarketHypeService
from trading_ai.settings import LoggingSettings, PersistenceSettings, TradingMode, TradingSettings


class FakePolymarketHypeService(PolymarketHypeService):
    async def fetch_hype(self, *, symbol: str | None = None, limit: int = 12, scan_limit: int = 100):  # noqa: ANN001
        return self.build_report(
            [
                {
                    "title": "MicroStrategy sells any Bitcoin by ___ ?",
                    "slug": "microstrategy-sell-any-bitcoin-in-2025",
                    "volume24hr": 250_000,
                    "volume": 25_000_000,
                    "liquidity": 150_000,
                    "tags": [{"label": "MicroStrategy"}, {"label": "Crypto"}],
                },
                {
                    "title": "2026 NBA Champion",
                    "slug": "2026-nba-champion",
                    "volume24hr": 1_300_000,
                    "volume": 380_000_000,
                    "liquidity": 1_800_000,
                    "tags": [{"label": "Sports"}],
                },
            ],
            symbol=symbol,
            limit=limit,
        )

    async def fetch_terminal(self, *, symbol: str | None = None, limit: int = 8, scan_limit: int = 100):  # noqa: ANN001
        return self.build_terminal(
            [
                {
                    "title": "MicroStrategy sells any Bitcoin by ___ ?",
                    "slug": "microstrategy-sell-any-bitcoin-in-2025",
                    "description": "Primary sources are MSTR filings, on-chain data, and credible reporting.",
                    "volume24hr": 250_000,
                    "volume": 25_000_000,
                    "liquidity": 150_000,
                    "tags": [{"label": "MicroStrategy"}, {"label": "Crypto"}],
                    "markets": [
                        {
                            "active": True,
                            "closed": False,
                            "acceptingOrders": True,
                            "enableOrderBook": True,
                            "outcomes": '["Yes","No"]',
                            "outcomePrices": '["0.31","0.69"]',
                            "clobTokenIds": '["111","222"]',
                            "bestBid": 0.3,
                            "bestAsk": 0.32,
                            "spread": 0.02,
                        }
                    ],
                }
            ],
            leaderboard=[
                {
                    "rank": "1",
                    "proxyWallet": "0xabc",
                    "userName": "top_trader",
                    "pnl": 1000,
                    "vol": 5000,
                }
            ],
            trades=[
                {
                    "proxyWallet": "0xabc",
                    "side": "BUY",
                    "title": "MicroStrategy sells any Bitcoin by ___ ?",
                    "slug": "microstrategy-sell-any-bitcoin-in-2025",
                    "outcome": "Yes",
                    "size": 50,
                    "price": 0.31,
                    "timestamp": 1_778_600_000,
                }
            ],
            kalshi_events={
                "events": [
                    {
                        "title": "Will MicroStrategy sell Bitcoin?",
                        "event_ticker": "KXMSTRBTC",
                        "markets": [
                            {
                                "ticker": "KXMSTRBTC-26",
                                "status": "active",
                                "yes_bid_dollars": "0.25",
                                "yes_ask_dollars": "0.27",
                            }
                        ],
                    }
                ]
            },
            books_by_token={
                "111": {
                    "bids": [{"price": "0.30", "size": "500"}],
                    "asks": [{"price": "0.32", "size": "600"}],
                }
            },
            symbol=symbol,
            limit=limit,
        )


def test_polymarket_hype_endpoint_returns_read_only_context(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module

    settings = TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'context.db').as_posix()}"),
        logging=LoggingSettings(level="INFO"),
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    monkeypatch.setattr(app_module, "PolymarketHypeService", FakePolymarketHypeService)

    with TestClient(create_app()) as client:
        response = client.get("/market-context/polymarket/hype?symbol=BTC-USD&limit=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "polymarket_gamma"
    assert payload["requested_symbol"] == "BTC-USD"
    assert payload["events_scanned"] == 2
    assert payload["direct_event_count"] == 1
    assert "Do not trade automatically" in payload["safe_use"]
    assert payload["events"][0]["relevance"] == "direct"


def test_polymarket_hype_endpoint_rejects_invalid_limit(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module

    settings = TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'context-invalid.db').as_posix()}"),
        logging=LoggingSettings(level="INFO"),
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    monkeypatch.setattr(app_module, "PolymarketHypeService", FakePolymarketHypeService)

    with TestClient(create_app()) as client:
        response = client.get("/market-context/polymarket/hype?limit=100")

    assert response.status_code == 400


def test_polymarket_prediction_terminal_endpoint_returns_all_sections(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module

    settings = TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'terminal.db').as_posix()}"),
        logging=LoggingSettings(level="INFO"),
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    monkeypatch.setattr(app_module, "PolymarketHypeService", FakePolymarketHypeService)

    with TestClient(create_app()) as client:
        response = client.get("/market-context/polymarket/terminal?symbol=MSTR&limit=3")

    assert response.status_code == 200
    payload = response.json()
    assert payload["requested_symbol"] == "MSTR"
    assert payload["wallets"]["leaderboard"][0]["user_name"] == "top_trader"
    assert payload["wallets"]["whale_trades"][0]["signal"] == "copy_watch"
    assert payload["resolution"]["items"]
    assert payload["microstructure"]["items"]
    assert payload["cross_venue"]["candidates"]
    assert payload["source_monitor"]["items"]


def test_polymarket_profit_hunter_endpoint_returns_paper_verdict(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module

    settings = TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'hunter.db').as_posix()}"),
        logging=LoggingSettings(level="INFO"),
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    monkeypatch.setattr(app_module, "PolymarketHypeService", FakePolymarketHypeService)

    with TestClient(create_app()) as client:
        response = client.post(
            "/market-context/polymarket/hunter/run"
            "?symbol=MSTR&horizon_minutes=60&max_stake_usd=25&min_trade_score=0.72&limit=3&record_snapshot=true"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["report"]["mode"] == "paper"
    assert payload["report"]["verdict"] in {"TRADE", "NO_TRADE", "INSUFFICIENT_EDGE"}
    assert payload["report"]["candidate_count"] >= 1
    assert payload["report"]["max_stake_usd"] == 25
    assert payload["snapshot"]["symbol"] == "MSTR"


def test_polymarket_prediction_terminal_rejects_invalid_limit(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module

    settings = TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'terminal-invalid.db').as_posix()}"),
        logging=LoggingSettings(level="INFO"),
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    monkeypatch.setattr(app_module, "PolymarketHypeService", FakePolymarketHypeService)

    with TestClient(create_app()) as client:
        response = client.get("/market-context/polymarket/terminal?limit=50")

    assert response.status_code == 400
