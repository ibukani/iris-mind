"""
Google AI Studio Provider — OpenAI 互換 API ラッパー。

Google AI Studio (Gemini) OpenAI 互換 REST API と httpx で通信し、ストリーミング・ツール呼び出しを提供する。
"""

from __future__ import annotations

import sys

import httpx

from iris.kernel.config import ModelConfig, ModelEntry
from iris.llm.openai_compatible_provider import OpenAICompatibleProvider


class GoogleProvider(OpenAICompatibleProvider):
    """Google AI Studio バックエンド向け LLM プロバイダ。"""

    def __init__(
        self,
        api_key: str,
        default_model: str = "gemini-2.5-flash",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai",
        http_client: httpx.Client | None = None,
        max_retries: int = 5,
    ) -> None:
        super().__init__(
            api_key=api_key,
            default_model=default_model,
            base_url=base_url,
            provider_name="Google",
            http_client=http_client,
            max_retries=max_retries,
        )

    @classmethod
    def ensure_environment(cls, entries: list[ModelEntry], model_config: ModelConfig) -> bool:
        """Google API 環境を確認する（API キー検証 → モデル存在確認）。"""
        if not entries:
            return True
        provider_name = entries[0].provider
        conn = model_config.providers.get(provider_name)
        api_key = conn.api_key if (conn and conn.api_key) else ""
        base_url = (
            (conn.base_url if conn else "") or "https://generativelanguage.googleapis.com/v1beta/openai"
        ).rstrip("/")

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
            remote_ids = {m["id"].removeprefix("models/") for m in data.get("data", [])}
        except Exception as e:
            print(f"Google API への接続に失敗しました: {e}", file=sys.stderr)
            return False

        ok = True
        for m in entries:
            if m.name.removeprefix("models/") not in remote_ids:
                print(
                    f"  警告: モデル '{m.name}' が Google AI Studio のモデル一覧に見つかりません。"
                    f" モデル名を確認してください。",
                    file=sys.stderr,
                )
                ok = False
        if not ok:
            print("一部のモデルが見つかりませんが、起動を続行します。", file=sys.stderr)
        return True
