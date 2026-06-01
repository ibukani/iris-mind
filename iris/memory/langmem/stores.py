"""MemoryExtractionJobStore / MemoryCandidateStore — ジョブと候補の JSONL 永続化。

通常の ``_JsonlStore`` と異なり、ID 指定で更新・検索できる。
テスト容易性のためインスタンス間で共有しない。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import threading
from typing import Any, TypeVar

from loguru import logger
import orjson
from pydantic import BaseModel

from iris.memory.langmem.models import MemoryCandidate, MemoryExtractionJob

T = TypeVar("T", bound=BaseModel)


class _IdIndexedJsonlStore[T: BaseModel]:
    """ID をキーにした append/update/list 可能な JSONL ストア。"""

    model_cls: type[BaseModel]

    def __init__(self, path: str, model_cls: type[T]) -> None:
        self.path = Path(path)
        self.model_cls = model_cls
        self._lock = threading.Lock()
        self._cache: list[dict[str, Any]] | None = None

    def _load(self) -> list[dict[str, Any]]:
        if self._cache is not None:
            return self._cache
        if not self.path.exists():
            self._cache = []
            return self._cache
        entries: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entries.append(orjson.loads(line.encode("utf-8")))
            except orjson.JSONDecodeError as e:
                logger.warning("{}: skipping corrupt line: {}", type(self).__name__, e)
        self._cache = entries
        return entries

    def _flush(self) -> None:
        assert self._cache is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            "\n".join(orjson.dumps(e).decode("utf-8") for e in self._cache),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def add(self, item: T) -> T:
        with self._lock:
            entries = self._load()
            data = item.model_dump(mode="python")
            entries.append(data)
            self._cache = entries
            self._flush()
        return item

    def update(self, item_id: str, **changes: Any) -> T | None:
        with self._lock:
            entries = self._load()
            for entry in entries:
                if entry.get("id") == item_id:
                    entry.update(changes)
                    entry["updated_at"] = datetime.now(UTC).isoformat()
                    self._cache = entries
                    self._flush()
                    return self.model_cls.model_validate(entry)  # type: ignore[return-value]
        return None

    def find(self, item_id: str) -> T | None:
        for e in self._load():
            if e.get("id") == item_id:
                return self.model_cls.model_validate(e)  # type: ignore[return-value]
        return None

    def list_all(self) -> list[T]:
        return [self.model_cls.model_validate(e) for e in self._load()]  # type: ignore[misc]

    def list_filtered(self, **filters: Any) -> list[T]:
        return [
            self.model_cls.model_validate(e)  # type: ignore[misc]
            for e in self._load()
            if all(e.get(k) == v for k, v in filters.items())
        ]

    def count(self, **filters: Any) -> int:
        return sum(1 for e in self._load() if all(e.get(k) == v for k, v in filters.items()))


class MemoryExtractionJobStore(_IdIndexedJsonlStore[MemoryExtractionJob]):
    """LangMem 抽出ジョブの永続ストア。"""

    def __init__(self, path: str) -> None:
        super().__init__(path, MemoryExtractionJob)


class MemoryCandidateStore(_IdIndexedJsonlStore[MemoryCandidate]):
    """LangMem 出力を保持する候補ストア。PromotionPolicy の入力。"""

    def __init__(self, path: str) -> None:
        super().__init__(path, MemoryCandidate)


__all__ = ["MemoryCandidateStore", "MemoryExtractionJobStore"]
