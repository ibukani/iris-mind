from __future__ import annotations

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from loguru import logger


def check_bridge_available(providers: dict[str, BaseChatModel]) -> bool:
    return any(_check_provider_available(provider) for provider in providers.values())


def _check_provider_available(provider: BaseChatModel) -> bool:
    if isinstance(provider, ChatOllama):
        url = getattr(provider, "base_url", None)
        if not url:
            return False
        try:
            return bool(httpx.get(url, timeout=1.0).status_code == 200)
        except Exception:
            logger.warning("Ollama provider at {} is unavailable", url)
            return False
    if isinstance(provider, ChatOpenAI):
        return bool(provider.openai_api_key)
    return False


def unload_model(model_name: str | None, model_map: dict[str, str], providers: dict[str, BaseChatModel]) -> None:
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
