from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from loguru import logger

from iris.memory.dispatcher import (
    build_store_handlers,
    dispatch_clear,
    dispatch_retrieve,
    dispatch_search,
)
from iris.memory.long_term.goal_store import GoalStore
from iris.memory.long_term.protocol import LongTermMemoryProtocol
from iris.memory.protocol import MemoryManagerProtocol
from iris.memory.sensory.protocol import SensoryMemoryProtocol
from iris.memory.short_term.protocol import ShortTermMemoryProtocol

if TYPE_CHECKING:
    from iris.memory.archive.store import RawConversationArchiveStore
    from iris.memory.langmem.pipeline import MemoryPipeline
    from iris.memory.langmem.scheduler import MemoryPipelineScheduler


class MemoryManager(MemoryManagerProtocol):
    """記憶マネージャー — 各記憶種別の管理クラスへのディスパッチャ。

    脳科学に基づく3層構造:
    - SensoryMemoryManager   (感覚記憶): 生入力の一時保持
    - ShortTermMemoryManager (短期記憶): 現在の会話内容（ワーキングメモリ）
    - LongTermMemoryManager  (長期記憶): エピソード記憶 + 意味記憶

    このクラスは以下を責務とする:
    1. イベント処理 (pending / timer / InputReady)
    2. store() / retrieve() / search() / clear() のディスパッチ
    3. 後方互換 API (add_episodic, get_recent, 等)
    """

    def __init__(
        self,
        *,
        sensory: SensoryMemoryProtocol | None = None,
        short_term: ShortTermMemoryProtocol | None = None,
        long_term: LongTermMemoryProtocol | None = None,
        archive: RawConversationArchiveStore | None = None,
        pipeline: MemoryPipeline | None = None,
        pipeline_scheduler: MemoryPipelineScheduler | None = None,
    ) -> None:
        from iris.memory.long_term.manager import LongTermMemoryManager
        from iris.memory.sensory.manager import SensoryMemoryManager
        from iris.memory.short_term.manager import ShortTermMemoryManager

        self.sensory: SensoryMemoryProtocol = sensory or SensoryMemoryManager()
        self.short_term: ShortTermMemoryProtocol = short_term or ShortTermMemoryManager()
        self.long_term: LongTermMemoryProtocol = long_term or LongTermMemoryManager()
        self.goals: GoalStore = GoalStore()
        self.archive = archive
        self.pipeline = pipeline
        self._pipeline_scheduler: MemoryPipelineScheduler | None = pipeline_scheduler
        if self._pipeline_scheduler is None and pipeline is not None:
            from iris.memory.langmem.scheduler import MemoryPipelineScheduler

            self._pipeline_scheduler = MemoryPipelineScheduler(pipeline)

        # 同期コンテキスト (イベントループ無し) で flush されたとき、抽出処理は
        # チャット応答を 5-30 秒ブロックする危険がある。scheduler が走れない時は
        # dirty 集合に積むだけで即座に返し、次にイベントループが回った時に
        # まとめて drain する。
        self._pipeline_dirty_scopes: set[tuple[str, str]] = set()

        self._store_handlers: dict[str, Callable[[Any], None]] = build_store_handlers(
            self.sensory,
            self.short_term,
            self.long_term,
        )

    def get_state(self) -> dict:
        from iris.memory.protocol import safe_count

        episodic_count = safe_count(self.long_term.episodic) if self.long_term else 0
        semantic_count = safe_count(self.long_term.semantic) if self.long_term else 0
        return {
            "episodic": episodic_count,
            "semantic": semantic_count,
            "short_term_turns": self.short_term.turn_count if self.short_term else 0,
        }

    def set_sensory_buffer(self, buf: Any) -> None:
        self.sensory = buf

    def store(self, stream: str, data: Any, room_id: str = "", account_id: str = "") -> None:
        logger.info("MemoryManager: store stream={}", stream)
        if isinstance(data, dict):
            if room_id:
                data.setdefault("room_id", room_id)
            if account_id:
                data.setdefault("account_id", account_id)
        handler = self._store_handlers.get(stream)
        if handler is not None:
            handler(data)
        else:
            logger.warning("MemoryManager: unknown stream={}", stream)

    def retrieve(self, stream: str, room_id: str = "", account_id: str = "", **filters: Any) -> list[dict[str, Any]]:
        return dispatch_retrieve(
            stream, filters, self.sensory, self.short_term, self.long_term, room_id=room_id, account_id=account_id
        )

    def search(
        self, query: str, stream: str | None = None, room_id: str = "", account_id: str = "", **kwargs: Any
    ) -> list[dict[str, Any]]:
        return dispatch_search(
            query, stream, kwargs, self.short_term, self.long_term, room_id=room_id, account_id=account_id
        )

    def clear(self, stream: str | None = None, room_id: str = "") -> None:
        dispatch_clear(stream, self.sensory, self.short_term, self.long_term)

    def flush(self, room_id: str = "", account_id: str = "") -> None:
        """未定着の短期記憶を長期記憶に書き出してからクリアする。

        LangMem pipeline が設定されていれば、``batch_min_turns`` を超えるターン数が
        未定着のときバックグラウンド的に抽出を試みる。失敗しても会話を止めない。
        """
        unconsolidated = self.short_term.get_unconsolidated_turns(account_id=account_id)
        if not unconsolidated:
            return

        user_turns = [t for t in unconsolidated if t.role == "user"]
        if user_turns:
            combined = " | ".join(t.text[:100] for t in user_turns[-3:])
            self.long_term.store_episodic(
                {"content": f"[conversation] {combined}", "kind": "conversation"},
                room_id=room_id,
                account_id=account_id,
            )

        topics = self.short_term.current_topics
        for topic in topics:
            self.long_term.store_semantic(
                {"content": topic, "type": "topic", "tags": ["short_term_topic"]},
                room_id=room_id,
                account_id=account_id,
            )

        self.short_term.mark_consolidated(room_id=room_id, account_id=account_id)
        logger.info("MemoryManager: flushed {} turns, {} topics", len(unconsolidated), len(topics))

        self._maybe_run_pipeline(len(unconsolidated), room_id=room_id, account_id=account_id)

    def archive_inbound(
        self,
        content: str,
        *,
        account_id: str = "",
        room_id: str = "",
        session_id: str = "",
        source: str = "",
        message_type: str = "chat",
    ) -> None:
        """入力メッセージをアーカイブするショートカット。"""
        if self.archive is None:
            return
        from iris.memory.archive.models import ConversationRecord

        self.archive.append(
            ConversationRecord(
                direction="inbound",
                role="user",
                content=content,
                account_id=account_id,
                room_id=room_id,
                session_id=session_id,
                source=source,
                message_type=message_type,
            )
        )

    def archive_outbound(
        self,
        content: str,
        *,
        account_id: str = "",
        room_id: str = "",
        session_id: str = "",
        source: str = "assistant",
    ) -> None:
        """アシスタント応答をアーカイブするショートカット。"""
        if self.archive is None:
            return
        from iris.memory.archive.models import ConversationRecord

        self.archive.append(
            ConversationRecord(
                direction="outbound",
                role="assistant",
                content=content,
                account_id=account_id,
                room_id=room_id,
                session_id=session_id,
                source=source,
                message_type="chat",
            )
        )

    def _maybe_run_pipeline(
        self,
        turn_count: int,
        *,
        room_id: str = "",
        account_id: str = "",
    ) -> None:
        pipeline = self.pipeline
        if pipeline is None or not getattr(pipeline, "enabled", False):
            return
        try:
            min_turns = int(pipeline._config.batch_min_turns)
        except Exception:
            min_turns = 6
        if turn_count < min_turns:
            return

        scheduler = self._pipeline_scheduler
        scope = (account_id, room_id)
        if scheduler is None:
            return

        # まず前回同期コンテキストで dirty に積まれた scope を drain する
        if self._pipeline_dirty_scopes:
            for acc, rm in list(self._pipeline_dirty_scopes):
                if scheduler.is_already_running(acc, rm):
                    self._pipeline_dirty_scopes.discard((acc, rm))
                    continue
                try:
                    task = scheduler.schedule_full_cycle(account_id=acc, room_id=rm)
                except Exception as e:
                    logger.debug("MemoryManager: scheduler drain failed: {}", e)
                    continue
                if task is not None:
                    self._pipeline_dirty_scopes.discard((acc, rm))
                # task is None = イベントループが無い → dirty に残す

        # 1) イベントループがあれば非同期スケジュール (同一 scope の重複を抑止)
        if not scheduler.is_already_running(account_id, room_id):
            try:
                task = scheduler.schedule_full_cycle(
                    account_id=account_id,
                    room_id=room_id,
                )
            except Exception as e:
                logger.debug("MemoryManager: scheduler schedule failed: {}", e)
                return
            if task is not None:
                return
            # イベントループが無い → 同期ブロックを避けるため dirty に積むだけ
            self._pipeline_dirty_scopes.add(scope)
            logger.debug(
                "MemoryManager: pipeline run deferred (no event loop) account={} room={}",
                account_id,
                room_id,
            )
            return

        # 2) 既に同一 scope が走っているなら何もしない
        return

    def get_user_preferences(self, room_id: str = "", account_id: str = "") -> list[dict[str, Any]]:
        return self.long_term.search_semantic(
            "ユーザーの好み 興味 趣味", max_results=2, room_id=room_id, account_id=account_id
        )

    def add_episodic(
        self, content: str, kind: str = "", _metadata: dict | None = None, room_id: str = "", account_id: str = ""
    ) -> None:
        self.store("episodic", {"content": content, "kind": kind}, room_id=room_id, account_id=account_id)

    def get_recent(self, n: int = 3, room_id: str = "", account_id: str = "") -> list[dict[str, Any]]:
        return self.long_term.get_episodic_recent(n, room_id=room_id, account_id=account_id)

    def add_semantic(
        self, content: str, tags: list[str] | None = None, room_id: str = "", account_id: str = ""
    ) -> None:
        self.store("semantic", {"content": content, "tags": tags or []}, room_id=room_id, account_id=account_id)

    def add_semantic_by_type(
        self, entry_type: str, content: str, tags: list[str] | None = None, room_id: str = "", account_id: str = ""
    ) -> None:
        self.store(
            "semantic",
            {"content": content, "type": entry_type, "tags": tags or []},
            room_id=room_id,
            account_id=account_id,
        )

    def search_semantic(
        self, query: str, max_results: int = 3, room_id: str = "", account_id: str = ""
    ) -> list[dict[str, Any]]:
        return self.long_term.search_semantic(query, max_results=max_results, room_id=room_id, account_id=account_id)

    def search_emotional(
        self,
        current_emotion: Any | None = None,
        max_results: int = 5,
        room_id: str = "",
    ) -> list[dict[str, Any]]:
        return self.long_term.search_emotional(
            current_emotion=current_emotion, max_results=max_results, room_id=room_id
        )
