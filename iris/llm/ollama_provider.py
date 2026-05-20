"""
Ollama Provider — Ollama API ラッパー。

ollama.Client をラップし、ストリーミング・thinking モード・ツール呼び出しを提供する。
"""

from __future__ import annotations

from collections.abc import Callable
import contextlib
import logging
import os
import re
import subprocess
import sys
import threading
import time
from typing import Any

import httpx
from ollama import Client

from iris.kernel.config import ModelConfig, ModelEntry

logger = logging.getLogger(__name__)
_MAX_RETRIES = 3
_RETRY_BACKOFF_SECONDS = 0.5
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_IS_WINDOWS = sys.platform == "win32"


class OllamaProvider:
    """Ollama バックエンド向け LLM プロバイダ。"""

    def __init__(
        self,
        model_name: str = "qwen3.5:9b",
        base_url: str = "http://localhost:11434",
        num_gpu: int = 0,
        num_ctx: int = 8192,
    ) -> None:
        self.model_name = model_name
        self.num_gpu = num_gpu
        self.num_ctx = num_ctx
        self.client = Client(host=base_url)
        self._chat_lock = threading.Lock()

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
    ) -> dict:
        """LLM にチャットリクエストを送信する。"""
        with self._chat_lock:
            call_kwargs = self._build_chat_kwargs(
                messages=messages,
                model=model,
                enable_thinking=enable_thinking,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                interrupt_token=interrupt_token,
                stream=on_token is not None,
                kwargs=kwargs,
            )

            if on_token is not None:
                return self._stream_chat(**call_kwargs, on_token=on_token, interrupt_token=interrupt_token)

            resp = self._chat_with_retries(call_kwargs)
            resp["message"] = _process_message(resp["message"])
            return resp

    def _build_chat_kwargs(
        self,
        messages: list[dict],
        model: str | None,
        enable_thinking: bool,
        temperature: float,
        max_tokens: int,
        tools: list[dict] | None,
        interrupt_token: object | None,
        stream: bool,
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx": kwargs.pop("num_ctx", self.num_ctx),
            "num_gpu": kwargs.pop("num_gpu", self.num_gpu),
            "repeat_penalty": 1.1,
        }
        main_gpu = kwargs.pop("main_gpu", None)
        if main_gpu is not None:
            options["main_gpu"] = main_gpu
        call_kwargs: dict[str, Any] = {
            "model": model or self.model_name,
            "messages": messages,
            "options": options,
            "stream": stream,
            "think": enable_thinking,
        }
        if tools:
            call_kwargs["tools"] = tools
        if kwargs.get("keep_alive") is not None:
            call_kwargs["keep_alive"] = kwargs.pop("keep_alive")
        if interrupt_token is not None:
            call_kwargs["interrupt_token"] = interrupt_token
        return call_kwargs

    def _chat_with_retries(self, kwargs: dict) -> dict:
        return self._retry_transport_call(
            lambda: self.client.chat(**kwargs),
            "Ollama request retry loop exited unexpectedly",
        )

    def _stream_chat(
        self,
        on_token: Callable[[str], None],
        interrupt_token: Any = None,
        **kwargs: Any,
    ) -> dict:
        return self._retry_transport_call(
            lambda: self._stream_chat_once(
                on_token=on_token,
                interrupt_token=interrupt_token,
                **kwargs,
            ),
            "Ollama stream retry loop exited unexpectedly",
        )

    def _stream_chat_once(
        self,
        on_token: Callable[[str], None],
        interrupt_token: Any = None,
        **kwargs: Any,
    ) -> dict:
        content_parts: list[str] = []
        tool_calls = None
        final = None
        try:
            stream = self.client.chat(**kwargs)
            for chunk in stream:
                if interrupt_token is not None and getattr(interrupt_token, "is_cancelled", False):
                    break
                if chunk.get("done"):
                    final = dict(chunk)
                    break
                msg = chunk.get("message", {})
                if msg.get("content"):
                    content_parts.append(msg["content"])
                    on_token(msg["content"])
                if msg.get("tool_calls"):
                    tool_calls = msg["tool_calls"]
        except httpx.TransportError:
            if content_parts:
                raise RuntimeError("Ollama stream disconnected after partial response") from None
            raise

        if final is None:
            final = {"message": {"role": "assistant", "content": ""}}
        full_content = "".join(content_parts)
        final["message"]["content"] = full_content
        if tool_calls:
            final["message"]["tool_calls"] = tool_calls
        final["message"] = _process_message(final["message"])
        return final

    def _retry_transport_call(self, operation: Callable[[], dict], error_message: str) -> dict:
        for attempt in range(_MAX_RETRIES):
            try:
                return operation()
            except httpx.TransportError:
                if attempt == _MAX_RETRIES - 1:
                    raise
                _log_retry(attempt)
                time.sleep(_retry_delay(attempt))

        raise RuntimeError(error_message)

    def unload_model(self, model_name: str) -> None:
        """指定モデルを VRAM から解放する。"""
        self.client.chat(
            model=model_name,
            messages=[{"role": "user", "content": ""}],
            keep_alive=0,
        )

    def is_available(self) -> bool:
        """Ollama が応答可能か確認する。"""
        try:
            self.client.list()
            return True
        except Exception:
            return False

    @classmethod
    def ensure_environment(cls, entries: list[ModelEntry], model_config: ModelConfig) -> bool:
        """Ollama 環境を確認・準備する（再起動 → モデル確認 → pull）。"""
        default_gpu = model_config.default_num_gpu if entries else 99
        os.environ.setdefault("OLLAMA_GPU_LAYERS", str(default_gpu))
        _restart_ollama()
        model_names = [e.name for e in entries]
        _stop_config_models(model_names)
        time.sleep(0.5)
        return all(_ensure_model_pulled(name) for name in model_names)


def _process_message(msg: dict) -> dict:
    """LLM応答メッセージの後処理。"""
    if not msg.get("content") and msg.get("thinking"):
        msg["content"] = _extract_answer_from_thinking(msg["thinking"])
    if msg.get("content"):
        msg["content"] = msg["content"].strip()
    return msg


def _retry_delay(attempt: int) -> float:
    return _RETRY_BACKOFF_SECONDS * (2**attempt)  # type: ignore[no-any-return]


def _log_retry(attempt: int) -> None:
    logger.warning("Ollama connection failed; retrying (%d/%d)", attempt + 1, _MAX_RETRIES)


def _get_available_models() -> set[str]:
    """Ollama に既に pull 済みのモデル名のセットを返す。"""
    try:
        client = Client()
        response = client.list()
        models: set[str] = set()
        for model in response.get("models", []):
            name = model.get("name", "") if isinstance(model, dict) else getattr(model, "name", "")
            if name and ":" in name:
                models.add(name.split(":")[0])
            elif name:
                models.add(name)
        return models
    except Exception:
        return set()


def _ensure_model_pulled(model_name: str) -> bool:
    """モデルが存在しない場合はユーザーに確認して pull する。"""
    model_base = model_name.split(":")[0]
    available = _get_available_models()
    if model_base in available:
        return True

    try:
        console_input = input(
            f"モデル '{model_name}' が見つかりません。\n  ollama pull {model_name}\nを実行してダウンロードしますか？ [y/N] "
        )
    except EOFError:
        logger.warning("Non-interactive environment: skipping model pull for '%s'", model_name)
        return False
    if console_input.strip().lower() in ("y", "yes"):
        try:
            subprocess.run(
                ["ollama", "pull", model_name],
                check=True,
                timeout=600,
            )
            return True
        except subprocess.CalledProcessError:
            print(f"モデル '{model_name}' のダウンロードに失敗しました。", file=sys.stderr)
            return False
        except subprocess.TimeoutExpired:
            print(f"モデル '{model_name}' のダウンロードがタイムアウトしました。", file=sys.stderr)
            return False
    return False


def _restart_ollama() -> None:
    """既存 Ollama プロセスを終了し、GPU 向け設定で再起動する。"""
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


def _stop_config_models(model_names: list[str]) -> None:
    """指定されたモデルを停止する。"""
    for name in model_names:
        with contextlib.suppress(Exception):
            subprocess.run(["ollama", "stop", name], capture_output=True, timeout=10)


def _extract_answer_from_thinking(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return stripped
    final_lines: list[str] = []
    in_thinking_block = False
    for line in stripped.splitlines():
        if re.match(r"^\s*```?\s*(think|thought|reasoning|思考)\s*", line, re.IGNORECASE):
            in_thinking_block = True
            continue
        if in_thinking_block and re.match(r"^\s*```?\s*", line):
            in_thinking_block = False
            continue
        if not in_thinking_block:
            final_lines.append(line)
    if final_lines:
        return "\n".join(final_lines).strip()
    content_lines = [
        line
        for line in stripped.splitlines()
        if not re.match(
            r"^\s*(思考|Thinking|Reasoning|Step \d|Hmm|Wait|Let me|I need|Actually|"
            r"Re-evaluat|Draft|Final|I'll|I think|I should|Maybe|Perhaps|"
            r"First,?|Next,?|Finally,?)",
            line.strip(),
            re.IGNORECASE,
        )
    ]
    if content_lines:
        return content_lines[-1].strip()
    return stripped
