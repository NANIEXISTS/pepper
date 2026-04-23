from __future__ import annotations

from abc import ABC, abstractmethod

from .models import AgentContext


class TradingAgent(ABC):
    @abstractmethod
    async def run(self, ctx: AgentContext):
        """Run the agent against the current context."""
