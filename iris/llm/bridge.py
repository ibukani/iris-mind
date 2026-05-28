"""LLM Bridge — マルチプロバイダルーター。

ModelConfig に基づき複数の LangChain ChatModel インスタンスを管理し、
モデル名に応じて適切なプロバイダへルーティングする。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_ollama import ChatOllama
from loguru import logger

from iris.kernel.config import ModelConfig

from .health import check_bridge_available
from .interrupt_token import InterruptToken
from .model_factory import build_ollama_options, build_openai_kwargs, create_chat_model, resolve_connection, unload_model
from .priority_lock import PriorityLock
from .repetition import RepetitionDetector


class LLMBridge:
    """複数の LLM プロバイダへのアクセスを抽象化し、ルーティングを行うブリッジクラス。"""

    def __init__(self, model_config: ModelConfig) -> None:
        self._providers: dict[str, BaseChatModel] = {}
        self._model_map: dict[str, str] = {}
        self._entries: dict[str, ModelEntry] = {}
        self._model_config = model_config
        self._priority_lock = PriorityLock()
        self._repetition_detector = RepetitionDetector()

        for entry in model_config.models:
            base_url, api_key = resolve_connection(entry, model_config)
            key = f"{entry.provider}|{base_url}|{api_key}"
            if key not in self._providers:
                self._providers[key] = create_chat_model(entry, base_url, api_key, model_config)
            self._model_map[entry.name] = key
            self._entries[entry.name] = entry

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
        provider = self._resolve_provider(model_name)
        entry = self._entries.get(model_name)

        call_kwargs = self._build_call_kwargs(provider, temperature, max_tokens, entry, kwargs, reasoning=reasoning)
        active_model = provider.bind_tools(tools) if tools else provider

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
                active_model, messages, call_kwargs, on_token, local_interrupt_token, wrapped_on_token
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

    def _build_call_kwargs(
        self,
        provider: BaseChatModel,
        temperature: float,
        max_tokens: int,
        entry: ModelEntry | None,
        kwargs: dict[str, Any],
        reasoning: bool | None = None,
    ) -> dict[str, Any]:
        if isinstance(provider, ChatOllama):
            call_options = build_ollama_options(temperature, max_tokens, entry, kwargs)
            instance_options = dict(getattr(provider, "options", None) or {})
            merged = {**instance_options, **call_options}
            if "num_ctx" not in merged:
                merged["num_ctx"] = self._model_config.default_num_ctx
            call_kwargs: dict[str, Any] = {"options": merged}
            if reasoning is not None:
                call_kwargs["reasoning"] = reasoning
        else:
            call_kwargs = build_openai_kwargs(temperature, max_tokens, kwargs)
        call_kwargs.update(kwargs)
        return call_kwargs

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
            return AIMessage(content="")
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
        provider = self._resolve_provider(model_name)
        call_kwargs = self._build_call_kwargs(provider, temperature, max_tokens, None, kwargs)

        active_model = provider.with_structured_output(schema)
        return await active_model.ainvoke(messages, **call_kwargs)

    def _detect_repetition(self, text: str) -> bool:
        return self._repetition_detector.detect(text)

    def _trim_repetition(self, text: str) -> str:
        return self._repetition_detector.trim(text)

    def is_available(self) -> bool:
        return check_bridge_available(self._providers)

    def unload_model(self, model_name: str | None = None) -> None:
        unload_model(model_name, self._model_map, self._providers)

    def _resolve_provider(self, model_name: str) -> BaseChatModel:
        """モデル名から対応するプロバイダインスタンスを解決する。"""
        key = self._model_map.get(model_name)
        if key:
            return self._providers[key]
        first = next(iter(self._providers.values()))
        logger.warning("Model {!r} not found in provider map, using first provider", model_name)
        return first

    def _get_default_model(self) -> str:
        """デフォルト of モデル名を取得する（マップの最初のモデル）。"""
        for name in self._model_map:
            return name
        return ""
