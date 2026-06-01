"""Archive event handler — MessageEvent / 完了イベントから RawArchive に追記する。"""

from __future__ import annotations

from typing import Any

from loguru import logger

from iris.io.events import MessageEvent
from iris.memory.archive.models import ConversationRecord
from iris.memory.archive.store import RawConversationArchiveStore


class ArchiveEventHandler:
    """MessageEvent を購読し、入出力を Archive に追記するハンドラ。"""

    def __init__(
        self,
        event_bus: Any,
        archive: RawConversationArchiveStore,
        *,
        include_outbound: bool = True,
    ) -> None:
        self.event_bus = event_bus
        self._archive = archive
        self._include_outbound = include_outbound
        if event_bus is not None:
            event_bus.subscribe(MessageEvent, self._on_message_event)

    def _on_message_event(self, event: MessageEvent) -> None:
        if not event.content:
            return
        if event.direction == "request" and event.msg_type in ("chat", "system"):
            self._archive_inbound(event)
        elif event.direction == "response" and self._include_outbound:
            self._archive_outbound(event)

    def archive_response_text(
        self,
        text: str,
        *,
        account_id: str = "",
        room_id: str = "",
        session_id: str = "",
        source: str = "assistant.final",
    ) -> None:
        """アシスタントの最終応答を Archive に書き込むためのフック。

        streaming のたびに呼ばず、最終確定後に 1 回だけ呼ぶこと。
        """
        if not text:
            return
        rec = ConversationRecord(
            direction="outbound",
            role="assistant",
            content=text,
            account_id=account_id,
            room_id=room_id,
            session_id=session_id,
            source=source,
            message_type="chat",
        )
        self._archive.append(rec)

    def _archive_inbound(self, event: MessageEvent) -> None:
        rec = ConversationRecord(
            direction="inbound",
            role="user",
            content=event.content,
            account_id=event.account_id,
            room_id=event.room_id,
            session_id=event.session_id,
            source=event.source_role or event.source or "",
            message_type=event.msg_type,
        )
        self._archive.append(rec)
        logger.debug("Archive: inbound message archived (room={})", event.room_id)

    def _archive_outbound(self, event: MessageEvent) -> None:
        rec = ConversationRecord(
            direction="outbound",
            role="assistant",
            content=event.content,
            account_id=event.account_id,
            room_id=event.room_id,
            session_id=event.session_id,
            source=event.source_role or event.source or "assistant",
            message_type=event.msg_type,
        )
        self._archive.append(rec)
        logger.debug("Archive: outbound message archived (room={})", event.room_id)


__all__ = ["ArchiveEventHandler"]
