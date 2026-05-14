"""
OpenRouter Provider — OpenAI 互換 API ラッパー。

OpenRouter REST API と httpx で通信し、ストリーミング・ツール呼び出しを提供する。
"""

from __future__ import annotations

import json
import logging
import sys
import time
from collections.abc import Callable
from typing import Any

import httpx

from iris.kernel.config import ModelConfig

logger = logging.getLogger(__name__)


class OpenRouterProvider:
    """OpenRouter バックエンド向け LLM プロバイダ。"""

    def __init__(
        self,
        api_key: str,
        default_model: str = "qwen/qwen-3.5-9b",
        base_url: str = "https://openrouter.ai/api/v1",
        http_client: httpx.Client | None = None,
        max_retries: int = 5,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required for OpenRouter")
        self.api_key = api_key
        self.default_model = default_model
        self.base_url = base_url.rstrip("/")
        self._client = http_client or httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0))
        self._max_retries = max_retries

    def _request(self, body: dict, headers: dict) -> httpx.Response:
        """指数バックオフ付きリトライで POST する。"""
        for attempt in range(self._max_retries):
            resp = self._client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=body,
            )
            if resp.status_code != 429:
                resp.raise_for_status()
                return resp

            retry_after = _parse_retry_after(resp, attempt)
            logger.warning(
                "OpenRouter 429 (attempt %d/%d): waiting %.1fs",
                attempt + 1,
                self._max_retries,
                retry_after,
            )
            time.sleep(retry_after)

        resp.raise_for_status()
        return resp  # unreachable

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        enable_thinking: bool = False,  # noqa: ARG002
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        on_token: Callable[[str], None] | None = None,
        **kwargs: Any,  # noqa: ARG002
    ) -> dict:
        """LLM にチャットリクエストを送信する。"""
        effective_model = model or self.default_model

        body: dict[str, Any] = {
            "model": effective_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": on_token is not None,
        }
        if tools:
            body["tools"] = tools

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/anomalyco/my-iris",
            "X-Title": "Iris",
        }

        try:
            if on_token is not None:
                return self._stream_chat(body=body, headers=headers, on_token=on_token)
            resp = self._request(body=body, headers=headers)
            data = resp.json()
            return _normalize_response(data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RuntimeError(
                    "OpenRouterのAPI制限（429）に達しました。しばらく待ってから再試行するか、"
                    "OpenRouterのアカウントにチャージしてください。"
                ) from e
            raise RuntimeError(f"OpenRouter API エラー ({e.response.status_code})") from e

    def _stream_chat(
        self,
        body: dict,
        headers: dict,
        on_token: Callable[[str], None],
    ) -> dict:
        content_parts: list[str] = []
        tool_calls: list[dict] | None = None

        for attempt in range(self._max_retries):
            with self._client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=body,
            ) as stream:
                if stream.status_code == 429:
                    retry_after = _parse_retry_after(stream, attempt)
                    logger.warning(
                        "OpenRouter 429 stream (attempt %d/%d): waiting %.1fs",
                        attempt + 1,
                        self._max_retries,
                        retry_after,
                    )
                    time.sleep(retry_after)
                    continue

                stream.raise_for_status()
                for line in stream.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})

                    content = delta.get("content", "")
                    if content:
                        content_parts.append(content)
                        on_token(content)

                    if delta.get("tool_calls"):
                        if tool_calls is None:
                            tool_calls = []
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)
                            while len(tool_calls) <= idx:
                                tool_calls.append(
                                    {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                                )
                            existing = tool_calls[idx]
                            if tc.get("id"):
                                existing["id"] = tc["id"]
                            if tc.get("function"):
                                fn = tc["function"]
                                if fn.get("name"):
                                    existing["function"]["name"] += fn["name"]
                                if fn.get("arguments"):
                                    existing["function"]["arguments"] += fn["arguments"]
                break
        else:
            raise RuntimeError("OpenRouter stream failed after max retries")

        full_content = "".join(content_parts)
        msg: dict = {"role": "assistant", "content": full_content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        return {"message": _process_message(msg)}

    def is_available(self) -> bool:
        """API キーが設定されていれば利用可能とみなす。"""
        return bool(self.api_key)

    def unload_model(self, model_name: str) -> None:  # noqa: ARG002
        """OpenRouter にアンロード概念はない。"""
        return

    @classmethod
    def ensure_environment(cls, model_config: ModelConfig) -> bool:
        """OpenRouter 環境を確認する（API キー検証 → モデル存在確認）。"""
        if not model_config.api_key or model_config.api_key.startswith("${"):
            print(
                "APIキーが設定されていません。config.yaml の model.api_key を確認してください。",
                file=sys.stderr,
            )
            return False

        base_url = model_config.base_url.rstrip("/")
        headers = {
            "Authorization": f"Bearer {model_config.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = httpx.get(f"{base_url}/models", headers=headers, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            remote_ids = {m["id"] for m in data.get("data", [])}
        except Exception as e:
            print(f"OpenRouter への接続に失敗しました: {e}", file=sys.stderr)
            return False

        ok = True
        for m in model_config.models:
            if m.name not in remote_ids:
                print(
                    f"  警告: モデル '{m.name}' が OpenRouter のモデル一覧に見つかりません。"
                    f" モデル名を確認してください。",
                    file=sys.stderr,
                )
                ok = False
        if not ok:
            print("一部のモデルが見つかりませんが、起動を続行します。", file=sys.stderr)
        return True


def _normalize_response(data: dict) -> dict:
    """OpenAI 互換レスポンスを内部形式に正規化する。"""
    choice = data.get("choices", [{}])[0]
    msg = choice.get("message", {})
    return {"message": _process_message(msg)}


def _process_message(msg: dict) -> dict:
    if msg.get("content"):
        msg["content"] = msg["content"].strip()
    return msg


def _parse_retry_after(resp: httpx.Response, attempt: int = 0) -> float:
    val = resp.headers.get("Retry-After")
    if val:
        try:
            return float(val)
        except ValueError:
            pass
    return 2.0**attempt
