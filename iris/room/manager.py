from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger

from iris.room.events import (
    RoomCreatedEvent,
    RoomDeletedEvent,
    RoomJoinedEvent,
    RoomLeftEvent,
    RoomUpdatedEvent,
)
from iris.room.models import Room, RoomMember, RoomState
from iris.room.store import RoomStore


class RoomManager:
    """ルーム管理の核心サービス。

    責務:
    - ルームのCRUD
    - メンバーシップ管理（セッション追跡含む）
    - AccountManager からのアカウント解決
    - EventBus へのイベント発行
    """

    def __init__(self, store: RoomStore, event_bus: Any = None, account_manager: Any = None) -> None:
        self._store = store
        self._event_bus = event_bus
        self._account_manager = account_manager

    def set_account_manager(self, account_manager: Any) -> None:
        self._account_manager = account_manager

    def create_room(self, name: str, created_by: str = "", **kwargs: Any) -> Room:
        """新規ルームを作成する。"""
        room = Room(name=name, created_by=created_by, **kwargs)
        self._store.add_room(room)

        if self._event_bus:
            self._event_bus.publish(
                RoomCreatedEvent(
                    timestamp=datetime.now(UTC),
                    source="room",
                    room_id=room.room_id,
                    name=room.name,
                    created_by=created_by,
                ),
            )

        return room

    def get_room(self, room_id: str) -> Room | None:
        """room_id からルームを取得する。"""
        return self._store.find_room_by_id(room_id)

    def list_rooms(self, state: RoomState = RoomState.ACTIVE) -> list[Room]:
        """ルーム一覧を取得する。"""
        if state == RoomState.ACTIVE:
            return self._store.find_active_rooms()
        return self._store.load_rooms()

    def update_room(self, room_id: str, **fields: Any) -> None:
        """ルームフィールドを更新する。"""
        room = self.get_room(room_id)
        if not room:
            logger.warning("RoomManager: room not found: {}", room_id)
            return

        for key, value in fields.items():
            old = getattr(room, key, None)
            setattr(room, key, value)
            if self._event_bus and old != value:
                self._event_bus.publish(
                    RoomUpdatedEvent(
                        timestamp=datetime.now(UTC),
                        source="room",
                        room_id=room_id,
                        field_name=key,
                        old_value=old,
                        new_value=value,
                    ),
                )

        room.updated_at = datetime.now(UTC).isoformat()
        self._store.update_room(room)
        logger.info("RoomManager: updated room_id={}", room_id)

    def archive_room(self, room_id: str) -> None:
        """ルームをアーカイブする。"""
        self.update_room(room_id, state=RoomState.ARCHIVED)

    def delete_room(self, room_id: str) -> None:
        """ルームを削除する。"""
        self._store.delete_room(room_id)

        if self._event_bus:
            self._event_bus.publish(
                RoomDeletedEvent(
                    timestamp=datetime.now(UTC),
                    source="room",
                    room_id=room_id,
                ),
            )

        logger.info("RoomManager: deleted room_id={}", room_id)

    def join_room(self, room_id: str, account_id: str, session_id: str = "", role: str = "member") -> None:
        """ルームに参加する。同一(room_id, account_id)の参加は重複防止。"""
        room = self.get_room(room_id)
        if not room:
            logger.warning("RoomManager: room not found: {}", room_id)
            return

        existing = self._store.find_member(room_id, account_id)
        if existing and existing.is_active:
            if session_id and session_id not in existing.session_ids:
                existing.session_ids.append(session_id)
                self._store.update_member(existing)
                logger.debug("RoomManager: added session {} to existing member in room {}", session_id, room_id)
            else:
                logger.debug("RoomManager: account {} already in room {}", account_id, room_id)
            return

        member = RoomMember(
            room_id=room_id, account_id=account_id, session_ids=[session_id] if session_id else [], role=role
        )
        if existing and not existing.is_active:
            existing.disconnected_at = None
            existing.session_ids = [session_id] if session_id else []
            existing.joined_at = datetime.now(UTC).isoformat()
            existing.role = role
            self._store.update_member(existing)
            member = existing
        else:
            self._store.add_member(member)

        if self._event_bus:
            self._event_bus.publish(
                RoomJoinedEvent(
                    timestamp=datetime.now(UTC),
                    source="room",
                    room_id=room_id,
                    account_id=account_id,
                    display_name=self._resolve_display_name(account_id),
                ),
            )

        logger.debug("RoomManager: account {} joined room {} (session={})", account_id, room_id, session_id)

    def leave_room(self, room_id: str, account_id: str, session_id: str = "") -> None:
        """ルームから退室する。session_id 指定時はそのセッションのみ解除。"""
        member = self._store.find_member(room_id, account_id)
        if not member or not member.is_active:
            logger.debug("RoomManager: no active member for account {} in room {}", account_id, room_id)
            return

        if session_id:
            if session_id in member.session_ids:
                member.session_ids.remove(session_id)
                if member.session_ids:
                    self._store.update_member(member)
                    logger.debug("RoomManager: removed session {} from member (still has sessions)", session_id)
                    return
            else:
                logger.debug("RoomManager: session {} not found in member's sessions", session_id)
                return

        member.disconnected_at = datetime.now(UTC).isoformat()
        self._store.update_member(member)

        if self._event_bus:
            self._event_bus.publish(
                RoomLeftEvent(
                    timestamp=datetime.now(UTC),
                    source="room",
                    room_id=room_id,
                    account_id=account_id,
                    display_name=self._resolve_display_name(account_id),
                ),
            )

        logger.debug("RoomManager: account {} left room {} (session={})", account_id, room_id, session_id)

    def on_session_disconnect(self, session_id: str) -> None:
        """セッション切断時に、そのセッションを含むメンバーの session_ids を更新し、空になったら退室処理する。"""
        members = self._store.find_active_members_containing_session(session_id)
        for member in members:
            if session_id in member.session_ids:
                member.session_ids.remove(session_id)

            if not member.session_ids:
                member.disconnected_at = datetime.now(UTC).isoformat()
                self._store.update_member(member)
                if self._event_bus:
                    self._event_bus.publish(
                        RoomLeftEvent(
                            timestamp=datetime.now(UTC),
                            source="room",
                            room_id=member.room_id,
                            account_id=member.account_id,
                            display_name=self._resolve_display_name(member.account_id),
                        ),
                    )
                logger.debug(
                    "RoomManager: account {} disconnected from room {} (no remaining sessions)",
                    member.account_id,
                    member.room_id,
                )
            else:
                self._store.update_member(member)
                logger.debug(
                    "RoomManager: removed session {} from account {} ({} sessions remain)",
                    session_id,
                    member.account_id,
                    len(member.session_ids),
                )

        if members:
            logger.debug("RoomManager: processed session disconnect for session={}", session_id)

    def get_members(self, room_id: str) -> list[RoomMember]:
        """ルームメンバー一覧を取得する。"""
        return self._store.find_members_by_room(room_id)

    def get_rooms_by_account(self, account_id: str) -> list[Room]:
        """アカウントが参加しているルーム一覧を取得する。"""
        return self._store.find_rooms_by_account(account_id)

    def is_member(self, room_id: str, account_id: str) -> bool:
        """アカウントがルームのアクティブメンバーかどうかを確認する。"""
        member = self._store.find_member(room_id, account_id)
        return member is not None and member.is_active

    def _resolve_display_name(self, account_id: str) -> str:
        """account_id から表示名を解決する。見つからない場合は account_id を返す。"""
        if self._account_manager:
            account = self._account_manager.resolve(account_id)
            if account:
                return str(account.display_name)
        return account_id

    def get_default_room(self) -> Room | None:
        """デフォルトルーム（'default'という名前のルーム）を取得する。存在しない場合は作成する。"""
        for room in self._store.load_rooms():
            if room.name == "default" and room.state == RoomState.ACTIVE:
                return room
        return self.create_room("default", created_by="system")
