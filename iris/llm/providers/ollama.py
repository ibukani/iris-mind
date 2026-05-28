"""OllamaProvider — Ollama 向け全実装。

ChatModel 生成、パラメータ構築、ヘルスチェック、アンロード、
環境検証を一箇所に集約。config.yaml で provider: ollama のエントリに対応。
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import time
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from loguru import logger

from iris.kernel.config import ModelConfig, ModelEntry

from .base import BaseLLMProvider

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_IS_WINDOWS = sys.platform == "win32"


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
            options=options,
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
        options: dict[str, Any] = {
            "temperature": temperature,
            "num_predict": max_tokens,
        }
        if entry and getattr(entry, "repeat_penalty", None) is not None:
            options["repeat_penalty"] = entry.repeat_penalty
        for k in ("presence_penalty", "frequency_penalty", "repeat_penalty"):
            if k in kwargs:
                options[k] = kwargs.pop(k)

        # num_ctx は Ollama の options 配下に入れる
        num_ctx = kwargs.pop("num_ctx", None)
        if num_ctx is not None:
            options["num_ctx"] = num_ctx

        call_kwargs: dict[str, Any] = {"options": options}
        if reasoning is not None:
            call_kwargs["reasoning"] = reasoning
        return call_kwargs

    def check_health(self, provider: BaseChatModel) -> bool:
        import httpx

        url = getattr(provider, "base_url", None)
        if not url:
            return False
        try:
            return bool(httpx.get(url, timeout=1.0).status_code == 200)
        except Exception:
            logger.warning("Ollama provider at {} is unavailable", url)
            return False

    def unload(self, model_name: str, provider: BaseChatModel) -> None:
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

    @classmethod
    def ensure_environment(
        cls,
        entries: list[ModelEntry],
        model_config: ModelConfig,
    ) -> bool:
        default_gpu = model_config.default_num_gpu if entries else 99
        os.environ.setdefault("OLLAMA_GPU_LAYERS", str(default_gpu))
        os.environ["OLLAMA_FLASH_ATTENTION"] = "1"
        cls._restart_ollama()
        model_names = [e.name for e in entries]
        cls._stop_config_models(model_names)
        time.sleep(0.5)
        return all(cls._ensure_model_pulled(name) for name in model_names)

    # ── 内部ヘルパー ─────────────────────────────────────────

    @classmethod
    def _restart_ollama(cls) -> None:
        with contextlib.suppress(Exception):
            if _IS_WINDOWS:
                subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"], capture_output=True, timeout=5)
            else:
                subprocess.run(["pkill", "-f", "ollama"], capture_output=True, timeout=5)
        time.sleep(2)

        popen_kwargs: dict[str, Any] = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if _IS_WINDOWS:
            popen_kwargs["creationflags"] = _CREATE_NO_WINDOW
        subprocess.Popen(["ollama", "serve"], **popen_kwargs)
        time.sleep(5)

    @classmethod
    def _stop_config_models(cls, model_names: list[str]) -> None:
        for name in model_names:
            with contextlib.suppress(Exception):
                subprocess.run(["ollama", "stop", name], capture_output=True, timeout=10)

    @staticmethod
    def _extract_model_name(model: Any) -> str:
        name = ""
        if isinstance(model, dict):
            name = model.get("model") or model.get("name") or ""
        else:
            name = getattr(model, "model", "") or getattr(model, "name", "")
        return name.split(":")[0] if ":" in name else name

    @classmethod
    def _get_available_models(cls) -> set[str]:
        from ollama import Client

        try:
            response = Client().list()
            names = [cls._extract_model_name(m) for m in response.get("models", [])]
            return {n for n in names if n}
        except Exception:
            return set()

    @classmethod
    def _ensure_model_pulled(cls, model_name: str) -> bool:
        model_base = model_name.split(":")[0]
        if model_base in cls._get_available_models():
            return True
        if not cls._confirm_pull(model_name):
            return False
        try:
            subprocess.run(["ollama", "pull", model_name], check=True, timeout=600)
            return True
        except subprocess.CalledProcessError:
            print(f"モデル '{model_name}' のダウンロードに失敗しました。", file=sys.stderr)
            return False
        except subprocess.TimeoutExpired:
            print(f"モデル '{model_name}' のダウンロードがタイムアウトしました。", file=sys.stderr)
            return False

    @staticmethod
    def _confirm_pull(model_name: str) -> bool:
        try:
            resp = input(
                f"モデル '{model_name}' が見つかりません。\n  ollama pull {model_name}\nを実行してダウンロードしますか？ [y/N] "
            )
        except EOFError:
            logger.warning("Non-interactive environment: skipping model pull for '{}'", model_name)
            return False
        return resp.strip().lower() in ("y", "yes")
