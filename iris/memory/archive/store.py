"""Raw Conversation Archive Store — append-only JSONL 永続化。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import threading
from typing import Any

from loguru import logger
import orjson
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from iris.memory.archive.models import ConversationRecord
from iris.memory.archive.policy import ArchivePolicy


class RawConversationArchiveStore:
    """Append-only の会話アーカイブストア。

    設計:
    - 日付単位で ``conversations/YYYY-MM-DD.jsonl`` を作成し追記する。
    - ファイルサイズが ``max_per_file_bytes`` を超えた場合は ``YYYY-MM-DD_NN.jsonl`` にロールオーバーする。
    - 追記専用。書き換え・削除 API は公開しない。
    - 書き込み失敗時は例外を握り潰してログに記録する (メイン会話フローを止めない)。
    """

    def __init__(self, policy: ArchivePolicy | None = None) -> None:
        self._policy = policy or ArchivePolicy()
        self._lock = threading.Lock()
        self._root: Path = Path(self._policy.archive_dir)
        self._write_cache: dict[str, list[dict]] = {}

    # ── public API ──

    def append(self, record: ConversationRecord | dict[str, Any]) -> str | None:
        """レコードを append する。失敗しても例外を投げない。"""
        if not self._policy.enabled:
            return None
        try:
            payload = self._coerce(record)
            with self._lock:
                self._append_locked(payload)
            return str(payload["id"])
        except Exception as e:
            logger.warning("RawConversationArchiveStore: append failed: {}", e)
            return None

    def load_all(self) -> list[dict[str, Any]]:
        """全アーカイブを読み出して結合して返す (解析用)。"""
        if not self._root.exists():
            return []
        results: list[dict[str, Any]] = []
        for f in sorted(self._root.glob("*.jsonl")):
            try:
                lines = f.read_text(encoding="utf-8").splitlines()
            except OSError as e:
                logger.warning("RawConversationArchiveStore: failed to read {}: {}", f, e)
                continue
            for line in lines:
                if not line.strip():
                    continue
                try:
                    results.append(orjson.loads(line.encode("utf-8")))
                except orjson.JSONDecodeError as e:
                    logger.warning("RawConversationArchiveStore: skipping corrupt line in {}: {}", f, e)
                    continue
        return results

    def query_by_time(self, start: str, end: str | None = None) -> list[dict[str, Any]]:
        """ISO8601 timestamp で ``[start, end]`` 範囲のエントリを返す。"""
        end = end or "9999-12-31T23:59:59+00:00"
        return [r for r in self.load_all() if start <= r.get("timestamp", "") <= end]

    def find_by_id(self, record_id: str) -> dict[str, Any] | None:
        for r in self.load_all():
            if r.get("id") == record_id:
                return r
        return None

    @property
    def archive_dir(self) -> Path:
        return self._root

    # ── internals ──

    def _coerce(self, record: ConversationRecord | dict[str, Any]) -> dict[str, Any]:
        payload = record.to_dict() if isinstance(record, ConversationRecord) else dict(record)
        if not payload.get("id"):
            payload["id"] = self._gen_id()
        if not payload.get("timestamp"):
            payload["timestamp"] = datetime.now(UTC).isoformat()
        return payload

    def _append_locked(self, payload: dict[str, Any]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._select_file()
        with path.open("a", encoding="utf-8") as f:
            f.write(orjson.dumps(payload).decode("utf-8"))
            f.write("\n")
        self._evict_old_files_if_needed()

    def _select_file(self) -> Path:
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        prefix = date_str
        candidates = sorted(self._root.glob(f"{prefix}*.jsonl"))
        if not candidates:
            return self._root / f"{prefix}.jsonl"
        latest = candidates[-1]
        if latest.exists() and latest.stat().st_size >= self._policy.max_per_file_bytes:
            idx = 1
            for c in candidates:
                import contextlib

                if c.stem.startswith(f"{prefix}_"):
                    with contextlib.suppress(ValueError):
                        idx = max(idx, int(c.stem.split("_")[-1]) + 1)
            return self._root / f"{prefix}_{idx:02d}.jsonl"
        return latest

    def _evict_old_files_if_needed(self) -> None:
        try:
            files = sorted(self._root.glob("*.jsonl"))
            if len(files) <= self._policy.keep_recent_files:
                return
            for f in files[: -self._policy.keep_recent_files]:
                f.unlink(missing_ok=True)
        except Exception as e:
            logger.warning("RawConversationArchiveStore: evict failed: {}", e)

    @staticmethod
    def _gen_id() -> str:
        import uuid

        return str(uuid.uuid4())


# LLM bridge 互換確認用ダミー (テスト時に path を mock する)
@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=0.05, min=0.05, max=0.2),
    retry=retry_if_exception_type(PermissionError),
    reraise=True,
)
def _retry_unlink(p: Path) -> None:
    p.unlink(missing_ok=True)


__all__ = ["RawConversationArchiveStore"]
