"""EpisodicInput / SemanticInput への型強制 (coercion) ヘルパ。

memory 層の上位 API は入力型を緩く受け取る (str / dict / TypedDict) ため、
内部で統一された TypedDict に変換する。
"""

from __future__ import annotations

from typing import Any

from iris.memory.long_term.models import EpisodicInput, SemanticInput


def coerce_episodic_input(data: Any, kind: str = "") -> EpisodicInput:
    if isinstance(data, EpisodicInput):
        return data
    if isinstance(data, str):
        return EpisodicInput(content=data, kind=kind)
    if isinstance(data, dict):
        return EpisodicInput(
            content=str(data.get("content") or data.get("summary") or ""),
            kind=str(data.get("kind", kind)),
            metadata=data.get("metadata"),
            room_id=str(data.get("room_id", "")),
            account_id=str(data.get("account_id", "")),
        )
    return EpisodicInput(content=str(data), kind=kind)


def coerce_semantic_input(data: Any) -> SemanticInput:
    if isinstance(data, SemanticInput):
        return data
    if isinstance(data, dict):
        raw_tags = data.get("tags") or []
        tags: list[str] = [str(t) for t in raw_tags] if isinstance(raw_tags, list) else []
        return SemanticInput(
            content=str(data.get("content", "")),
            type=str(data.get("type", "lesson")),
            tags=tags,
            room_id=str(data.get("room_id", "")),
            account_id=str(data.get("account_id", "")),
        )
    return SemanticInput(content=str(data))


__all__ = ["coerce_episodic_input", "coerce_semantic_input"]
