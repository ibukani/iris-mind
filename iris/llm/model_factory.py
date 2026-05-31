"""Model Factory — 接続情報解決ユーティリティ。

ChatModel 生成・パラメータ構築は各 BaseLLMProvider 実装に委譲済み。
ここでは config.yaml から接続先を解決する関数のみを保持する。
"""

from __future__ import annotations

from iris.kernel.config import ModelConfig, ModelEntry

_PROVIDER_DEFAULTS: dict[str, str] = {
    "ollama": "http://localhost:11434",
    "openrouter": "https://openrouter.ai/api/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
}


def resolve_connection(entry: ModelEntry, model_config: ModelConfig) -> tuple[str, str]:
    """モデルエントリの接続情報（base_url, api_key）を解決する。"""
    conn = model_config.providers.get(entry.provider)
    base_url = conn.base_url if conn else ""
    api_key = conn.api_key if conn else ""
    default_url = _PROVIDER_DEFAULTS.get(entry.provider)
    if default_url:
        base_url = base_url or default_url
    return base_url, api_key
