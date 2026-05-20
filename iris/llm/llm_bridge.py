"""
LLM Bridge — マルチプロバイダルーター。

ModelConfig に基づき複数の LLMProvider インスタンスを管理し、
モデル名に応じて適切なプロバイダへルーティングする。
"""

from __future__ import annotations

from collections.abc import Callable
import logging
import re
from typing import Any

from iris.kernel.config import ModelConfig, ModelEntry

from .ollama_provider import OllamaProvider
from .openrouter_provider import OpenRouterProvider
from .provider import LLMProvider, ProviderFactory

logger = logging.getLogger(__name__)

_PROVIDER_CLASSES: dict[str, type[ProviderFactory]] = {
    "ollama": OllamaProvider,
    "openrouter": OpenRouterProvider,
}


def get_provider_class(provider_type: str) -> type[ProviderFactory]:
    """指定されたプロバイダタイプに対応するファクトリクラスを取得する。"""
    cls = _PROVIDER_CLASSES.get(provider_type)
    if cls is None:
        msg = f"Unknown provider type: {provider_type!r}"
        raise ValueError(msg)
    return cls


class LLMBridge:
    """複数の LLM プロバイダへのアクセスを抽象化し、ルーティングを行うブリッジクラス。"""

    def __init__(self, model_config: ModelConfig) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._model_map: dict[str, str] = {}
        self._entries: dict[str, ModelEntry] = {}
        self._model_config = model_config

        for entry in model_config.models:
            key = f"{entry.provider}|{entry.base_url}|{entry.api_key}"
            if key not in self._providers:
                self._providers[key] = self._create_provider(entry)
            self._model_map[entry.name] = key
            self._entries[entry.name] = entry

    def _create_provider(self, entry: ModelEntry) -> LLMProvider:
        """モデル設定に基づいてプロバイダインスタンスを生成する。"""
        if entry.provider == "openrouter":
            return OpenRouterProvider(
                api_key=entry.api_key or "",
                default_model=entry.name,
                base_url=entry.base_url or "https://openrouter.ai/api/v1",
            )
        return OllamaProvider(
            model_name=entry.name,
            base_url=entry.base_url or "http://localhost:11434",
            num_gpu=entry.num_gpu if entry.num_gpu is not None else self._model_config.default_num_gpu,
            num_ctx=entry.num_ctx if entry.num_ctx is not None else self._model_config.default_num_ctx,
            keep_alive=entry.keep_alive or "10m",
        )

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        enable_thinking: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        on_token: Callable[[str], None] | None = None,
        interrupt_token: object | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """指定されたモデルでチャット生成を実行する。

        適切なプロバイダへルーティングし、設定されたコンテキスト上限やGPU数などのパラメータを適用する。
        """
        model_name = model or self._get_default_model()
        provider = self._resolve_provider(model_name)
        entry = self._entries.get(model_name)
        if entry is not None:
            if entry.num_ctx is not None:
                kwargs.setdefault("num_ctx", entry.num_ctx)
            if entry.num_gpu is not None:
                kwargs.setdefault("num_gpu", entry.num_gpu)
            if entry.presence_penalty is not None:
                kwargs.setdefault("presence_penalty", entry.presence_penalty)
            if entry.frequency_penalty is not None:
                kwargs.setdefault("frequency_penalty", entry.frequency_penalty)
            if entry.repeat_penalty is not None:
                kwargs.setdefault("repeat_penalty", entry.repeat_penalty)

        # Resolve interrupt token
        local_interrupt_token = interrupt_token
        if local_interrupt_token is None:
            from iris.agency.execution.interrupt_token import InterruptToken

            local_interrupt_token = InterruptToken()

        accumulated_text: list[str] = []

        def wrapped_on_token(token: str) -> None:
            if getattr(local_interrupt_token, "is_cancelled", False):
                return
            accumulated_text.append(token)
            full_text = "".join(accumulated_text)
            if self._detect_repetition(full_text):
                logger.warning("Repetition loop detected in stream, interrupting.")
                cancel_fn = getattr(local_interrupt_token, "cancel", None)
                if cancel_fn and callable(cancel_fn):
                    cancel_fn()
                return
            if on_token:
                on_token(token)

        resp = provider.chat(
            messages=messages,
            model=model_name,
            enable_thinking=enable_thinking,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            on_token=wrapped_on_token if on_token else None,
            interrupt_token=local_interrupt_token,
            **kwargs,
        )

        # Check and trim repetition in final response
        if "message" in resp and resp["message"].get("content"):
            content = resp["message"]["content"]
            if self._detect_repetition(content):
                resp["message"]["content"] = self._trim_repetition(content)
                logger.warning("Trimmed repetition loop from final LLM response.")

        return resp

    def _detect_repetition(self, text: str) -> bool:
        """Detect abnormal repetitions in generated text."""
        if not text:
            return False
        target = text[-150:] if len(text) > 150 else text

        # Match 2-20 chars repeated 4+ times consecutively
        # Skip if the pattern is composed of a single repeating character
        for match in re.finditer(r"(.{2,20}?)\1{3,}", target):
            pattern = match.group(1)
            if len(set(pattern)) > 1:
                return True

        # Match single char repeated 10+ times consecutively
        return bool(re.search(r"(.)\1{9,}", target))

    def _trim_repetition(self, text: str) -> str:
        """Trim detected repetition loops and append interruption note."""
        # 2-20 chars repeated 4+ times (skip if single-character pattern)
        for match_multi in re.finditer(r"((.{2,20}?)\2{3,})", text):
            pattern = match_multi.group(2)
            if len(set(pattern)) > 1:
                start, _ = match_multi.span(1)
                replacement = pattern * 2 + "… [繰り返し検知により中断]"
                return text[:start] + replacement

        # Single char repeated 10+ times
        match_single = re.search(r"((.)\2{9,})", text)
        if match_single:
            start, _ = match_single.span(1)
            char = match_single.group(2)
            replacement = char * 3 + "… [繰り返し検知により中断]"
            return text[:start] + replacement

        return text

    def is_available(self) -> bool:
        """登録されているプロバイダのいずれかが利用可能かどうかを判定する。"""
        any_ok = False
        for name, provider in self._providers.items():
            ok = provider.is_available()
            if not ok:
                logger.warning("Provider %s is unavailable", name)
            any_ok = any_ok or ok
        return any_ok

    def unload_model(self, model_name: str | None = None) -> None:
        """メモリ解放のため、指定されたモデルをプロバイダからアンロードする。"""
        if model_name:
            key = self._model_map.get(model_name)
            if key:
                self._providers[key].unload_model(model_name)

    def _resolve_provider(self, model_name: str) -> LLMProvider:
        """モデル名から対応するプロバイダインスタンスを解決する。"""
        key = self._model_map.get(model_name)
        if key:
            return self._providers[key]
        first = next(iter(self._providers.values()))
        logger.warning("Model %r not found in provider map, using first provider", model_name)
        return first

    def _get_default_model(self) -> str:
        """デフォルトのモデル名を取得する（マップの最初のモデル）。"""
        for name in self._model_map:
            return name
        return ""
