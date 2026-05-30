from __future__ import annotations

from typing import Any

from loguru import logger
import orjson

from iris.event.event_types import ControlMessageEvent


class _RoomDispatcher:
    """ルーム管理のControlMessage振り分け＋レスポンス構築。

    責務:
    - action文字列ルーティング
    - 入力検証
    - ControlMessageEvent レスポンス構築
    """

    def __init__(self, room_manager: Any, account_manager: Any = None) -> None:
        self._room_manager = room_manager
        self._account_manager = account_manager

    def handle_control_message(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent | None:
        action = msg.action

        if action == "room.create":
            return self._handle_create(msg, session_id)
        if action == "room.list":
            return self._handle_list(msg, session_id)
        if action == "room.info":
            return self._handle_info(msg, session_id)
        if action == "room.join":
            return self._handle_join(msg, session_id)
        if action == "room.leave":
            return self._handle_leave(msg, session_id)
        if action == "room.update":
            return self._handle_update(msg, session_id)
        if action == "room.delete":
            return self._handle_delete(msg, session_id)
        if action == "room.members":
            return self._handle_members(msg, session_id)

        logger.debug("RoomDispatcher: unhandled action={}", action)
        return None

    def handle_session_disconnect(self, session_id: str) -> None:
        self._room_manager.unbind_all_for_session(session_id)

    def _handle_create(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent:
        name = msg.text.strip() if msg.text else ""
        if not name:
            return self._error("room.create", "room name required")

        account_id = msg.account_id or ""
        room = self._room_manager.create_room(name, created_by=account_id)

        return ControlMessageEvent(
            timestamp=None,
            source="room",
            action="room.created",
            room_id=room.room_id,
            account_id=account_id,
            text=f"Created room: {room.name}",
        )

    def _handle_list(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent:
        rooms = self._room_manager.list_rooms()
        data = [r.to_dict() for r in rooms]
        return ControlMessageEvent(
            timestamp=None,
            source="room",
            action="room.list",
            room_id=msg.room_id,
            account_id=msg.account_id,
            text=orjson.dumps(data).decode("utf-8"),
        )

    def _handle_info(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent:
        room_id = msg.room_id
        if not room_id:
            return self._error("room.info", "room_id required")

        room = self._room_manager.get_room(room_id)
        if not room:
            return self._error("room.info", f"room not found: {room_id}")

        data = room.to_dict()
        return ControlMessageEvent(
            timestamp=None,
            source="room",
            action="room.info",
            room_id=room_id,
            account_id=msg.account_id,
            text=orjson.dumps(data).decode("utf-8"),
        )

    def _handle_join(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent:
        room_id = msg.room_id
        if not room_id:
            return self._error("room.join", "room_id required")

        account_id = msg.account_id
        if not account_id and self._account_manager:
            account = self._resolve_or_create_account(msg)
            if account is not None:
                account_id = account.account_id
        if not account_id:
            return self._error("room.join", "account_id or identity required")

        self._room_manager.join_room(room_id, account_id, session_id=session_id)

        return ControlMessageEvent(
            timestamp=None,
            source="room",
            action="room.joined",
            room_id=room_id,
            account_id=account_id,
            text=f"Joined room: {room_id}",
        )

    def _handle_leave(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent:
        room_id = msg.room_id
        if not room_id:
            return self._error("room.leave", "room_id required")

        account_id = msg.account_id
        if not account_id and self._account_manager:
            account = self._resolve_or_create_account(msg)
            if account is not None:
                account_id = account.account_id
        if not account_id:
            return self._error("room.leave", "account_id or identity required")

        self._room_manager.leave_room(room_id, account_id, session_id=session_id)

        return ControlMessageEvent(
            timestamp=None,
            source="room",
            action="room.left",
            room_id=room_id,
            account_id=account_id,
            text=f"Left room: {room_id}",
        )

    def _handle_update(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent:
        room_id = msg.room_id
        if not room_id:
            return self._error("room.update", "room_id required")

        room = self._room_manager.get_room(room_id)
        if not room:
            return self._error("room.update", f"room not found: {room_id}")

        updates: dict[str, Any] = {}
        if msg.text:
            try:
                data = orjson.loads(msg.text.encode("utf-8"))
                if isinstance(data, dict):
                    updates = data
            except orjson.JSONDecodeError:
                updates["name"] = msg.text

        if not updates:
            return self._error("room.update", "no fields to update")

        self._room_manager.update_room(room_id, **updates)

        return ControlMessageEvent(
            timestamp=None,
            source="room",
            action="room.updated",
            room_id=room_id,
            account_id=msg.account_id,
            text=f"Updated room: {room_id}",
        )

    def _handle_delete(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent:
        room_id = msg.room_id
        if not room_id:
            return self._error("room.delete", "room_id required")

        room = self._room_manager.get_room(room_id)
        if not room:
            return self._error("room.delete", f"room not found: {room_id}")

        self._room_manager.delete_room(room_id)

        return ControlMessageEvent(
            timestamp=None,
            source="room",
            action="room.deleted",
            room_id=room_id,
            account_id=msg.account_id,
            text=f"Deleted room: {room_id}",
        )

    def _handle_members(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent:
        room_id = msg.room_id
        if not room_id:
            return self._error("room.members", "room_id required")

        room = self._room_manager.get_room(room_id)
        if not room:
            return self._error("room.members", f"room not found: {room_id}")

        members = self._room_manager.get_members(room_id)
        data = [m.to_dict() for m in members]
        return ControlMessageEvent(
            timestamp=None,
            source="room",
            action="room.members",
            room_id=room_id,
            account_id=msg.account_id,
            text=orjson.dumps(data).decode("utf-8"),
        )

    def _resolve_or_create_account(self, msg: ControlMessageEvent) -> Any:
        if not self._account_manager:
            return None
        provider, subject, display_name, metadata = self._parse_identity(msg.identity)
        if not provider or not subject:
            return None
        return self._account_manager.resolve_or_create_identity(
            provider,
            subject,
            display_name=display_name or msg.nickname,
            metadata=metadata,
        )

    @staticmethod
    def _parse_identity(identity: dict[str, Any] | None) -> tuple[str, str, str, dict[str, object]]:
        if not identity:
            return "", "", "", {}
        raw_metadata = identity.get("metadata", {})
        metadata: dict[str, object] = raw_metadata if isinstance(raw_metadata, dict) else {}
        return (
            str(identity.get("provider", "")),
            str(identity.get("subject", "")),
            str(identity.get("display_name", "")),
            metadata,
        )

    @staticmethod
    def _error(action: str, message: str) -> ControlMessageEvent:
        return ControlMessageEvent(
            timestamp=None,
            source="room",
            action=action,
            text=f"Error: {message}",
        )
