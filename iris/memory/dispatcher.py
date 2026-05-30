from __future__ import annotations

from collections.abc import Callable
from typing import Any

from loguru import logger

from iris.memory.models import text_block


def build_store_handlers(
    sensory: Any,
    short_term: Any,
    long_term: Any,
) -> dict[str, Callable[[Any], None]]:
    return {
        "sensory": lambda data: _store_sensory(sensory, data),
        "short_term": lambda data: _store_short_term(short_term, data),
        "episodic": lambda data: _store_episodic(
            long_term, short_term, data,
            data.get("room_id", "") if isinstance(data, dict) else "",
            data.get("account_id", "") if isinstance(data, dict) else "",
        ),
        "semantic": lambda data: _store_semantic(
            long_term, short_term, data,
            data.get("room_id", "") if isinstance(data, dict) else "",
            data.get("account_id", "") if isinstance(data, dict) else "",
        ),
    }


def _store_sensory(sensory: Any, data: Any) -> None:
    if isinstance(data, dict) and data.get("raw"):
        sensory.store_raw(data["raw"])
    else:
        sensory.add_fragment(str(data), is_final=True)


def _store_short_term(short_term: Any, data: Any) -> None:
    if isinstance(data, str):
        short_term.add_turn("system", [text_block(data)])
    elif isinstance(data, dict):
        role = data.get("role", "system")
        content = data.get("content") or data.get("summary") or str(data)
        short_term.add_turn(role, [text_block(content)])


def _store_episodic(long_term: Any, short_term: Any, data: Any, room_id: str = "", account_id: str = "") -> None:
    long_term.store_episodic(data, room_id, account_id=account_id)
    if isinstance(data, dict):
        short_term.add_turn(
            "system",
            [text_block(data.get("content") or data.get("summary") or str(data))],
            account_id=account_id,
        )


def _store_semantic(long_term: Any, short_term: Any, data: Any, room_id: str = "", account_id: str = "") -> None:
    long_term.store_semantic(data, room_id, account_id=account_id)
    if isinstance(data, dict):
        content = data.get("content", "")
        if content:
            short_term.add_turn("system", [text_block(content)], account_id=account_id)


def dispatch_retrieve(
    stream: str,
    filters: dict[str, Any],
    sensory: Any,
    short_term: Any,
    long_term: Any,
    room_id: str = "",
    account_id: str = "",
) -> list[dict[str, Any]]:
    if stream == "sensory":
        result = sensory.retrieve()
        return [result] if result else []
    n = filters.get("n", 5) if isinstance(filters.get("n"), int) else 5
    if stream == "short_term":
        return short_term.get_recent_turns(n, account_id=account_id)  # type: ignore[no-any-return]
    if stream == "episodic":
        return long_term.get_episodic_recent(n, account_id=account_id)  # type: ignore[no-any-return]
    return []


def dispatch_search(
    query: str,
    stream: str | None,
    kwargs: dict[str, Any],
    short_term: Any,
    long_term: Any,
    room_id: str = "",
    account_id: str = "",
) -> list[dict[str, Any]]:
    max_results = kwargs.get("max_results", 3) if isinstance(kwargs.get("max_results"), int) else 3
    if stream == "short_term":
        return short_term.search(query, max_results=max_results, account_id=account_id)  # type: ignore[no-any-return]
    if stream == "semantic" or stream is None:
        return long_term.search_semantic(query, max_results=max_results, account_id=account_id)  # type: ignore[no-any-return]
    return []


def dispatch_clear(
    stream: str | None,
    sensory: Any,
    short_term: Any,
    long_term: Any,
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
