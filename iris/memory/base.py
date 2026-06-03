from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import threading
from typing import Any

from loguru import logger
import orjson
from pydantic import BaseModel


class _JsonlStore:
    """JSONLファイルの読み書きを提供する基底クラス（生のdict操作用）。"""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._cache: list[dict[str, Any]] | None = None

    def load_all(self) -> list[dict[str, Any]]:
        if self._cache is not None:
            return self._cache
        if not self.path.exists():
            self._cache = []
            return []
        entries: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entries.append(orjson.loads(line.encode("utf-8")))
            except orjson.JSONDecodeError:
                logger.warning("{}: skipping corrupt entry: {:.80}", type(self).__name__, line)
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
        self._cache = None

    def _add_entry(self, entry: dict[str, Any], max_entries: int) -> None:
        with self._lock:
            entries = self.load_all()
            entries.append(entry)
            if len(entries) > max_entries:
                entries = entries[-max_entries:]
            self._cache = entries
            self._flush()


class _IdIndexedJsonlStore[T: BaseModel]:
    """ID をキーにした append/update/list 可能な JSONL ストア（モデル型付き）。"""

    def __init__(self, path: str, model_cls: type[T]) -> None:
        self._store = _JsonlStore(path)
        self.model_cls = model_cls

    @property
    def path(self) -> Path:
        return self._store.path

    def _load(self) -> list[dict[str, Any]]:
        return self._store.load_all()

    def _flush(self) -> None:
        self._store._flush()

    def add(self, item: T) -> T:
        data = item.model_dump(mode="python")
        with self._store._lock:
            entries = self._store.load_all()
            entries.append(data)
            self._store._cache = entries
            self._store._flush()
        return item

    def update(self, item_id: str, **changes: Any) -> T | None:
        with self._store._lock:
            entries = self._store.load_all()
            for entry in entries:
                if entry.get("id") == item_id:
                    entry.update(changes)
                    entry["updated_at"] = datetime.now(UTC).isoformat()
                    self._store._cache = entries
                    self._store._flush()
                    return self.model_cls.model_validate(entry)
            return None

    def find(self, item_id: str) -> T | None:
        for e in self._store.load_all():
            if e.get("id") == item_id:
                return self.model_cls.model_validate(e)
        return None

    def list_all(self) -> list[T]:
        return [self.model_cls.model_validate(e) for e in self._store.load_all()]

    def list_filtered(self, **filters: Any) -> list[T]:
        return [
            self.model_cls.model_validate(e)
            for e in self._store.load_all()
            if all(e.get(k) == v for k, v in filters.items())
        ]

    def count(self, **filters: Any) -> int:
        return sum(1 for e in self._store.load_all() if all(e.get(k) == v for k, v in filters.items()))
