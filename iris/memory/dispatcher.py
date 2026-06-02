from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from iris.memory.long_term.protocol import LongTermMemoryProtocol
from iris.memory.models import ContentBlock, text_block
from iris.memory.sensory.protocol import SensoryMemoryProtocol
from iris.memory.short_term.protocol import ShortTermMemoryProtocol


@dataclass(frozen=True, slots=True)
class StoreScope:
    """Dispatcher が抽出する room/account スコープ。"""

    room_id: str
    account_id: str

    @classmethod
    def of(cls, data: Any) -> StoreScope:
        if not isinstance(data, dict):
            return cls("", "")
        return cls(str(data.get("room_id", "")), str(data.get("account_id", "")))


def _extract_int(value: Any, default: int) -> int:
    return value if isinstance(value, int) else default


def _coerce_short_term_turn(
    data: Any,
    *,
    role_default: str = "system",
) -> tuple[str, list[ContentBlock]] | None:
    if isinstance(data, str):
        return role_default, [text_block(data)]
    if isinstance(data, dict):
        role = str(data.get("role", role_default))
        content = data.get("content") or data.get("summary") or str(data)
        return role, [text_block(str(content))]
    return None


def build_store_handlers(
    sensory: SensoryMemoryProtocol,
    short_term: ShortTermMemoryProtocol,
    long_term: LongTermMemoryProtocol,
) -> dict[str, Callable[[Any], None]]:
    """stream ごとの保存ハンドラを構築する。"""

    def _store_sensory(data: Any) -> None:
        if isinstance(data, dict) and data.get("raw"):
            sensory.store_raw(str(data["raw"]))
        else:
            sensory.add_fragment(str(data), is_final=True)

    def _store_short_term(data: Any) -> None:
        scope = StoreScope.of(data)
        coerced = _coerce_short_term_turn(data)
        if coerced is None:
            return
        role, blocks = coerced
        short_term.add_turn(role, blocks, room_id=scope.room_id, account_id=scope.account_id)

    def _store_episodic(data: Any) -> None:
        scope = StoreScope.of(data)
        if scope.room_id or scope.account_id:
            long_term.store_episodic(
                data,
                kind="",
                room_id=scope.room_id,
                account_id=scope.account_id,
            )
        else:
            long_term.store_episodic(data)
        coerced = _coerce_short_term_turn(data, role_default="system")
        if coerced is not None:
            role, blocks = coerced
            short_term.add_turn(role, blocks, account_id=scope.account_id)

    def _store_semantic(data: Any) -> None:
        scope = StoreScope.of(data)
        if scope.room_id or scope.account_id:
            long_term.store_semantic(
                data,
                room_id=scope.room_id,
                account_id=scope.account_id,
            )
        else:
            long_term.store_semantic(data)
        if isinstance(data, dict):
            content = str(data.get("content", ""))
            if content:
                short_term.add_turn("system", [text_block(content)], account_id=scope.account_id)

    return {
        "sensory": _store_sensory,
        "short_term": _store_short_term,
        "episodic": _store_episodic,
        "semantic": _store_semantic,
    }


def dispatch_retrieve(
    stream: str,
    filters: dict[str, Any],
    sensory: SensoryMemoryProtocol,
    short_term: ShortTermMemoryProtocol,
    long_term: LongTermMemoryProtocol,
    room_id: str = "",
    account_id: str = "",
) -> list[dict[str, Any]]:
    if stream == "sensory":
        snapshot = sensory.retrieve()
        return [snapshot.model_dump()] if snapshot.fragments or snapshot.raw else []
    n = _extract_int(filters.get("n"), 5)
    if stream == "short_term":
        return [t.model_dump() for t in short_term.get_recent_turns(n, room_id=room_id, account_id=account_id)]
    if stream == "episodic":
        return long_term.get_episodic_recent(n, room_id=room_id, account_id=account_id)
    return []


def dispatch_search(
    query: str,
    stream: str | None,
    kwargs: dict[str, Any],
    short_term: ShortTermMemoryProtocol,
    long_term: LongTermMemoryProtocol,
    room_id: str = "",
    account_id: str = "",
) -> list[dict[str, Any]]:
    max_results = _extract_int(kwargs.get("max_results"), 3)
    if stream == "short_term":
        return [
            r.model_dump()
            for r in short_term.search(query, max_results=max_results, room_id=room_id, account_id=account_id)
        ]
    if stream == "semantic" or stream is None:
        return long_term.search_semantic(query, max_results=max_results, room_id=room_id, account_id=account_id)
    return []


def dispatch_clear(
    stream: str | None,
    sensory: SensoryMemoryProtocol,
    short_term: ShortTermMemoryProtocol,
    long_term: LongTermMemoryProtocol,
    room_id: str = "",
) -> None:
    logger.info("MemoryManager: clear stream={}", stream or "all")
    if stream == "sensory" or stream is None:
        sensory.clear()
    if stream == "short_term" or stream is None:
        short_term.clear()
    if stream == "episodic" or stream is None:
        long_term.clear_episodic()
    if stream == "semantic" or stream is None:
        long_term.clear_semantic()


__all__ = [
    "StoreScope",
    "build_store_handlers",
    "dispatch_clear",
    "dispatch_retrieve",
    "dispatch_search",
]
