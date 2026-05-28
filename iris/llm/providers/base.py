"""BaseLLMProvider — LLM プロバイダ抽象基底クラス。

新規プロバイダ追加手順:
  1. BaseLLMProvider を継承し、provider_name を設定
  2. providers/ 配下に配置 (auto-discover が自動発見 + 登録)
  3. create_chat_model(), build_call_kwargs() を実装
  追加ファイル 1 つだけ。既存コード編集不要。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from langchain_core.language_models import BaseChatModel

from iris.kernel.config import ModelConfig, ModelEntry

# ── Registry ────────────────────────────────────────────────

_PROVIDER_REGISTRY: dict[str, type[BaseLLMProvider]] = {}


def register_provider(name: str, cls: type[BaseLLMProvider]) -> None:
    """プロバイダクラスをレジストリに登録する。"""
    _PROVIDER_REGISTRY[name] = cls


def get_provider_class(provider_type: str) -> type[BaseLLMProvider]:
    """指定されたプロバイダ種別に対応するクラスを取得する。"""
    cls = _PROVIDER_REGISTRY.get(provider_type)
    if cls is None:
        msg = f"Unknown provider type: {provider_type!r}"
        raise ValueError(msg)
    return cls


def discover_providers() -> None:
    """providers/ 配下の全プロバイダモジュールを自動発見し import する。

    各モジュールのクラス定義時に __init_subclass__ が呼ばれ、
    provider_name をキーに自動登録される。
    追加ファイルを置くだけで既存コード編集は不要。
    """
    import importlib
    from pathlib import Path

    pkg_path = Path(__file__).parent
    for f in sorted(pkg_path.glob("*.py")):
        name = f.stem
        if name in ("base", "__init__"):
            continue
        importlib.import_module(f".{name}", "iris.llm.providers")


# ── ベースクラス ────────────────────────────────────────────


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
    def ensure_environment(
        cls,
        entries: list[ModelEntry],
        model_config: ModelConfig,
    ) -> bool:
        """実行環境の確認・準備。デフォルトは True を返す。"""
        return True
