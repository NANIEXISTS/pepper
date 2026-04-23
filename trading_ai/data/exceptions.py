from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MarketDataUnavailableError(RuntimeError):
    symbol: str
    timeframe: str
    failures: list[str] = field(default_factory=list)
    cached_available: bool = False
    cache_age_seconds: float | None = None

    def __post_init__(self) -> None:
        message = f"Market data unavailable for {self.symbol} {self.timeframe}."
        if self.failures:
            message = f"{message} Failures: {' | '.join(self.failures)}"
        if self.cached_available and self.cache_age_seconds is not None:
            message = f"{message} Last cache age: {self.cache_age_seconds:.1f}s."
        RuntimeError.__init__(self, message)
