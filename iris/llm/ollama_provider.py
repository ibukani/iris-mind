"""
Ollama Provider — Ollama API ラッパー。

ollama.Client をラップし、ストリーミング・thinking モード・ツール呼び出しを提供する。
"""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

from ollama import Client

from iris.kernel.config import ModelConfig


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

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        enable_thinking: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        on_token: Callable[[str], None] | None = None,
        keep_alive: str | None = None,
        **kwargs: Any,
    ) -> dict:
        """LLM にチャットリクエストを送信する。"""
        effective_model = model or self.model_name
        options = {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx": self.num_ctx,
            "num_gpu": self.num_gpu,
            "repeat_penalty": 1.1,
        }
        call_kwargs: dict = {
            "model": effective_model,
            "messages": messages,
            "options": options,
            "stream": on_token is not None,
        }
        if tools:
            call_kwargs["tools"] = tools
        call_kwargs["think"] = enable_thinking
        if keep_alive is not None:
            call_kwargs["keep_alive"] = keep_alive

        interrupt_token = kwargs.pop("interrupt_token", None)
        call_kwargs.update(kwargs)

        if on_token is not None:
            return self._stream_chat(**call_kwargs, on_token=on_token, interrupt_token=interrupt_token)

        resp = self.client.chat(**call_kwargs)
        resp["message"] = _process_message(resp["message"])
        return resp

    def _stream_chat(
        self,
        on_token: Callable[[str], None],
        interrupt_token: Any = None,
        **kwargs: Any,
    ) -> dict:
        stream = self.client.chat(**kwargs)
        content_parts: list[str] = []
        tool_calls = None
        final = None
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

        if final is None:
            final = {"message": {"role": "assistant", "content": ""}}
        full_content = "".join(content_parts)
        final["message"]["content"] = full_content
        if tool_calls:
            final["message"]["tool_calls"] = tool_calls
        final["message"] = _process_message(final["message"])
        return final

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
    def ensure_environment(cls, model_config: ModelConfig) -> bool:
        """Ollama 環境を確認・準備する（再起動 → モデル確認 → pull）。"""
        os.environ.setdefault("OLLAMA_GPU_LAYERS", str(model_config.num_gpu))
        _restart_ollama()
        _stop_config_models(model_config.model_names)
        time.sleep(0.5)
        return all(_ensure_model_pulled(name) for name in model_config.model_names)


def _process_message(msg: dict) -> dict:
    """LLM応答メッセージの後処理。"""
    if not msg.get("content") and msg.get("thinking"):
        msg["content"] = _extract_answer_from_thinking(msg["thinking"])
    if msg.get("content"):
        msg["content"] = msg["content"].strip()
    return msg


def _get_available_models() -> set[str]:
    """Ollama に既に pull 済みのモデル名のセットを返す。"""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().splitlines()
            models: set[str] = set()
            for line in lines[2:]:
                if line.strip():
                    name = line.strip().split()[0]
                    if ":" in name:
                        models.add(name.split(":")[0])
            return models
    except Exception:
        pass
    return set()


def _ensure_model_pulled(model_name: str) -> bool:
    """モデルが存在しない場合はユーザーに確認して pull する。"""
    model_base = model_name.split(":")[0]
    available = _get_available_models()
    if model_base in available:
        return True

    console_input = input(
        f"モデル '{model_name}' が見つかりません。\n  ollama pull {model_name}\nを実行してダウンロードしますか？ [y/N] "
    )
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


def _restart_ollama():
    """既存 Ollama プロセスを終了し、GPU 向け設定で再起動する。"""
    with contextlib.suppress(Exception):
        subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"], capture_output=True, timeout=5)
    time.sleep(2)

    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    time.sleep(5)


def _stop_config_models(model_names: list[str]):
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
