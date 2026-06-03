"""BaseLLMProvider — LLM プロバイダ抽象基底クラス。

新規プロバイダ追加手順:
  1. BaseLLMProvider を継承し、provider_name を設定
  2. providers/ 配下に配置 (auto-discover が自動発見 + 登録)
  3. create_chat_model(), build_call_kwargs() を実装
  追加ファイル 1 つだけ。既存コード編集不要。

--- 後方互換エクスポート ---
register_provider / get_provider_class / discover_providers は
registry.py / discovery.py に移動したが、下位互換のため再エクスポートする。
新規コードは明示的なモジュールからのインポートを推奨:
  from iris.llm.providers.registry import register_provider, get_provider_class
  from iris.llm.providers.discovery import discover_providers
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from langchain_core.language_models import BaseChatModel

from iris.kernel.config import ModelConfig, ModelEntry

# 後方互換のための再エクスポート
from iris.llm.providers.discovery import discover_providers  # noqa: F401
from iris.llm.providers.registry import (  # noqa: F401
    get_provider_class,
    register_provider,
)


class BaseLLMProvider(ABC):
    """LLM プロバイダの抽象基底クラス。

    継承時に __init_subclass__ が provider_name をキーに自動登録する。
    provider_name が空文字の場合は登録しない (複数名で1クラスを使う場合等)。
    """

    provider_name: str = ""
    """config.yaml の ModelEntry.provider と一致させる識別子。
    空文字の場合は auto-registration がスキップされる。"""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.provider_name:
            from iris.llm.providers.registry import register_provider

            register_provider(cls.provider_name, cls)

    @abstractmethod
    def create_chat_model(
        self,
        entry: ModelEntry,
        base_url: str,
        api_key: str,
        model_config: ModelConfig,
    ) -> BaseChatModel:
        """ModelEntry の設定に基づき LangChain ChatModel インスタンスを生成する。"""

    @abstractmethod
    def build_call_kwargs(
        self,
        temperature: float,
        max_tokens: int,
        entry: ModelEntry | None,
        kwargs: dict[str, Any],
        reasoning: bool | None = None,
        default_num_ctx: int = 8192,
    ) -> dict[str, Any]:
        """LLM 呼び出し時のプロバイダ固有キーワード引数を構築する。

        プロバイダ固有パラメータはここで kwargs から消費 (pop) する。
        戻り値はモデルの ainvoke/astream に ** 展開される。
        """

    def check_health(self, provider: BaseChatModel) -> bool:
        """ヘルスチェック。デフォルトは True を返す。"""
        return True

    def unload(self, model_name: str, provider: BaseChatModel) -> None:
        """モデルアンロード。デフォルトは何もしない。必要に応じてオーバーライド。"""
        return

    @classmethod
    def validate_environment(
        cls,
        entries: list[ModelEntry],
        model_config: ModelConfig,
    ) -> bool:
        """実行環境の検証 (軽量)。デフォルトは True を返す。"""
        return True

    @classmethod
    def prepare_environment(
        cls,
        entries: list[ModelEntry],
        model_config: ModelConfig,
    ) -> bool:
        """実行環境の準備 (heavy: restart, pull 等)。デフォルトは True を返す。"""
        return True

    @classmethod
    def ensure_environment(
        cls,
        entries: list[ModelEntry],
        model_config: ModelConfig,
    ) -> bool:
        """validate + prepare を順に実行する。"""
        if not cls.validate_environment(entries, model_config):
            return False
        return cls.prepare_environment(entries, model_config)
