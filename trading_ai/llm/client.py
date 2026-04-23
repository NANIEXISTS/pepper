from __future__ import annotations

from dataclasses import dataclass

from openai import AsyncOpenAI

from ..settings import LlmSettings


@dataclass(slots=True)
class LLMResponse:
    content: str
    provider: str
    model: str
    used_live_model: bool


@dataclass(slots=True)
class LLMClient:
    settings: LlmSettings

    async def generate_text(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        provider = self.settings.provider.lower()
        if provider == "disabled" or not self.settings.api_key:
            return LLMResponse(
                content="LLM disabled. Using deterministic agent logic only.",
                provider="disabled",
                model=self.settings.model,
                used_live_model=False,
            )

        if provider != "openai":
            return LLMResponse(
                content=f"LLM provider '{self.settings.provider}' is not wired in this runtime. Falling back to deterministic logic.",
                provider=self.settings.provider,
                model=self.settings.model,
                used_live_model=False,
            )

        client = AsyncOpenAI(
            api_key=self.settings.api_key,
            base_url=self.settings.api_base,
        )
        response = await client.responses.create(
            model=self._normalize_model(self.settings.model),
            temperature=self.settings.temperature,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = getattr(response, "output_text", None) or ""
        return LLMResponse(
            content=content.strip() or "Model returned an empty response.",
            provider="openai",
            model=self.settings.model,
            used_live_model=True,
        )

    @staticmethod
    def _normalize_model(model: str) -> str:
        return model.split("/", 1)[1] if model.startswith("openai/") else model
