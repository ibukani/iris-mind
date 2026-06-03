"""health — Ollama サーバー / モデルのヘルスチェック。"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from loguru import logger


def check_server_health(provider: BaseChatModel) -> bool:
    import httpx

    url = getattr(provider, "base_url", None)
    if not url:
        return False
    try:
        return bool(httpx.get(url, timeout=1.0).status_code == 200)
    except Exception:
        logger.warning("Ollama provider at {} is unavailable", url)
        return False


def unload_model(model_name: str, provider: BaseChatModel) -> None:
    if not isinstance(provider, ChatOllama):
        return
    from ollama import Client

    try:
        Client(host=getattr(provider, "base_url", None)).chat(
            model=model_name,
            messages=[{"role": "user", "content": ""}],
            keep_alive=0,
        )
    except Exception as e:
        logger.warning("Failed to unload ollama model {}: {}", model_name, e)
