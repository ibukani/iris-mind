from __future__ import annotations

from collections.abc import Callable
from typing import Any

from iris.memory.models import system_event_block


class RoomEventHandler:
    """入退室イベントの処理を担当する。

    責務:
    - RoomJoinedEvent / RoomJoinedBatchEvent / RoomLeftEvent の処理
    - ユーザー追跡の更新 (short_term.add_user / remove_user)
    - system_event_block の生成と flush
    """

    def __init__(
        self,
        sensory: Any,
        short_term: Any,
        store_and_flush_block: Callable[[Any, str, str], None],
    ) -> None:
        self._sensory = sensory
        self._short_term = short_term
        self._store_and_flush_block = store_and_flush_block

    def handle_joined(self, event: Any) -> None:
        self._sync_membership(event.account_id, event.display_name, event.room_id, joined=True)
        self._store_and_flush_block(
            system_event_block(
                f"[system] {event.display_name} が入室しました",
                event_type="room.joined",
                account_id=event.account_id,
                display_name=event.display_name,
                room_id=event.room_id,
            ),
            event.account_id,
            event.room_id,
        )

    def handle_joined_batch(self, event: Any) -> None:
        if not event.joins:
            return
        for join in event.joins:
            self._sync_membership(join.account_id, join.display_name, join.room_id, joined=True)
        first = event.joins[0]
        join_count = len(event.joins)
        if join_count > 1:
            text = f"[system] {first.display_name} 他{join_count - 1}名が入室しました"
        else:
            text = f"[system] {first.display_name} が入室しました"
        self._store_and_flush_block(
            system_event_block(
                text,
                event_type="room.joined",
                account_id=first.account_id,
                display_name=first.display_name,
                room_id=first.room_id,
            ),
            first.account_id,
            first.room_id,
        )

    def handle_left(self, event: Any) -> None:
        self._sync_membership(event.account_id, event.display_name, event.room_id, joined=False)
        self._store_and_flush_block(
            system_event_block(
                f"[system] {event.display_name} が退室しました",
                event_type="room.left",
                account_id=event.account_id,
                display_name=event.display_name,
                room_id=event.room_id,
            ),
            event.account_id,
            event.room_id,
        )

    def _sync_membership(self, account_id: str, display_name: str, room_id: str, *, joined: bool) -> None:
        if not self._short_term:
            return
        if joined:
            self._short_term.add_user(account_id, display_name, room_id=room_id)
        else:
            self._short_term.remove_user(account_id, room_id=room_id)
