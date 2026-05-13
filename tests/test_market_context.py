from __future__ import annotations

from trading_ai.market_context import PolymarketHypeService


def test_polymarket_hype_maps_crypto_and_macro_narratives() -> None:
    service = PolymarketHypeService()
    report = service.build_report(
        [
            {
                "title": "When will Bitcoin hit $150k?",
                "slug": "when-will-bitcoin-hit-150k",
                "volume24hr": 5_000_000,
                "volume": 20_000_000,
                "liquidity": 50_000,
                "tags": [{"label": "Bitcoin"}, {"label": "Crypto"}],
            },
            {
                "title": "Will China invade Taiwan by end of 2026?",
                "slug": "will-china-invade-taiwan-before-2027",
                "volume24hr": 300_000,
                "volume": 23_000_000,
                "liquidity": 900_000,
                "tags": [{"label": "Geopolitics"}],
            },
            {
                "title": "2026 FIFA World Cup Winner",
                "slug": "2026-fifa-world-cup-winner",
                "volume24hr": 8_000_000,
                "volume": 900_000_000,
                "liquidity": 200_000_000,
                "tags": [{"label": "Sports"}],
            },
        ],
        symbol="BTC-USD",
        limit=3,
    )

    assert report.events_scanned == 3
    assert report.direct_event_count >= 1
    assert "BTC-USD" in report.top_symbols
    assert report.events[0].title == "When will Bitcoin hit $150k?"
    assert report.events[0].relevance == "direct"
    assert "MSTR" in report.events[0].mapped_symbols
    assert any(event.relevance == "macro" for event in report.events)


def test_polymarket_hype_unavailable_report_is_safe() -> None:
    service = PolymarketHypeService()
    report = service.unavailable_report(symbol="BTC-USD", error="timeout")

    assert report.available is False
    assert report.events == []
    assert report.requested_symbol == "BTC-USD"
    assert "timeout" in report.warnings[0]


def test_prediction_terminal_builds_wallet_rules_books_arb_and_sources() -> None:
    service = PolymarketHypeService()
    token_id = "111"
    report = service.build_terminal(
        [
            {
                "title": "Will Bitcoin hit $150k in 2026?",
                "slug": "bitcoin-150k-2026",
                "description": (
                    "This market resolves Yes if Bitcoin trades above $150,000 before Dec 31, 2026. "
                    "The primary resolution source will be major exchange BTC/USD prices and credible reporting."
                ),
                "volume24hr": 2_000_000,
                "volume": 30_000_000,
                "liquidity": 1_000_000,
                "tags": [{"label": "Bitcoin"}],
                "markets": [
                    {
                        "active": True,
                        "closed": False,
                        "acceptingOrders": True,
                        "enableOrderBook": True,
                        "outcomes": '["Yes","No"]',
                        "outcomePrices": '["0.42","0.58"]',
                        "clobTokenIds": f'["{token_id}","222"]',
                        "bestBid": 0.41,
                        "bestAsk": 0.43,
                        "spread": 0.02,
                        "negRisk": True,
                    }
                ],
            }
        ],
        leaderboard=[
            {
                "rank": "1",
                "proxyWallet": "0xabc",
                "userName": "top_trader",
                "xUsername": "top",
                "pnl": 12345,
                "vol": 100000,
                "verifiedBadge": True,
            }
        ],
        trades=[
            {
                "proxyWallet": "0xabc",
                "side": "BUY",
                "title": "Will Bitcoin hit $150k in 2026?",
                "slug": "bitcoin-150k-2026",
                "outcome": "Yes",
                "size": 250,
                "price": 0.42,
                "timestamp": 1_778_600_000,
            }
        ],
        kalshi_events={
            "events": [
                {
                    "title": "Will Bitcoin reach 150k before 2026 ends?",
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
            token_id: {
                "bids": [{"price": "0.41", "size": "900"}, {"price": "0.40", "size": "700"}],
                "asks": [{"price": "0.43", "size": "800"}, {"price": "0.44", "size": "600"}],
                "neg_risk": True,
            }
        },
        symbol="BTC-USD",
        limit=4,
    )

    assert report.wallets.leaderboard[0].user_name == "top_trader"
    assert report.wallets.whale_trades[0].signal == "copy_watch"
    assert report.resolution.items[0].ambiguity_score > 0
    assert "credible_reporting_discretion" in report.resolution.items[0].risk_flags
    assert report.microstructure.items[0].negative_risk is True
    assert report.microstructure.items[0].fill_probability_score > 0
    assert report.cross_venue.candidates[0].kalshi_ticker == "KXBTC150-26"
    assert report.cross_venue.candidates[0].probability_gap is not None
    assert "Major exchange BTC/USD reference prices" in report.source_monitor.items[0].official_sources
