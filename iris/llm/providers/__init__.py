"""Providers — LLM バックエンド実装群。

環境検証用のダミークラス定義を提供し、LangChain 移行後も
既存の ensure_environment 呼び出し（main.py やテスト）との互換性を維持する。
"""

from __future__ import annotations

from typing import Protocol

from iris.kernel.config import ModelConfig, ModelEntry

from . import ollama_env


class ProviderFactory(Protocol):
    """プロバイダクラス（ファクトリ）のインターフェース。"""

    @classmethod
    def ensure_environment(cls, entries: list[ModelEntry], model_config: ModelConfig) -> bool: ...


class OllamaProvider:
    """Ollama 環境検証用ダミークラス。"""

    @classmethod
    def ensure_environment(cls, entries: list[ModelEntry], model_config: ModelConfig) -> bool:
        return ollama_env.ensure_environment(entries, model_config)


class _ApiKeyProvider:
    """APIキーの存在確認のみを行うプロバイダ基底実装。"""

    @classmethod
    def ensure_environment(cls, entries: list[ModelEntry], model_config: ModelConfig) -> bool:
        for entry in entries:
            conn = model_config.providers.get(entry.provider)
            if not conn or not conn.api_key:
                return False
        return True


class OpenRouterProvider(_ApiKeyProvider):
    """OpenRouter 環境検証用ダミークラス。"""


class GoogleProvider(_ApiKeyProvider):
    """Google 環境検証用ダミークラス。"""


_PROVIDER_CLASSES: dict[str, type[ProviderFactory]] = {
    "ollama": OllamaProvider,
    "openrouter": OpenRouterProvider,
    "google": GoogleProvider,
}


def get_provider_class(provider_type: str) -> type[ProviderFactory]:
    """指定されたプロバイダタイプに対応するファクトリクラスを取得する。"""
    cls = _PROVIDER_CLASSES.get(provider_type)
    if cls is None:
        msg = f"Unknown provider type: {provider_type!r}"
        raise ValueError(msg)
    return cls


__all__ = [
    "GoogleProvider",
    "OllamaProvider",
    "OpenRouterProvider",
    "ProviderFactory",
    "get_provider_class",
]
