"""
Providers — LLM バックエンド実装群。

各プロバイダは iris.llm.protocol の LLMProvider Protocol に準拠する。
"""

from __future__ import annotations

from .base import OpenAICompatibleProvider
from .google import GoogleProvider
from .ollama import OllamaProvider
from .openrouter import OpenRouterProvider

_PROVIDER_CLASSES: dict[str, type] = {
    "ollama": OllamaProvider,
    "openrouter": OpenRouterProvider,
    "google": GoogleProvider,
}


def get_provider_class(provider_type: str) -> type:
    """指定されたプロバイダタイプに対応するファクトリクラスを取得する。"""
    cls = _PROVIDER_CLASSES.get(provider_type)
    if cls is None:
        msg = f"Unknown provider type: {provider_type!r}"
        raise ValueError(msg)
    return cls


__all__ = [
    "GoogleProvider",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "OpenRouterProvider",
    "get_provider_class",
]
