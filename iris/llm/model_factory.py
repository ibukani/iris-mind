"""Model Factory — LLM モデルインスタンス生成。

LLMBridge からモデル生成ロジックを分離し、プロバイダ別の ChatModel 構築を担当する。
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from loguru import logger
from pydantic import SecretStr

from iris.kernel.config import ModelConfig, ModelEntry

_PROVIDER_DEFAULTS: dict[str, str] = {
    "ollama": "http://localhost:11434",
    "openrouter": "https://openrouter.ai/api/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
}


def resolve_connection(entry: ModelEntry, model_config: ModelConfig) -> tuple[str, str]:
    """モデルエントリの接続情報（base_url, api_key）を解決する。"""
    conn = model_config.providers.get(entry.provider)
    base_url = conn.base_url if conn else ""
    api_key = conn.api_key if conn else ""
    default_url = _PROVIDER_DEFAULTS.get(entry.provider)
    if default_url:
        base_url = base_url or default_url
    return base_url, api_key


def create_chat_model(entry: ModelEntry, base_url: str, api_key: str, model_config: ModelConfig) -> BaseChatModel:
    """モデル設定に基づいて LangChain ChatModel インスタンスを生成する。"""
    if entry.provider == "ollama":
        options: dict[str, Any] = {
            "num_ctx": entry.num_ctx if entry.num_ctx is not None else model_config.default_num_ctx,
            "num_gpu": entry.num_gpu if entry.num_gpu is not None else model_config.default_num_gpu,
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
            reasoning=entry.reasoning,
            client_kwargs={"timeout": 120},
            async_client_kwargs={"timeout": 120},
            options=options,  # type: ignore[call-arg]
        )

    # openrouter / google 等の OpenAI 互換プロバイダ
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


def build_ollama_options(
    temperature: float,
    max_tokens: int,
    entry: Any,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Ollama 用のオプション辞書を構築する。"""
    options: dict[str, Any] = {
        "temperature": temperature,
        "num_predict": max_tokens,
    }
    if entry and getattr(entry, "repeat_penalty", None) is not None:
        options["repeat_penalty"] = entry.repeat_penalty
    for k in ("presence_penalty", "frequency_penalty", "repeat_penalty"):
        if k in kwargs:
            options[k] = kwargs.pop(k)
    return options


def build_openai_kwargs(
    temperature: float,
    max_tokens: int,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    """OpenAI 互換プロバイダ用のキーワード引数辞書を構築する。"""
    call_kwargs: dict[str, Any] = {
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    for k in ("presence_penalty", "frequency_penalty"):
        if k in kwargs:
            call_kwargs[k] = kwargs.pop(k)
    return call_kwargs


def unload_model(model_name: str | None, model_map: dict[str, str], providers: dict[str, BaseChatModel]) -> None:
    """指定モデルを Ollama からアンロードする（keep_alive=0 で強制開放）。"""
    if not model_name:
        return
    key = model_map.get(model_name)
    if not key:
        return
    provider = providers[key]
    if isinstance(provider, ChatOllama):
        _unload_ollama_model(model_name, provider)


def _unload_ollama_model(model_name: str, provider: ChatOllama) -> None:
    from ollama import Client

    try:
        Client(host=getattr(provider, "base_url", None)).chat(
            model=model_name,
            messages=[{"role": "user", "content": ""}],
            keep_alive=0,
        )
    except Exception as e:
        logger.warning("Failed to unload ollama model {}: {}", model_name, e)
