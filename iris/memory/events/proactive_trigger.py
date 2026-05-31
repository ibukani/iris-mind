from __future__ import annotations

from typing import Any


class ProactiveTrigger:
    """プロアクティブ発話のトリガー判定を担当する。

    責務:
    - アイドル状態でのプロアクティブ入力 (InputReady) の publish
    - 最もアクティブな Room の選択
    """

    def __init__(self, event_bus: Any, room_provider: Any) -> None:
        self._event_bus = event_bus
        self._room_provider = room_provider

    def publish(self) -> None:
        from iris.io.events import InputReady

        room_id = self._select_room()
        self._event_bus.publish(
            InputReady(
                timestamp=None,
                source="memory",
                session_id="",
                room_id=room_id,
                content="",
                context={"from_timer": True},
            ),
        )

    def _select_room(self) -> str:
        if not self._room_provider:
            return ""
        rooms = self._room_provider.list_rooms()
        if not rooms:
            default = self._room_provider.get_default_room()
            return default.room_id if default else ""
        best_room = None
        best_active: str | None = None
        for room in rooms:
            members = self._room_provider.get_members(room.room_id)
            for m in members:
                if m.is_active and (best_active is None or (m.last_active or "") > (best_active or "")):
                    best_active = m.last_active
                    best_room = room
        if best_room:
            return str(best_room.room_id)
        default = self._room_provider.get_default_room()
        return default.room_id if default else ""
