"""LLM Bridge — マルチプロバイダルーター。

ModelConfig に基づき複数の LangChain ChatModel インスタンスを管理し、
モデル名に応じて適切なプロバイダへルーティングする。
"""

from __future__ import annotations

from collections.abc import Callable
import re
from typing import Any

from cachetools import LRUCache, cached
import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from loguru import logger
from pydantic import SecretStr

from iris.kernel.config import ModelConfig, ModelEntry

from .priority_lock import PriorityLock


class LLMBridge:
    """複数の LLM プロバイダへのアクセスを抽象化し、ルーティングを行うブリッジクラス。"""

    def __init__(self, model_config: ModelConfig) -> None:
        self._providers: dict[str, BaseChatModel] = {}
        self._model_map: dict[str, str] = {}
        self._entries: dict[str, ModelEntry] = {}
        self._model_config = model_config
        self._priority_lock = PriorityLock()

        for entry in model_config.models:
            base_url, api_key = self._resolve_connection(entry)
            key = f"{entry.provider}|{base_url}|{api_key}"
            if key not in self._providers:
                self._providers[key] = self._create_chat_model(entry, base_url, api_key)
            self._model_map[entry.name] = key
            self._entries[entry.name] = entry

    def _resolve_connection(self, entry: ModelEntry) -> tuple[str, str]:
        conn = self._model_config.providers.get(entry.provider)
        base_url = conn.base_url if conn else ""
        api_key = conn.api_key if conn else ""
        if entry.provider == "ollama":
            base_url = base_url or "http://localhost:11434"
        elif entry.provider == "openrouter":
            base_url = base_url or "https://openrouter.ai/api/v1"
        elif entry.provider == "google":
            base_url = base_url or "https://generativelanguage.googleapis.com/v1beta/openai"
        return base_url, api_key

    def _create_chat_model(self, entry: ModelEntry, base_url: str, api_key: str) -> BaseChatModel:
        """モデル設定に基づいて LangChain ChatModel インスタンスを生成する。"""
        if entry.provider == "ollama":
            options: dict[str, Any] = {
                "num_ctx": entry.num_ctx if entry.num_ctx is not None else self._model_config.default_num_ctx,
                "num_gpu": entry.num_gpu if entry.num_gpu is not None else self._model_config.default_num_gpu,
            }
            if entry.presence_penalty is not None:
                options["presence_penalty"] = entry.presence_penalty
            if entry.frequency_penalty is not None:
                options["frequency_penalty"] = entry.frequency_penalty
            if entry.repeat_penalty is not None:
                options["repeat_penalty"] = entry.repeat_penalty
            return ChatOllama(
                model=entry.name,
                base_url=base_url,
                keep_alive=entry.keep_alive or "10m",
                options=options,  # type: ignore[call-arg]
            )

        # openrouter / google 等の OpenAI 互換プロバイダ
        extra_headers = {}
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

    async def chat(
        self,
        messages: list[BaseMessage],
        model: str | None = None,
        enable_thinking: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        on_token: Callable[[str], None] | None = None,
        interrupt_token: object | None = None,
        priority: int = 0,
        **kwargs: Any,
    ) -> AIMessage:
        """指定されたモデルでチャット生成を実行する。"""
        model_name = model or self._get_default_model()
        provider = self._resolve_provider(model_name)
        entry = self._entries.get(model_name)

        call_kwargs: dict[str, Any] = {}
        if isinstance(provider, ChatOllama):
            options = {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
            if entry and entry.repeat_penalty is not None:
                options["repeat_penalty"] = entry.repeat_penalty
            for k in ["presence_penalty", "frequency_penalty", "repeat_penalty"]:
                if k in kwargs:
                    options[k] = kwargs.pop(k)
            call_kwargs["options"] = options
        else:
            call_kwargs["temperature"] = temperature
            call_kwargs["max_tokens"] = max_tokens
            for k in ["presence_penalty", "frequency_penalty"]:
                if k in kwargs:
                    call_kwargs[k] = kwargs.pop(k)

        call_kwargs.update(kwargs)

        active_model: Any = provider
        if tools:
            active_model = provider.bind_tools(tools)

        # Resolve interrupt token
        local_interrupt_token = interrupt_token
        if local_interrupt_token is None:
            from .interrupt_token import InterruptToken

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

        langchain_messages = messages

        async with self._priority_lock(priority):
            if on_token:
                full_message = None
                try:
                    async for chunk in active_model.astream(langchain_messages, **call_kwargs):
                        if getattr(local_interrupt_token, "is_cancelled", False):
                            break
                        if full_message is None:
                            full_message = chunk
                        else:
                            full_message += chunk

                        if chunk.content and isinstance(chunk.content, str):
                            wrapped_on_token(chunk.content)
                except Exception as e:
                    logger.error("LangChain stream error: {}", e)
                    raise

                if full_message is None:
                    full_message = AIMessage(content="")

                resp_message: Any = full_message
            else:
                resp_message = await active_model.ainvoke(langchain_messages, **call_kwargs)

        content = resp_message.content
        if isinstance(content, list):
            content_str = ""
            for c in content:
                if isinstance(c, dict) and "text" in c:
                    content_str += c["text"]
                elif isinstance(c, str):
                    content_str += c
            content = content_str

        # Check and trim repetition in final response
        if content and self._detect_repetition(content):
            content = self._trim_repetition(content)
            logger.warning("Trimmed repetition loop from final LLM response.")
            if isinstance(resp_message, AIMessage):
                # We can construct a new AIMessage since content is updated
                new_msg = AIMessage(content=content)
                if hasattr(resp_message, "tool_calls"):
                    new_msg.tool_calls = resp_message.tool_calls
                return new_msg
        if not isinstance(resp_message, AIMessage):
            return AIMessage(content=str(getattr(resp_message, "content", "")))
        return resp_message

    async def chat_with_structured_output(
        self,
        schema: Any,
        messages: list[BaseMessage],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> Any:
        """指定されたモデルで with_structured_output を使用したチャット生成を実行する。"""
        model_name = model or self._get_default_model()
        provider = self._resolve_provider(model_name)

        call_kwargs: dict[str, Any] = {}
        if isinstance(provider, ChatOllama):
            call_kwargs["options"] = {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        else:
            call_kwargs["temperature"] = temperature
            call_kwargs["max_tokens"] = max_tokens
        call_kwargs.update(kwargs)

        active_model = provider.with_structured_output(schema)
        return await active_model.ainvoke(messages, **call_kwargs)

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
        for provider in self._providers.values():
            if isinstance(provider, ChatOllama):
                try:
                    url = getattr(provider, "base_url", None)
                    if url:
                        r = httpx.get(url, timeout=1.0)
                        if r.status_code == 200:
                            any_ok = True
                except Exception:
                    logger.warning("Ollama provider at {} is unavailable", getattr(provider, "base_url", None))
            elif isinstance(provider, ChatOpenAI) and provider.openai_api_key:
                any_ok = True
        return any_ok

    def unload_model(self, model_name: str | None = None) -> None:
        """メモリ解放のため、指定されたモデルをプロバイダからアンロードする。"""
        if model_name:
            key = self._model_map.get(model_name)
            if key:
                provider = self._providers[key]
                if isinstance(provider, ChatOllama):
                    from ollama import Client

                    try:
                        Client(host=getattr(provider, "base_url", None)).chat(
                            model=model_name,
                            messages=[{"role": "user", "content": ""}],
                            keep_alive=0,
                        )
                    except Exception as e:
                        logger.warning("Failed to unload ollama model {}: {}", model_name, e)

    @cached(cache=LRUCache(maxsize=32))  # type: ignore[arg-type]
    def _resolve_provider(self, model_name: str) -> BaseChatModel:
        """モデル名から対応するプロバイダインスタンスを解決する。"""
        key = self._model_map.get(model_name)
        if key:
            return self._providers[key]
        first = next(iter(self._providers.values()))
        logger.warning("Model %r not found in provider map, using first provider", model_name)
        return first

    @cached(cache=LRUCache(maxsize=1))  # type: ignore[arg-type]
    def _get_default_model(self) -> str:
        """デフォルト of モデル名を取得する（マップの最初のモデル）。"""
        for name in self._model_map:
            return name
        return ""
