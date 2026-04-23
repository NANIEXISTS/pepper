from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from dynaconf import Dynaconf
from pydantic import BaseModel, ConfigDict, Field

from .core.enums import OrderType, TradingMode


class ApiSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)


class ExchangeSettings(BaseModel):
    exchange_id: str = "binance"
    sandbox: bool = True
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    api_password: Optional[str] = None


class DataSettings(BaseModel):
    provider: str = "router"
    provider_routing: list[str] = Field(default_factory=lambda: ["ccxt", "yahoo"])
    base_url: str = "https://query1.finance.yahoo.com"
    request_timeout_seconds: float = Field(default=10.0, gt=0.0)
    supported_timeframes: list[str] = Field(default_factory=lambda: ["5m", "15m", "1h", "4h", "1d"])
    default_lookback_bars: int = Field(default=500, ge=50, le=5000)
    ccxt_quote_fallbacks: list[str] = Field(default_factory=lambda: ["USDT", "USDC", "FDUSD", "BUSD"])
    cache_max_staleness_seconds: int = Field(default=900, ge=60, le=86_400)
    provider_max_retries: int = Field(default=1, ge=0, le=5)
    retry_backoff_seconds: float = Field(default=0.5, ge=0.0, le=30.0)


class RiskSettings(BaseModel):
    max_per_trade_risk_fraction: float = Field(default=0.01, gt=0.0, le=0.05)
    max_daily_drawdown_fraction: float = Field(default=0.05, gt=0.0, le=0.25)
    max_positions: int = Field(default=10, ge=1, le=100)
    stop_loss_required: bool = True


class ExecutionSettings(BaseModel):
    default_order_type: OrderType = OrderType.LIMIT
    market_fallback_seconds: int = Field(default=3, ge=1, le=120)
    live_trading_enabled: bool = False


class PaperTradingSettings(BaseModel):
    starting_cash: float = Field(default=100_000.0, gt=0.0)
    default_cycle_timeframe: str = "1h"
    default_lookback_bars: int = Field(default=600, ge=100, le=5000)
    signal_confidence_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    schedule_interval_seconds: int = Field(default=300, ge=60, le=86_400)


class LlmSettings(BaseModel):
    provider: str = "disabled"
    model: str = "openai/gpt-5-mini"
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)


class ReinforcementSettings(BaseModel):
    enabled: bool = False
    inventory_fraction_limit: float = Field(default=0.25, gt=0.0, le=1.0)
    episode_length: int = Field(default=24, ge=2, le=500)
    max_slippage_bps: float = Field(default=15.0, ge=0.0, le=100.0)


class BacktestingSettings(BaseModel):
    initial_capital: float = Field(default=100_000.0, gt=0.0)
    transaction_fee_bps: float = Field(default=10.0, ge=0.0, le=100.0)
    slippage_bps: float = Field(default=2.0, ge=0.0, le=100.0)
    short_window: int = Field(default=20, ge=2, le=200)
    long_window: int = Field(default=50, ge=3, le=400)
    trend_filter_window: int = Field(default=200, ge=20, le=800)
    train_bars: int = Field(default=240, ge=50, le=10_000)
    test_bars: int = Field(default=80, ge=20, le=5_000)
    max_walk_forward_windows: int = Field(default=4, ge=1, le=20)


class PersistenceSettings(BaseModel):
    database_url: str = "sqlite+aiosqlite:///./trading_ai.db"


class LoggingSettings(BaseModel):
    level: str = "INFO"
    json_output: bool = True


class OperatorAccountSettings(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    role: Literal["viewer", "trader", "admin"] = "viewer"


class AuthSettings(BaseModel):
    enabled: bool = False
    realm: str = "Pepper Operator Console"
    operators: list[OperatorAccountSettings] = Field(default_factory=list)


class TradingSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    app_name: str = "Trading AI"
    app_mode: TradingMode = TradingMode.PAPER
    default_symbol: str = "BTC-USD"
    api: ApiSettings = Field(default_factory=ApiSettings)
    exchange: ExchangeSettings = Field(default_factory=ExchangeSettings)
    data: DataSettings = Field(default_factory=DataSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    paper_trading: PaperTradingSettings = Field(default_factory=PaperTradingSettings)
    llm: LlmSettings = Field(default_factory=LlmSettings)
    reinforcement: ReinforcementSettings = Field(default_factory=ReinforcementSettings)
    backtesting: BacktestingSettings = Field(default_factory=BacktestingSettings)
    persistence: PersistenceSettings = Field(default_factory=PersistenceSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)


def _settings_source() -> Dynaconf:
    root = Path(__file__).resolve().parent.parent
    return Dynaconf(
        envvar_prefix="TRADING_AI",
        settings_files=[str(root / "config.yaml")],
        load_dotenv=True,
        environments=False,
        merge_enabled=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> TradingSettings:
    raw_settings = _settings_source().as_dict()
    return TradingSettings.model_validate(raw_settings)
