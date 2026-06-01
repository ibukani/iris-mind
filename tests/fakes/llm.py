"""Fake LLM Provider。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class FakeLLMProvider:
    def __init__(self, responses: list[Any] | None = None) -> None:
        self.call_count = 0
        from langchain_core.messages import AIMessage

        self._responses: list[Any] = responses or [AIMessage(content="Hello from FakeLLM")]
        self._messages_log: list[list[dict]] = []
        self._model_log: list[str | None] = []

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        enable_thinking: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        on_token: Callable[[str], None] | None = None,
        **kwargs: Any,
    ) -> Any:
        self._messages_log.append(messages)
        self._model_log.append(model)
        resp = self._responses[self.call_count % len(self._responses)]
        self.call_count += 1
        return resp

    def is_available(self) -> bool:
        return True

    def unload_model(self, model_name: str) -> None:
        pass


__all__ = ["FakeLLMProvider"]
