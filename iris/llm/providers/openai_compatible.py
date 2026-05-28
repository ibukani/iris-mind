"""OpenAICompatibleProvider — OpenAI 互換 API 向け全実装。

OpenRouter / Google など、ChatOpenAI で接続可能なプロバイダを統一的に扱う。
config.yaml で provider: openrouter / google のエントリに対応。
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from loguru import logger
from pydantic import SecretStr

from iris.kernel.config import ModelConfig, ModelEntry

from .base import BaseLLMProvider


class OpenAICompatibleProvider(BaseLLMProvider):
    """OpenAI 互換 API プロバイダ実装 (OpenRouter / Google 等)。

    1 クラスで複数 provider_type を扱うため provider_name は空文字にし、
    明示的な register_provider() でマッピングする。
    """

    provider_name = ""

    def create_chat_model(
        self,
        entry: ModelEntry,
        base_url: str,
        api_key: str,
        model_config: ModelConfig,
    ) -> BaseChatModel:
        extra_headers: dict[str, str] = {}
        if entry.provider == "openrouter":
            extra_headers = {
                "HTTP-Referer": "https://github.com/ibukani/iris-kernel",
                "X-Title": "Iris Kernel",
            }

        model_kwargs: dict[str, Any] = {}
        if entry.presence_penalty is not None:
            model_kwargs["presence_penalty"] = entry.presence_penalty
        if entry.frequency_penalty is not None:
            model_kwargs["frequency_penalty"] = entry.frequency_penalty

        return ChatOpenAI(
            model=entry.name,
            api_key=SecretStr(api_key),
            base_url=base_url,
            default_headers=extra_headers if extra_headers else None,
            model_kwargs=model_kwargs,
        )

    def build_call_kwargs(
        self,
        temperature: float,
        max_tokens: int,
        entry: ModelEntry | None,
        kwargs: dict[str, Any],
        reasoning: bool | None = None,
        default_num_ctx: int = 8192,
    ) -> dict[str, Any]:
        call_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        for k in ("presence_penalty", "frequency_penalty"):
            if k in kwargs:
                call_kwargs[k] = kwargs.pop(k)
        # OpenAI 互換 API は num_ctx を扱わない
        kwargs.pop("num_ctx", None)
        return call_kwargs

    def check_health(self, provider: BaseChatModel) -> bool:
        if isinstance(provider, ChatOpenAI):
            return bool(provider.openai_api_key)
        logger.warning("Unsupported provider type for health check: {}", type(provider).__name__)
        return False

    @classmethod
    def ensure_environment(
        cls,
        entries: list[ModelEntry],
        model_config: ModelConfig,
    ) -> bool:
        for entry in entries:
            conn = model_config.providers.get(entry.provider)
            if not conn or not conn.api_key:
                return False
        return True


# ── 後方互換用エイリアス ────────────────────────────────────


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter 専用インスタンス (OpenAICompatibleProvider のエイリアス)。"""


class GoogleProvider(OpenAICompatibleProvider):
    """Google 専用インスタンス (OpenAICompatibleProvider のエイリアス)。"""
