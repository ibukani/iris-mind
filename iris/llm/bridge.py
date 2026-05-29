"""LLM Bridge — マルチプロバイダルーター。

ModelConfig に基づき複数のプロバイダ ChatModel インスタンスを管理し、
モデル名に応じて適切なプロバイダへルーティングする。
プロバイダ固有のロジックは BaseLLMProvider 実装に委譲している。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from loguru import logger

from iris.kernel.config import ModelConfig, ModelEntry

from .interrupt_token import InterruptToken
from .model_factory import resolve_connection
from .priority_lock import PriorityLock
from .repetition import RepetitionDetector


class LLMBridge:
    """複数の LLM プロバイダへのアクセスを抽象化し、ルーティングを行うブリッジクラス。"""

    def __init__(self, model_config: ModelConfig) -> None:
        from .providers import get_provider_class

        self._chat_models: dict[str, BaseChatModel] = {}
        self._model_map: dict[str, str] = {}
        self._entries: dict[str, ModelEntry] = {}
        self._model_providers: dict[str, BaseLLMProvider] = {}
        self._provider_instances: dict[str, BaseLLMProvider] = {}
        self._model_config = model_config
        self._priority_lock = PriorityLock()
        self._repetition_detector = RepetitionDetector()

        for entry in model_config.models:
            base_url, api_key = resolve_connection(entry, model_config)
            provider_cls = get_provider_class(entry.provider)
            key = f"{entry.provider}|{base_url}|{api_key}"

            if key not in self._provider_instances:
                provider = provider_cls()
                self._provider_instances[key] = provider
            else:
                provider = self._provider_instances[key]

            if key not in self._chat_models:
                self._chat_models[key] = provider.create_chat_model(entry, base_url, api_key, model_config)

            self._model_map[entry.name] = key
            self._entries[entry.name] = entry
            self._model_providers[entry.name] = provider

    @staticmethod
    def _extract_content(resp_message: AIMessage) -> str:
        content = resp_message.content
        if isinstance(content, list):
            return "".join(c["text"] if isinstance(c, dict) else str(c) for c in content)
        return str(content) if content else ""

    async def chat(
        self,
        messages: list[BaseMessage],
        model: str | None = None,
        reasoning: bool | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        on_token: Callable[[str], None] | None = None,
        interrupt_token: InterruptToken | None = None,
        priority: int = 0,
        **kwargs: Any,
    ) -> AIMessage:
        model_name = model or self._get_default_model()
        chat_model = self._resolve_chat_model(model_name)
        entry = self._entries.get(model_name)
        provider = self._get_provider_for_model(model_name)

        call_kwargs = provider.build_call_kwargs(
            temperature,
            max_tokens,
            entry,
            kwargs,
            reasoning=reasoning,
            default_num_ctx=self._model_config.default_num_ctx,
        )
        call_kwargs.update(kwargs)

        active_model = chat_model.bind_tools(tools) if tools else chat_model

        local_interrupt_token = interrupt_token or InterruptToken()
        accumulated_text: list[str] = []

        def wrapped_on_token(token: str) -> None:
            if local_interrupt_token.is_cancelled:
                return
            accumulated_text.append(token)
            if self._detect_repetition("".join(accumulated_text)):
                logger.warning("Repetition loop detected in stream, interrupting.")
                local_interrupt_token.cancel()
                return
            if on_token:
                on_token(token)

        async with self._priority_lock(priority):
            resp_message = await self._stream_or_invoke(
                active_model,
                messages,
                call_kwargs,
                on_token,
                local_interrupt_token,
                wrapped_on_token,
            )

        return self._handle_response_content(resp_message)

    def _handle_response_content(self, resp_message: AIMessage) -> AIMessage:
        content = self._extract_content(resp_message)
        if content and self._detect_repetition(content):
            content = self._trim_repetition(content)
            logger.warning("Trimmed repetition loop from final LLM response.")
            new_msg = AIMessage(content=content)
            if getattr(resp_message, "tool_calls", None):
                new_msg.tool_calls = resp_message.tool_calls
            return new_msg
        return resp_message

    async def _stream_or_invoke(
        self,
        active_model: Any,
        messages: list[BaseMessage],
        call_kwargs: dict[str, Any],
        on_token: Callable[[str], None] | None,
        interrupt_token: InterruptToken,
        wrapped_on_token: Callable[[str], None],
    ) -> Any:
        if not on_token:
            return await active_model.ainvoke(messages, **call_kwargs)

        full_message = None
        try:
            async for chunk in active_model.astream(messages, **call_kwargs):
                full_message = chunk if full_message is None else full_message + chunk
                if chunk.content and isinstance(chunk.content, str):
                    wrapped_on_token(chunk.content)
        except Exception as e:
            logger.error("LangChain stream error: {}", e)
            raise

        if interrupt_token.is_cancelled:
            return full_message or AIMessage(content="")
        return full_message or AIMessage(content="")

    async def chat_with_structured_output(
        self,
        schema: Any,
        messages: list[BaseMessage],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> Any:
        model_name = model or self._get_default_model()
        chat_model = self._resolve_chat_model(model_name)
        provider = self._get_provider_for_model(model_name)
        entry = self._entries.get(model_name)

        call_kwargs = provider.build_call_kwargs(
            temperature,
            max_tokens,
            entry,
            kwargs,
            default_num_ctx=self._model_config.default_num_ctx,
        )

        active_model = chat_model.with_structured_output(schema)
        return await active_model.ainvoke(messages, **call_kwargs)

    def _detect_repetition(self, text: str) -> bool:
        return self._repetition_detector.detect(text)

    def _trim_repetition(self, text: str) -> str:
        return self._repetition_detector.trim(text)

    def is_available(self) -> bool:
        for key, chat_model in self._chat_models.items():
            provider = self._provider_instances.get(key)
            if provider and provider.check_health(chat_model):
                return True
        return False

    def unload_model(self, model_name: str | None = None) -> None:
        if not model_name:
            return
        key = self._model_map.get(model_name)
        if not key:
            return
        provider = self._provider_instances.get(key)
        chat_model = self._chat_models.get(key)
        if provider and chat_model:
            provider.unload(model_name, chat_model)

    def _resolve_chat_model(self, model_name: str) -> BaseChatModel:
        """モデル名から対応する ChatModel インスタンスを解決する。"""
        key = self._model_map.get(model_name)
        if key:
            return self._chat_models[key]
        first = next(iter(self._chat_models.values()))
        logger.warning("Model {!r} not found in model map, using first provider", model_name)
        return first

    def _get_provider_for_model(self, model_name: str) -> BaseLLMProvider:
        """モデル名から対応する BaseLLMProvider インスタンスを取得する。"""
        provider = self._model_providers.get(model_name)
        if provider:
            return provider
        first = next(iter(self._provider_instances.values()))
        logger.warning("No provider found for model {!r}, using first available", model_name)
        return first

    def _get_default_model(self) -> str:
        for name in self._model_map:
            return name
        return ""


# ── 循環インポート回避のための型インポート ──────────────────

from .providers import BaseLLMProvider  # noqa: E402
