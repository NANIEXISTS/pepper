from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import trading_ai.data.providers.alpaca as alpaca_provider_module
import trading_ai.data.providers.ccxt as ccxt_provider_module
from trading_ai.core.models import MarketBar, MarketDataRequest
from trading_ai.data import MarketDataService, MarketDataUnavailableError
from trading_ai.data.providers import AlpacaMarketDataProvider, CcxtMarketDataProvider, RoutingMarketDataProvider
from trading_ai.settings import AlpacaSettings, DataSettings, ExchangeSettings


def _bar(*, timestamp: datetime, open_: float, high: float, low: float, close: float, volume: float) -> MarketBar:
    return MarketBar(
        symbol="BTC-USD",
        timeframe="1h",
        timestamp=timestamp,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


class _FailingProvider:
    name = "primary"

    async def fetch_ohlcv(self, request: MarketDataRequest) -> list[MarketBar]:  # noqa: ARG002
        raise RuntimeError("provider offline")


class _SuccessfulProvider:
    name = "secondary"

    async def fetch_ohlcv(self, request: MarketDataRequest) -> list[MarketBar]:  # noqa: ARG002
        return [
            _bar(
                timestamp=datetime(2025, 1, 1, 1, tzinfo=UTC),
                open_=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1_000.0,
            )
        ]


class _InvalidCandleProvider:
    name = "invalid"

    async def fetch_ohlcv(self, request: MarketDataRequest) -> list[MarketBar]:  # noqa: ARG002
        return [
            _bar(
                timestamp=datetime(2025, 1, 1, 1, tzinfo=UTC),
                open_=100.0,
                high=100.2,
                low=100.4,
                close=100.5,
                volume=1_000.0,
            )
        ]


class _HourlyProvider:
    name = "hourly"

    async def fetch_ohlcv(self, request: MarketDataRequest) -> list[MarketBar]:  # noqa: ARG002
        start = datetime(2025, 1, 1, 1, tzinfo=UTC)
        bars: list[MarketBar] = []
        for offset in range(8):
            price = 100.0 + offset
            bars.append(
                _bar(
                    timestamp=start + timedelta(hours=offset),
                    open_=price,
                    high=price + 1.0,
                    low=price - 1.0,
                    close=price + 0.5,
                    volume=1_000.0 + offset,
                )
            )
        return bars


class _FlakyProvider:
    name = "flaky"

    def __init__(self) -> None:
        self.calls = 0

    async def fetch_ohlcv(self, request: MarketDataRequest) -> list[MarketBar]:  # noqa: ARG002
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("transient upstream failure")
        return [
            _bar(
                timestamp=datetime(2025, 1, 1, 1, tzinfo=UTC),
                open_=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1_000.0,
            )
        ]


@pytest.mark.asyncio
async def test_routing_provider_falls_back_to_next_provider() -> None:
    provider = RoutingMarketDataProvider([_FailingProvider(), _SuccessfulProvider()])

    bars = await provider.fetch_ohlcv(MarketDataRequest(symbol="BTC-USD", timeframe="1h", lookback_bars=50))

    assert len(bars) == 1
    assert bars[0].close == 100.5


@pytest.mark.asyncio
async def test_market_data_service_rejects_invalid_candles() -> None:
    service = MarketDataService(_InvalidCandleProvider())

    with pytest.raises(MarketDataUnavailableError, match="traded prices"):
        await service.fetch_dataframe(MarketDataRequest(symbol="BTC-USD", timeframe="1h", lookback_bars=50))


@pytest.mark.asyncio
async def test_market_data_service_resamples_hourly_to_4h() -> None:
    service = MarketDataService(_HourlyProvider())

    frame = await service.fetch_dataframe(MarketDataRequest(symbol="BTC-USD", timeframe="4h", lookback_bars=50))

    assert len(frame) == 2
    assert set(frame["timeframe"]) == {"4h"}
    assert frame.attrs["source_timeframe"] == "1h"


@pytest.mark.asyncio
async def test_market_data_service_uses_cached_snapshot_when_provider_fails() -> None:
    provider = _FlakyProvider()
    service = MarketDataService(provider, cache_max_staleness_seconds=3600)
    request = MarketDataRequest(symbol="BTC-USD", timeframe="1h", lookback_bars=50)

    fresh = await service.fetch_dataframe(request)
    stale = await service.fetch_dataframe(request)

    assert fresh.attrs["stale"] is False
    assert stale.attrs["stale"] is True
    assert stale.attrs["cache_age_seconds"] >= 0.0
    assert stale.attrs["provider_failures"]


@pytest.mark.asyncio
async def test_market_data_service_raises_when_no_cache_exists() -> None:
    service = MarketDataService(_FailingProvider(), cache_max_staleness_seconds=3600)

    with pytest.raises(MarketDataUnavailableError, match="Market data unavailable"):
        await service.fetch_dataframe(MarketDataRequest(symbol="BTC-USD", timeframe="1h", lookback_bars=50))


class _FakeCcxtExchange:
    id = "binance"

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}
        self.has = {"fetchOHLCV": True}
        self.timeframes = {"1h": "1h", "4h": "4h"}
        self.symbols = ["BTC/USDT", "ETH/USDT"]
        self.fetch_calls: list[dict] = []

    async def load_markets(self) -> None:
        return None

    def parse_timeframe(self, timeframe: str) -> int:
        mapping = {"1h": 3600, "4h": 14400}
        return mapping[timeframe]

    def milliseconds(self) -> int:
        return int(datetime(2025, 1, 2, tzinfo=UTC).timestamp() * 1000)

    async def fetch_ohlcv(self, symbol: str, timeframe: str, since: int | None = None, limit: int | None = None) -> list[list[float]]:
        self.fetch_calls.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "since": since,
                "limit": limit,
            }
        )
        start = datetime(2025, 1, 1, tzinfo=UTC)
        rows: list[list[float]] = []
        for offset in range(limit or 0):
            timestamp = int((start + timedelta(hours=offset)).timestamp() * 1000)
            price = 100.0 + offset
            rows.append([timestamp, price, price + 1.0, price - 1.0, price + 0.5, 1_000.0 + offset])
        return rows

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_ccxt_provider_resolves_symbol_and_fetches_ohlcv(monkeypatch) -> None:
    created: list[_FakeCcxtExchange] = []

    def _factory(config: dict | None = None) -> _FakeCcxtExchange:
        exchange = _FakeCcxtExchange(config)
        created.append(exchange)
        return exchange

    monkeypatch.setattr(ccxt_provider_module.ccxt_async, "binance", _factory)
    provider = CcxtMarketDataProvider(
        data_settings=DataSettings(ccxt_quote_fallbacks=["USDT"]),
        exchange_settings=ExchangeSettings(exchange_id="binance"),
    )

    bars = await provider.fetch_ohlcv(MarketDataRequest(symbol="BTC-USD", timeframe="1h", lookback_bars=60))

    assert len(bars) == 60
    assert bars[-1].symbol == "BTC-USD"
    assert created[0].fetch_calls[0]["symbol"] == "BTC/USDT"
    assert created[0].fetch_calls[0]["timeframe"] == "1h"


@pytest.mark.asyncio
async def test_ccxt_provider_rejects_missing_fetch_ohlcv_capability(monkeypatch) -> None:
    class _NoOhlcvExchange(_FakeCcxtExchange):
        def __init__(self, config: dict | None = None) -> None:
            super().__init__(config)
            self.has = {"fetchOHLCV": False}

    monkeypatch.setattr(ccxt_provider_module.ccxt_async, "binance", _NoOhlcvExchange)
    provider = CcxtMarketDataProvider(
        data_settings=DataSettings(),
        exchange_settings=ExchangeSettings(exchange_id="binance"),
    )

    with pytest.raises(RuntimeError, match="fetchOHLCV support"):
        await provider.fetch_ohlcv(MarketDataRequest(symbol="BTC-USD", timeframe="1h", lookback_bars=60))


class _FakeAlpacaResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.status_code = 200
        self.text = ""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class _FakeAlpacaClient:
    def __init__(self, *, recorder: list[dict], payload: dict, timeout: float) -> None:
        self.recorder = recorder
        self.payload = payload
        self.timeout = timeout

    async def __aenter__(self) -> "_FakeAlpacaClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    async def get(self, url: str, params: dict | None = None, headers: dict | None = None) -> _FakeAlpacaResponse:
        self.recorder.append({"url": url, "params": params or {}, "headers": headers or {}})
        return _FakeAlpacaResponse(self.payload)


@pytest.mark.asyncio
async def test_alpaca_provider_fetches_stock_bars_with_auth(monkeypatch) -> None:
    recorder: list[dict] = []

    def _factory(*, timeout: float) -> _FakeAlpacaClient:
        return _FakeAlpacaClient(
            recorder=recorder,
            payload={
                "bars": {
                    "AAPL": [
                        {"t": "2025-01-01T15:00:00Z", "o": 189.0, "h": 190.0, "l": 188.5, "c": 189.5, "v": 1200.0}
                    ]
                }
            },
            timeout=timeout,
        )

    monkeypatch.setattr(alpaca_provider_module.httpx, "AsyncClient", _factory)
    provider = AlpacaMarketDataProvider(
        data_settings=DataSettings(request_timeout_seconds=5.0),
        alpaca_settings=AlpacaSettings(api_key="key", api_secret="secret"),
    )

    bars = await provider.fetch_ohlcv(MarketDataRequest(symbol="AAPL", timeframe="1h", lookback_bars=60))

    assert len(bars) == 1
    assert bars[0].symbol == "AAPL"
    assert recorder[0]["params"]["feed"] == "iex"
    assert recorder[0]["headers"]["APCA-API-KEY-ID"] == "key"


@pytest.mark.asyncio
async def test_alpaca_provider_fetches_crypto_bars_without_auth(monkeypatch) -> None:
    recorder: list[dict] = []

    def _factory(*, timeout: float) -> _FakeAlpacaClient:
        return _FakeAlpacaClient(
            recorder=recorder,
            payload={
                "bars": {
                    "BTC/USD": [
                        {"t": "2025-01-01T15:00:00Z", "o": 100000.0, "h": 100500.0, "l": 99500.0, "c": 100200.0, "v": 42.0}
                    ]
                }
            },
            timeout=timeout,
        )

    monkeypatch.setattr(alpaca_provider_module.httpx, "AsyncClient", _factory)
    provider = AlpacaMarketDataProvider(
        data_settings=DataSettings(request_timeout_seconds=5.0),
        alpaca_settings=AlpacaSettings(),
    )

    bars = await provider.fetch_ohlcv(MarketDataRequest(symbol="BTC-USD", timeframe="1h", lookback_bars=60))

    assert len(bars) == 1
    assert bars[0].symbol == "BTC-USD"
    assert "/v1beta3/crypto/us/bars" in recorder[0]["url"]
    assert recorder[0]["params"]["symbols"] == "BTC/USD"
    assert recorder[0]["headers"] == {}
