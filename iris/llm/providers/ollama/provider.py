"""OllamaProvider — Ollama 向けプロバイダ実装。

各責務は siblings モジュールに委譲:
  - call_options.py: ChatOllama 生成/呼び出しパラメータ
  - health.py: ヘルスチェック / アンロード
  - environment.py: 環境変数設定
  - model_admin.py: 再起動 / 停止 / モデルプル / 確認対話
"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama

from iris.kernel.config import ModelConfig, ModelEntry
from iris.llm.providers.base import BaseLLMProvider
from iris.llm.providers.ollama.call_options import build_call_options, build_create_options
from iris.llm.providers.ollama.environment import set_ollama_env_vars
from iris.llm.providers.ollama.health import check_server_health, unload_model
from iris.llm.providers.ollama.model_admin import ensure_model_pulled, restart_ollama, stop_models


class OllamaProvider(BaseLLMProvider):
    """Ollama プロバイダ実装。"""

    provider_name = "ollama"

    def create_chat_model(
        self,
        entry: ModelEntry,
        base_url: str,
        api_key: str,
        model_config: ModelConfig,
    ) -> BaseChatModel:
        options = build_create_options(entry, model_config)
        return ChatOllama(
            model=entry.name,
            base_url=base_url,
            keep_alive=entry.keep_alive or "10m",
            reasoning=entry.reasoning,
            client_kwargs={"timeout": 120},
            async_client_kwargs={"timeout": 120},
            options=options,  # type: ignore[call-arg]
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
        options = build_call_options(temperature, max_tokens, entry, kwargs, default_num_ctx)
        call_kwargs: dict[str, Any] = {"options": options}
        if reasoning is not None:
            call_kwargs["reasoning"] = reasoning
        return call_kwargs

    def check_health(self, provider: BaseChatModel) -> bool:
        return check_server_health(provider)

    def unload(self, model_name: str, provider: BaseChatModel) -> None:
        unload_model(model_name, provider)

    @classmethod
    def validate_environment(
        cls,
        entries: list[ModelEntry],
        model_config: ModelConfig,
    ) -> bool:
        set_ollama_env_vars(entries, model_config)
        return True

    @classmethod
    def prepare_environment(
        cls,
        entries: list[ModelEntry],
        model_config: ModelConfig,
    ) -> bool:
        restart_ollama()
        model_names = [e.name for e in entries]
        stop_models(model_names)
        time.sleep(0.5)
        return all(ensure_model_pulled(name) for name in model_names)
