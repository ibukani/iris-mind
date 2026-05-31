from __future__ import annotations

from collections.abc import Callable
import threading
from typing import Any

from iris.io.events import InputReady, InterruptEvent
from iris.memory.models import ContentBlock
from iris.memory.sensory.assembler import SensoryMemoryAssembler
from iris.memory.sensory.models import PendingInputEntry, PendingInputKey, RawInput, SensorySnapshot
from iris.memory.sensory.protocol import SensoryMemoryProtocol
from iris.memory.sensory.readiness import ReadinessEvaluator
from iris.memory.sensory.store import SensoryStore


class SensoryMemoryManager(SensoryMemoryProtocol):
    """感覚記憶 (Sensory Memory)。
    生の入力を処理前に一時保持する。

    内部で SensoryStore (状態保持用) と SensoryMemoryAssembler (断片の制御用) に処理を委譲する。
    """

    def __init__(
        self,
        timeout_ms: int = 800,
        max_fragments: int = 10,
        event_bus: Any = None,
    ) -> None:
        self._store = SensoryStore()
        self._assembler = SensoryMemoryAssembler(
            store=self._store,
            timeout_ms=timeout_ms,
            max_fragments=max_fragments,
        )
        self.event_bus = event_bus
        self._lock = threading.RLock()

    # ---- fragment mode ----

    def set_flush_callback(self, callback: Callable[[str, list[ContentBlock]], None]) -> None:
        self._assembler.set_flush_callback(callback)

    def set_readiness_evaluator(self, evaluator: ReadinessEvaluator) -> None:
        self._assembler.set_readiness_evaluator(evaluator)

    def add_fragment(self, content: str, is_final: bool, room_id: str = "") -> None:
        self._assembler.add_fragment(content, is_final, room_id)

    def add_fragment_block(self, block: ContentBlock, is_final: bool, room_id: str = "") -> None:
        self._assembler.add_fragment_block(block, is_final, room_id)

    def flush(self, room_id: str = "") -> None:
        self._assembler.flush(room_id)

    def cancel(self, room_id: str | None = None) -> None:
        with self._lock:
            self._assembler.cancel(room_id)
            self._store.clear(room_id)

    def clear(self, room_id: str | None = None) -> None:
        with self._lock:
            self._assembler.clear(room_id)
            self._store.clear(room_id)

    def clear_raw(self, room_id: str | None = None) -> None:
        self._store.clear(room_id)

    def close(self) -> None:
        with self._lock:
            self._assembler.close()
            self._store.clear()

    # ---- raw input mode ----

    def store_raw(self, content: str, room_id: str = "", account_id: str = "", session_id: str = "") -> None:
        self._store.store_raw_block(
            block={"type": "text", "text": content},
            room_id=room_id,
            account_id=account_id,
            session_id=session_id,
        )

    def store_raw_block(
        self, block: ContentBlock, room_id: str = "", account_id: str = "", session_id: str = ""
    ) -> None:
        self._store.store_raw_block(block, room_id=room_id, account_id=account_id, session_id=session_id)

    def retrieve(self, room_id: str = "") -> SensorySnapshot:
        with self._lock:
            return self._store.retrieve(room_id)

    def take_raw(self, room_id: str = "") -> RawInput | None:
        with self._lock:
            return self._store.take_raw(room_id)

    def add_pending_input(self, account_id: str, room_id: str, content: str) -> None:
        self._store.add_pending_input(account_id, room_id, content)

    def take_pending_input(self) -> dict[PendingInputKey, list[PendingInputEntry]]:
        return self._store.take_pending_input()

    def clear_pending_input(self) -> None:
        self._store.clear_pending_input()

    def flush_pending(self) -> dict[PendingInputKey, list[PendingInputEntry]]:
        pending = self.take_pending_input()
        if not pending:
            return {}
        bus = self.event_bus
        if bus is not None:
            for entries in pending.values():
                for entry in entries:
                    bus.publish(
                        InterruptEvent(
                            timestamp=None,
                            source="memory",
                            room_id=entry.room_id,
                        ),
                    )
                    bus.publish(
                        InputReady(
                            timestamp=None,
                            source="memory",
                            content=entry.content,
                            account_id=entry.account_id,
                            room_id=entry.room_id,
                            context={},
                        ),
                    )
        return pending

    def store_and_flush_pending_block(
        self,
        block: ContentBlock,
        account_id: str,
        room_id: str = "",
    ) -> None:
        self.store_raw_block(block, room_id=room_id, account_id=account_id)
        self.add_pending_input(account_id, room_id, block.get("text", ""))
        self.flush_pending()
        self.clear_raw(room_id)

    def has_pending_raw(self, room_id: str = "") -> bool:
        return self._store.retrieve(room_id).raw is not None

    @property
    def has_pending_input(self) -> bool:
        return self._store.has_pending_input

    @property
    def pending_input(self) -> dict[PendingInputKey, list[PendingInputEntry]]:
        return self._store.pending_input

    @property
    def pending_lock(self) -> Any:
        return self._store.pending_lock

    def fragment_count(self, room_id: str = "") -> int:
        return self._assembler.fragment_count(room_id)

    def accumulated_blocks(self, room_id: str = "") -> list[ContentBlock]:
        return self._assembler.accumulated_blocks(room_id)

    def get_active_room_ids(self) -> list[str]:
        return self._store.get_active_room_ids()


__all__ = ["SensoryMemoryManager", "SensoryMemoryProtocol"]


__all__ = ["SensoryMemoryManager", "SensoryMemoryProtocol"]
