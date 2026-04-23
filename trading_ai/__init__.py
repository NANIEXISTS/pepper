"""Production-oriented backend foundation for a multi-asset AI trading system."""

from .api.app import create_app
from .execution import ExecutionEngine, LiveOrderRouter, PaperOrderRouter
from .risk import RiskAuditAgent
from .settings import TradingSettings, get_settings

__version__ = "0.3.1"

__all__ = [
    "ExecutionEngine",
    "LiveOrderRouter",
    "PaperOrderRouter",
    "RiskAuditAgent",
    "TradingSettings",
    "__version__",
    "create_app",
    "get_settings",
]
