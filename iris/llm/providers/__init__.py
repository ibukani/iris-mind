"""Providers — LLM プロバイダレジストリ。

新規プロバイダ追加手順:
  1. BaseLLMProvider を継承し provider_name を設定したクラスを providers/ 配下に作成
  2. 以上 (auto-discover + auto-register が自動処理)
  ヒトの作業 = ファイル 1 つ作成のみ。

注: OpenAICompatibleProvider のように 1 クラスで複数 provider_type を
     扱うケースは例外的に明示的な register_provider() を __init__.py に記述する。
"""

from __future__ import annotations

from .base import BaseLLMProvider, discover_providers, get_provider_class, register_provider
from .ollama import OllamaProvider
from .openai_compatible import GoogleProvider, OpenAICompatibleProvider, OpenRouterProvider

# ── Auto-discover: providers/ の全 .py を import → __init_subclass__ で auto-register ──

discover_providers()

# ── 複数 provider_type → 1 クラスのマッピング (例外) ──────────────────

register_provider("openrouter", OpenAICompatibleProvider)
register_provider("google", OpenAICompatibleProvider)

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
