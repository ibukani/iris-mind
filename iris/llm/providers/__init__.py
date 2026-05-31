"""Providers — LLM プロバイダレジストリ。

新規プロバイダ追加手順:
  1. BaseLLMProvider を継承し provider_name を設定したクラスを providers/ 配下に作成
  2. 以上 (auto-discover + auto-register が自動処理)
  ヒトの作業 = ファイル 1 つ作成のみ。
"""

from __future__ import annotations

from .base import BaseLLMProvider, discover_providers, get_provider_class, register_provider
from .ollama import OllamaProvider
from .openai_compatible import GoogleProvider, OpenAICompatibleProvider, OpenRouterProvider

# ── Auto-discover: providers/ の全 .py を import → __init_subclass__ で auto-register ──

discover_providers()

__all__ = [
    "BaseLLMProvider",
    "GoogleProvider",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "OpenRouterProvider",
    "discover_providers",
    "get_provider_class",
    "register_provider",
]
