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

# ── Auto-discover: providers/ の全 .py を import → __init_subclass__ で auto-register ──

discover_providers()

# ── 複数 provider_type → 1 クラスのマッピング (例外) ──────────────────

from .openai_compatible import OpenAICompatibleProvider as _OpenAICompatibleProvider

register_provider("openrouter", _OpenAICompatibleProvider)
register_provider("google", _OpenAICompatibleProvider)

# ── Re-exports (後方互換) ──────────────────────────────────

from .ollama import OllamaProvider as OllamaProvider
from .openai_compatible import GoogleProvider as GoogleProvider
from .openai_compatible import OpenAICompatibleProvider as OpenAICompatibleProvider
from .openai_compatible import OpenRouterProvider as OpenRouterProvider

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
