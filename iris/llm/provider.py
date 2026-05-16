"""
LLM Provider Protocol — プロバイダ抽象化インターフェース。

LLMBridge が依存するプロバイダの契約を定義する。
OllamaProvider / OpenRouterProvider はこの Protocol に準拠する。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from iris.kernel.config import ModelConfig


class LLMProvider(Protocol):
    """LLM プロバイダインスタンスのインターフェース。"""

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
    ) -> dict: ...

    def is_available(self) -> bool: ...

    def unload_model(self, model_name: str) -> None: ...


class ProviderFactory(Protocol):
    """Provider クラス自体（ファクトリ）のインターフェース。

    環境確認など、インスタンス化前のクラスレベル操作を定義する。
    """

    @classmethod
    def ensure_environment(cls, model_config: ModelConfig) -> bool: ...
