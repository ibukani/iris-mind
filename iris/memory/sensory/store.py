from __future__ import annotations

from datetime import UTC, datetime
import threading

from loguru import logger

from iris.memory.models import ContentBlock
from iris.memory.sensory.models import PendingInputEntry, PendingInputKey, RawInput, SensorySnapshot


class SensoryStore:
    """確定入力 (raw input) と断片入力 (fragment) の状態管理を行うストアクラス。

    マルチプレース対応のため、状態はルームIDをキーとする辞書で管理されます。
    """

    def __init__(self) -> None:
        self._raw_inputs: dict[str, RawInput] = {}
        self._fragments: dict[str, list[ContentBlock]] = {}
        self._pending_input: dict[PendingInputKey, list[PendingInputEntry]] = {}
        self._lock = threading.RLock()

    def store_raw_block(
        self, block: ContentBlock, room_id: str = "", account_id: str = "", session_id: str = ""
    ) -> None:
        with self._lock:
            self._raw_inputs[room_id] = RawInput(
                block=block,
                room_id=room_id,
                account_id=account_id,
                session_id=session_id,
                timestamp=datetime.now(UTC).isoformat(),
            )
        logger.debug("SensoryStore: stored raw block for room={} type={}", room_id, block.get("type", "text"))

    def take_raw(self, room_id: str = "") -> RawInput | None:
        with self._lock:
            return self._raw_inputs.pop(room_id, None)

    def retrieve(self, room_id: str = "") -> SensorySnapshot:
        with self._lock:
            return SensorySnapshot(
                room_id=room_id,
                fragments=list(self._fragments.get(room_id, [])),
                raw=self._raw_inputs.get(room_id),
            )

    def add_fragment(self, block: ContentBlock, room_id: str = "") -> None:
        with self._lock:
            if room_id not in self._fragments:
                self._fragments[room_id] = []
            self._fragments[room_id].append(block)

    def take_fragments(self, room_id: str = "") -> list[ContentBlock]:
        with self._lock:
            return self._fragments.pop(room_id, [])

    def clear(self, room_id: str | None = None) -> None:
        with self._lock:
            if room_id is not None:
                self._raw_inputs.pop(room_id, None)
                self._fragments.pop(room_id, None)
                # pending_input is keyed by PendingInputKey(account_id, room_id), so we filter it
                self._pending_input = {k: v for k, v in self._pending_input.items() if k.room_id != room_id}
            else:
                self._raw_inputs.clear()
                self._fragments.clear()
                self._pending_input.clear()

    def add_pending_input(self, account_id: str, room_id: str, content: str) -> None:
        with self._lock:
            key = PendingInputKey(account_id=account_id, room_id=room_id)
            self._pending_input[key] = [PendingInputEntry(content=content, account_id=account_id, room_id=room_id)]

    def take_pending_input(self) -> dict[PendingInputKey, list[PendingInputEntry]]:
        with self._lock:
            pending = dict(self._pending_input)
            self._pending_input.clear()
            return pending

    def clear_pending_input(self) -> None:
        with self._lock:
            self._pending_input.clear()

    @property
    def has_pending_input(self) -> bool:
        with self._lock:
            return bool(self._pending_input)

    @property
    def pending_input(self) -> dict[PendingInputKey, list[PendingInputEntry]]:
        with self._lock:
            return self._pending_input

    @property
    def pending_lock(self) -> threading.RLock:
        return self._lock

    def get_active_room_ids(self) -> list[str]:
        with self._lock:
            return list(set(self._raw_inputs.keys()) | set(self._fragments.keys()))
