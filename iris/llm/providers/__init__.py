"""Providers — LLM 環境検証関数群。

各プロバイダの環境確認（APIキー存在確認、Ollama プロセス確認等）を
クラスメソッド経由で提供する。新規プロバイダ追加時は以下の 3 箇所を更新する:

1. クラス定義（ensure_environment を実装）
2. `_PROVIDER_CLASSES` に追加
3. `__all__` に追加
"""

from __future__ import annotations

from iris.kernel.config import ModelConfig, ModelEntry

from . import ollama_environment as ollama_env


def _check_api_key(entries: list[ModelEntry], model_config: ModelConfig) -> bool:
    """APIキー設定の有無を確認する汎用チェック。"""
    for entry in entries:
        conn = model_config.providers.get(entry.provider)
        if not conn or not conn.api_key:
            return False
    return True


class OllamaProvider:
    """Ollama 環境検証クラス。"""

    @classmethod
    def ensure_environment(cls, entries: list[ModelEntry], model_config: ModelConfig) -> bool:
        return ollama_env.ensure_environment(entries, model_config)


class OpenRouterProvider:
    """OpenRouter 環境検証クラス（APIキー確認のみ）。"""

    @classmethod
    def ensure_environment(cls, entries: list[ModelEntry], model_config: ModelConfig) -> bool:
        return _check_api_key(entries, model_config)


class GoogleProvider:
    """Google 環境検証クラス（APIキー確認のみ）。"""

    @classmethod
    def ensure_environment(cls, entries: list[ModelEntry], model_config: ModelConfig) -> bool:
        return _check_api_key(entries, model_config)


_PROVIDER_CLASSES: dict[str, type[OllamaProvider | OpenRouterProvider | GoogleProvider]] = {
    "ollama": OllamaProvider,
    "openrouter": OpenRouterProvider,
    "google": GoogleProvider,
}


def get_provider_class(provider_type: str) -> type[OllamaProvider | OpenRouterProvider | GoogleProvider]:
    """指定されたプロバイダタイプに対応する環境検証クラスを取得する。"""
    cls = _PROVIDER_CLASSES.get(provider_type)
    if cls is None:
        msg = f"Unknown provider type: {provider_type!r}"
        raise ValueError(msg)
    return cls


__all__ = [
    "GoogleProvider",
    "OllamaProvider",
    "OpenRouterProvider",
    "get_provider_class",
]
