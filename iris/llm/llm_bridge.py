"""
LLM Bridge — マルチプロバイダルーター。

ModelConfig に基づき複数の LLMProvider インスタンスを管理し、
モデル名に応じて適切なプロバイダへルーティングする。
"""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from iris.kernel.config import ModelConfig, ModelEntry

from .ollama_provider import OllamaProvider
from .openrouter_provider import OpenRouterProvider
from .provider import LLMProvider, ProviderFactory

logger = logging.getLogger(__name__)

_PROVIDER_CLASSES: dict[str, type[ProviderFactory]] = {
    "ollama": OllamaProvider,
    "openrouter": OpenRouterProvider,
}


def get_provider_class(provider_type: str) -> type[ProviderFactory]:
    cls = _PROVIDER_CLASSES.get(provider_type)
    if cls is None:
        msg = f"Unknown provider type: {provider_type!r}"
        raise ValueError(msg)
    return cls


class LLMBridge:
    def __init__(self, model_config: ModelConfig) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._model_map: dict[str, str] = {}
        self._entries: dict[str, ModelEntry] = {}
        self._model_config = model_config

        for entry in model_config.models:
            key = f"{entry.provider}|{entry.base_url}|{entry.api_key}"
            if key not in self._providers:
                self._providers[key] = self._create_provider(entry)
            self._model_map[entry.name] = key
            self._entries[entry.name] = entry

    def _create_provider(self, entry: ModelEntry) -> LLMProvider:
        if entry.provider == "openrouter":
            return OpenRouterProvider(
                api_key=entry.api_key or "",
                default_model=entry.name,
                base_url=entry.base_url or "https://openrouter.ai/api/v1",
            )
        return OllamaProvider(
            model_name=entry.name,
            base_url=entry.base_url or "http://localhost:11434",
            num_gpu=entry.num_gpu if entry.num_gpu is not None else self._model_config.default_num_gpu,
            num_ctx=entry.num_ctx if entry.num_ctx is not None else self._model_config.default_num_ctx,
        )

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        enable_thinking: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        on_token: Callable[[str], None] | None = None,
        interrupt_token: object | None = None,
        **kwargs: Any,
    ) -> dict:
        model_name = model or self._get_default_model()
        provider = self._resolve_provider(model_name)
        entry = self._entries.get(model_name)
        if entry is not None:
            if entry.num_ctx is not None:
                kwargs.setdefault("num_ctx", entry.num_ctx)
            if entry.num_gpu is not None:
                kwargs.setdefault("num_gpu", entry.num_gpu)
            if entry.main_gpu is not None:
                kwargs.setdefault("main_gpu", entry.main_gpu)

        return provider.chat(
            messages=messages,
            model=model_name,
            enable_thinking=enable_thinking,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            on_token=on_token,
            interrupt_token=interrupt_token,
            **kwargs,
        )

    def is_available(self) -> bool:
        any_ok = False
        for name, provider in self._providers.items():
            ok = provider.is_available()
            if not ok:
                logger.warning("Provider %s is unavailable", name)
            any_ok = any_ok or ok
        return any_ok

    def unload_model(self, model_name: str | None = None) -> None:
        if model_name:
            key = self._model_map.get(model_name)
            if key:
                self._providers[key].unload_model(model_name)

    def _resolve_provider(self, model_name: str) -> LLMProvider:
        key = self._model_map.get(model_name)
        if key:
            return self._providers[key]
        first = next(iter(self._providers.values()))
        logger.warning("Model %r not found in provider map, using first provider", model_name)
        return first

    def _get_default_model(self) -> str:
        for name in self._model_map:
            return name
        return ""
