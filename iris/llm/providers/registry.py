"""Registry — LLM プロバイダクラスのレジストリ。

プロバイダクラスの登録と検索を担当する。
変更理由: base.py からレジストリ機能を分離。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.llm.providers.base import BaseLLMProvider

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
