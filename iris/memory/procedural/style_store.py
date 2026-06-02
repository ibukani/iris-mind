"""StyleMemoryStore — スタイル記憶の永続ストア。"""

from __future__ import annotations

from typing import Any

from iris.memory.langmem.stores import _IdIndexedJsonlStore
from iris.memory.procedural.models import StyleMemory
from iris.memory.procedural.style_index import StyleMemoryIndex


class StyleMemoryStore(_IdIndexedJsonlStore[StyleMemory]):
    def __init__(
        self,
        path: str,
        *,
        index: StyleMemoryIndex | None = None,
    ) -> None:
        super().__init__(path, StyleMemory)
        # ``index`` は外部から ``search()`` 経由で利用される。
        # 指定が無ければ store 自身の ``list_enabled`` が使われる。
        self._index: StyleMemoryIndex | None = index

    @property
    def index(self) -> StyleMemoryIndex | None:
        return self._index

    def set_index(self, index: StyleMemoryIndex) -> None:
        """後からインデックスを差し替える。"""
        self._index = index

    def list_enabled(
        self,
        *,
        account_id: str = "",
        room_id: str = "",
        max_items: int = 8,
    ) -> list[StyleMemory]:
        items: list[StyleMemory] = []
        for m in self.list_all():
            if not m.enabled:
                continue
            if m.scope == "room" and m.room_id and m.room_id != room_id:
                continue
            if m.scope == "account" and m.account_id and m.account_id != account_id:
                continue
            items.append(m)
        items.sort(key=lambda m: (m.confidence, m.success_count - m.failure_count), reverse=True)
        return items[:max_items]

    def search(
        self,
        *,
        query: str = "",
        account_id: str = "",
        room_id: str = "",
        max_items: int = 8,
    ) -> list[StyleMemory]:
        """インデックスが設定されていればそちらを使う。なければ ``list_enabled`` と同じ結果。"""
        if self._index is not None:
            return self._index.search(
                query=query,
                account_id=account_id,
                room_id=room_id,
                max_items=max_items,
            )
        return self.list_enabled(
            account_id=account_id,
            room_id=room_id,
            max_items=max_items,
        )

    def record_usage(self, item_id: str, *, success: bool) -> StyleMemory | None:
        m = self.find(item_id)
        if m is None:
            return None
        if success:
            m.success_count += 1
        else:
            m.failure_count += 1
        from datetime import UTC, datetime

        m.last_used_at = datetime.now(UTC).isoformat()
        return self.update(item_id, **m.model_dump(mode="python"))


__all__ = ["StyleMemoryStore"]


# silence unused import warning
_ = Any
