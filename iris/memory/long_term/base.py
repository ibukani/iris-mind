from __future__ import annotations

from pathlib import Path
import threading

from loguru import logger
import orjson
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


class _JsonlStore:
    """JSONLファイルの読み書きを提供する基底クラス。"""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._load_cache: list[dict] | None = None

    def load_all(self) -> list[dict]:
        if self._load_cache is not None:
            return self._load_cache
        if not self.path.exists():
            self._load_cache = []
            return []
        entries: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                entries.append(orjson.loads(line.encode("utf-8")))
            except orjson.JSONDecodeError:
                logger.warning("{}: skipping corrupt entry: {:.80}", type(self).__name__, line)
        self._load_cache = entries
        return entries

    def _write_file(self, entries: list[dict]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            "\n".join(orjson.dumps(e).decode("utf-8") for e in entries),
            encoding="utf-8",
        )
        self._replace_atomic(tmp)
        self._load_cache = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.05, min=0.05, max=0.5),
        retry=retry_if_exception_type(PermissionError),
        reraise=True,
    )
    def _replace_atomic(self, src: Path) -> None:
        src.replace(self.path)

    def _add_entry(self, entry: dict, max_entries: int) -> None:
        with self._lock:
            entries = self.load_all()
            entries.append(entry)
            if len(entries) > max_entries:
                entries = entries[-max_entries:]
            self._write_file(entries)
