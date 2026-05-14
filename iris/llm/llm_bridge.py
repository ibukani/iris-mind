"""
LLM Bridge — プロバイダファサード。

LLMProvider プロトコルに準拠したプロバイダインスタンスを受け取り、
従来と同じインターフェースで LLM 呼び出しを提供する。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .ollama_provider import OllamaProvider
from .openrouter_provider import OpenRouterProvider
from .provider import LLMProvider


class LLMBridge:
    """LLM プロバイダへのファサード。kernel 層に安定したインターフェースを提供する。"""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        enable_thinking: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        on_token: Callable[[str], None] | None = None,
        **kwargs: Any,
    ) -> dict:
        return self._provider.chat(
            messages=messages,
            model=model,
            enable_thinking=enable_thinking,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            on_token=on_token,
            **kwargs,
        )

    def is_available(self) -> bool:
        return self._provider.is_available()

    def unload_model(self, model_name: str) -> None:
        self._provider.unload_model(model_name)


def create_provider(
    provider_type: str,
    *,
    base_url: str = "http://localhost:11434",
    api_key: str = "",
    default_model: str = "qwen3.5:9b",
    num_gpu: int = 0,
    num_ctx: int = 8192,
) -> LLMProvider:
    """設定に基づいて適切なプロバイダを生成する。"""
    if provider_type == "openrouter":
        return OpenRouterProvider(
            api_key=api_key,
            default_model=default_model,
            base_url=base_url,
        )
    return OllamaProvider(
        model_name=default_model,
        base_url=base_url,
        num_gpu=num_gpu,
        num_ctx=num_ctx,
    )
