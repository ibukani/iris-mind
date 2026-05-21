"""
OpenRouter Provider — OpenAI 互換 API ラッパー。

OpenRouter REST API と httpx で通信し、ストリーミング・ツール呼び出しを提供する。
"""

from __future__ import annotations

import sys

import httpx

from iris.kernel.config import ModelConfig, ModelEntry
from iris.llm.openai_compatible_provider import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter バックエンド向け LLM プロバイダ。"""

    def __init__(
        self,
        api_key: str,
        default_model: str = "qwen/qwen-3.5-9b",
        base_url: str = "https://openrouter.ai/api/v1",
        http_client: httpx.Client | None = None,
        max_retries: int = 5,
    ) -> None:
        super().__init__(
            api_key=api_key,
            default_model=default_model,
            base_url=base_url,
            provider_name="OpenRouter",
            http_client=http_client,
            max_retries=max_retries,
        )

    def _get_headers(self) -> dict[str, str]:
        """OpenRouter 固有のリクエストヘッダーを取得する。"""
        headers = super()._get_headers()
        headers.update(
            {
                "HTTP-Referer": "https://github.com/anomalyco/iris-mind",
                "X-Title": "Iris",
            }
        )
        return headers

    @classmethod
    def ensure_environment(cls, entries: list[ModelEntry], model_config: ModelConfig) -> bool:
        """OpenRouter 環境を確認する（API キー検証 → モデル存在確認）。"""
        if not entries:
            return True
        provider_name = entries[0].provider
        conn = model_config.providers.get(provider_name)
        api_key = conn.api_key if (conn and conn.api_key) else ""
        base_url = ((conn.base_url if conn else "") or "https://openrouter.ai/api/v1").rstrip("/")

        if not api_key or api_key.startswith("${"):
            print(
                "APIキーが設定されていません。model.providers の api_key を確認してください。",
                file=sys.stderr,
            )
            return False

        headers = {
            "Authorization": f"Bearer {api_key}",
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
        for m in entries:
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
