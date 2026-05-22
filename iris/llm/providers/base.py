"""
OpenAI Compatible Provider Base Class.

OpenAI 互換 REST API を叩くプロバイダの共通基底クラス。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
from typing import Any

import httpx
from loguru import logger
import orjson
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)


class OpenAICompatibleProvider:
    """OpenAI 互換 REST API 向け LLM プロバイダの共通基底。"""

    def __init__(
        self,
        api_key: str,
        default_model: str,
        base_url: str,
        provider_name: str,
        http_client: httpx.Client | None = None,
        max_retries: int = 5,
    ) -> None:
        if not api_key:
            raise ValueError(f"api_key is required for {provider_name}")
        self.api_key = api_key
        self.default_model = default_model
        self.base_url = base_url.rstrip("/")
        self.provider_name = provider_name
        self._client = http_client or httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0))
        self._max_retries = max_retries

    def _get_headers(self) -> dict[str, str]:
        """リクエストヘッダーを取得する。派生クラスでオーバーライド可能。"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _request(self, body: dict[str, Any], headers: dict[str, str]) -> httpx.Response:
        """指数バックオフ付きリトライで POST する。"""
        _retryer = retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=60),
            retry=retry_if_exception(
                lambda e: isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429,
            ),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )

        @_retryer
        def _do() -> httpx.Response:
            resp = self._client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            return resp

        return _do()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        enable_thinking: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        on_token: Callable[[str], None] | None = None,
        interrupt_token: object | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """LLM にチャットリクエストを送信する。"""

        def _sync_chat() -> dict[str, Any]:
            effective_model = model or self.default_model

            body: dict[str, Any] = {
                "model": effective_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": on_token is not None,
            }
            presence_penalty = kwargs.pop("presence_penalty", None)
            if presence_penalty is not None:
                body["presence_penalty"] = presence_penalty
            frequency_penalty = kwargs.pop("frequency_penalty", None)
            if frequency_penalty is not None:
                body["frequency_penalty"] = frequency_penalty

            if tools:
                body["tools"] = tools

            headers = self._get_headers()

            try:
                if on_token is not None:
                    return self._stream_chat(
                        body=body, headers=headers, on_token=on_token, interrupt_token=interrupt_token
                    )
                resp = self._request(body=body, headers=headers)
                data = resp.json()
                return _normalize_response(data)
            except httpx.HTTPStatusError as e:
                code = e.response.status_code
                msg = _extract_error_text(e.response)
                raise RuntimeError(f"{self.provider_name} API エラー ({code}): {msg}") from e

        return await asyncio.to_thread(_sync_chat)

    def _stream_chat(
        self,
        body: dict[str, Any],
        headers: dict[str, str],
        on_token: Callable[[str], None],
        interrupt_token: object | None = None,
    ) -> dict[str, Any]:
        content_parts: list[str] = []
        tool_calls: list[dict[str, Any]] | None = None

        stream = self._open_stream(body, headers)

        for line in stream.iter_lines():
            if interrupt_token is not None and getattr(interrupt_token, "is_cancelled", False):
                logger.debug("%sProvider: interrupted", self.provider_name)
                break
            if not line or not line.startswith("data: "):
                continue
            payload = line[6:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = orjson.loads(payload.encode("utf-8"))
            except orjson.JSONDecodeError:
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

        stream.close()

        full_content = "".join(content_parts)
        msg: dict[str, Any] = {"role": "assistant", "content": full_content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        return {"message": _process_message(msg)}

    def _open_stream(self, body: dict[str, Any], headers: dict[str, str]) -> httpx.Response:
        @retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=60),
            retry=retry_if_exception(
                lambda e: isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429,
            ),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _connect() -> httpx.Response:
            req = self._client.build_request(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=body,
            )
            resp = self._client.send(req, stream=True)
            if resp.status_code == 429:
                resp.close()
                raise httpx.HTTPStatusError("429 Too Many Requests", request=req, response=resp)
            if resp.status_code != 200:
                error = _extract_error_text(resp)
                resp.close()
                raise RuntimeError(f"{self.provider_name} API エラー ({resp.status_code}): {error}")
            return resp

        return _connect()

    def is_available(self) -> bool:
        """API キーが設定されていれば利用可能とみなす。"""
        return bool(self.api_key)

    def unload_model(self, model_name: str) -> None:
        """API にアンロード概念はない。"""
        return


def _extract_error_text(resp: httpx.Response) -> str:
    """API のエラーレスポンスボディからメッセージを抽出する。"""
    try:
        body = resp.json()
        error = body.get("error", {})
        if isinstance(error, dict):
            return error.get("message", str(body))
        return str(error)
    except Exception:
        text = resp.text
        return text[:500] if text else f"HTTP {resp.status_code}"


def _normalize_response(data: dict[str, Any]) -> dict[str, Any]:
    """OpenAI 互換レスポンスを内部形式に正規化する。"""
    choice = data.get("choices", [{}])[0]
    msg = choice.get("message", {})
    return {"message": _process_message(msg)}


def _process_message(msg: dict[str, Any]) -> dict[str, Any]:
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
