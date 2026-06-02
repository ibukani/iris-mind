"""ルーム管理の核心サービス。

責務:
- ルームのCRUD
- メンバーシップ管理（セッション追跡含む）
- EventBus へのイベント発行

AccountManager などの依存は `RoomResolverProtocol` / `AccountResolverProtocol`
として受け取り、具象クラスには依存しない。`DisplayNameResolver` が必須
依存でなくなったため、表示名が解決できない場合は account_id をそのまま返す。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

from iris.room.batcher import RoomJoinBatcher
from iris.room.events import (
    RoomCreatedEvent,
    RoomDeletedEvent,
    RoomJoinedEvent,
    RoomLeftEvent,
    RoomUpdatedEvent,
)
from iris.room.field_coercion import coerce_update_field
from iris.room.models import Room, RoomMember, RoomMetadata, RoomState
from iris.room.store import RoomStore

if TYPE_CHECKING:
    from iris.kernel.protocols import EventPublisherProtocol


class RoomManager:
    def __init__(
        self,
        store: RoomStore,
        event_bus: EventPublisherProtocol | None = None,
        account_manager: Any | None = None,
        join_batcher: RoomJoinBatcher | None = None,
    ) -> None:
        self._store = store
        self._event_bus = event_bus
        self._account_resolver = account_manager
        self._join_batcher = join_batcher

    def create_room(
        self,
        name: str,
        created_by: str = "",
        *,
        description: str = "",
        topic: str = "",
        state: RoomState | str = RoomState.ACTIVE,
        metadata: RoomMetadata | None = None,
    ) -> Room:
        resolved_state = state if isinstance(state, RoomState) else RoomState(state)
        room = Room(
            name=name,
            created_by=created_by,
            description=description,
            topic=topic,
            state=resolved_state,
            metadata=dict(metadata) if metadata is not None else {},
        )
        self._store.add_room(room)
        self._publish_event(
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
        return self._store.find_room_by_id(room_id)

    def list_rooms(self, state: RoomState = RoomState.ACTIVE) -> list[Room]:
        return self._store.find_rooms_by_state(state)

    def update_room(
        self,
        room_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        topic: str | None = None,
        state: RoomState | str | None = None,
        metadata: RoomMetadata | None = None,
    ) -> None:
        room = self.get_room(room_id)
        if not room:
            logger.warning("RoomManager: room not found: {}", room_id)
            raise ValueError(f"room not found: {room_id}")

        updates: list[tuple[str, Any]] = []
        if name is not None:
            updates.append(("name", name))
        if description is not None:
            updates.append(("description", description))
        if topic is not None:
            updates.append(("topic", topic))
        if state is not None:
            updates.append(("state", state))
        if metadata is not None:
            updates.append(("metadata", metadata))

        for key, value in updates:
            old, new = coerce_update_field(room, key, value)
            if old == new:
                continue
            setattr(room, key, new)
            self._publish_event(
                RoomUpdatedEvent(
                    timestamp=datetime.now(UTC),
                    source="room",
                    room_id=room_id,
                    field_name=key,
                    old_value=old,
                    new_value=new,
                ),
            )

        room.updated_at = datetime.now(UTC).isoformat()
        self._store.update_room(room)
        logger.info("RoomManager: updated room_id={}", room_id)

    def archive_room(self, room_id: str) -> None:
        self.update_room(room_id, state=RoomState.ARCHIVED)

    def update_room_from_update(self, room_id: str, update: Any) -> None:
        if hasattr(update, "to_field_kwargs"):
            self.update_room(room_id, **update.to_field_kwargs())
        else:
            self.update_room(room_id)

    def delete_room(self, room_id: str) -> None:
        self._store.delete_room(room_id)
        self._publish_event(
            RoomDeletedEvent(
                timestamp=datetime.now(UTC),
                source="room",
                room_id=room_id,
            ),
        )
        logger.info("RoomManager: deleted room_id={}", room_id)

    def join_room(self, room_id: str, account_id: str, session_id: str = "", role: str = "member") -> bool:
        room = self.get_room(room_id)
        if not room:
            logger.warning("RoomManager: room not found: {}", room_id)
            return False
        if room.state != RoomState.ACTIVE:
            logger.warning("RoomManager: room not active: {}", room_id)
            return False

        existing = self._store.find_member(room_id, account_id)
        if existing and existing.is_active:
            if session_id and session_id not in existing.session_ids:
                existing.session_ids.append(session_id)
                self._store.update_member(existing)
                logger.debug("RoomManager: added session {} to existing member in room {}", session_id, room_id)
            else:
                logger.debug("RoomManager: account {} already in room {}", account_id, room_id)
            return True

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

        event = RoomJoinedEvent(
            timestamp=datetime.now(UTC),
            source="room",
            room_id=room_id,
            account_id=account_id,
            display_name=self._resolve_display_name(account_id),
        )
        if self._join_batcher is not None:
            self._join_batcher.add(event)
        else:
            self._publish_event(event)

        logger.debug("RoomManager: account {} joined room {} (session={})", account_id, room_id, session_id)
        return True

    def leave_room(self, room_id: str, account_id: str, session_id: str = "") -> bool:
        member = self._store.find_member(room_id, account_id)
        if not member or not member.is_active:
            logger.debug("RoomManager: no active member for account {} in room {}", account_id, room_id)
            return False

        if session_id:
            if session_id in member.session_ids:
                member.session_ids.remove(session_id)
                if member.session_ids:
                    self._store.update_member(member)
                    logger.debug("RoomManager: removed session {} from member (still has sessions)", session_id)
                    return True
            else:
                logger.debug("RoomManager: session {} not found in member's sessions", session_id)
                return False

        member.disconnected_at = datetime.now(UTC).isoformat()
        self._store.update_member(member)
        self._publish_event(
            RoomLeftEvent(
                timestamp=datetime.now(UTC),
                source="room",
                room_id=room_id,
                account_id=account_id,
                display_name=self._resolve_display_name(account_id),
            ),
        )
        logger.debug("RoomManager: account {} left room {} (session={})", account_id, room_id, session_id)
        self._maybe_delete_empty_room(room_id)
        return True

    def _maybe_delete_empty_room(self, room_id: str) -> None:
        remaining = self._store.find_members_by_room(room_id)
        if remaining:
            return
        room = self.get_room(room_id)
        if room is None:
            return
        if room.name == "default" or room.created_by == "system":
            logger.debug("RoomManager: room {} is protected, skipping auto-delete", room_id)
            return
        logger.info("RoomManager: auto-deleting empty room {} (name={})", room_id, room.name)
        self.delete_room(room_id)

    def get_members(self, room_id: str) -> list[RoomMember]:
        return self._store.find_members_by_room(room_id)

    def get_rooms_by_account(self, account_id: str) -> list[Room]:
        return self._store.find_rooms_by_account(account_id)

    def is_member(self, room_id: str, account_id: str) -> bool:
        member = self._store.find_member(room_id, account_id)
        return member is not None and member.is_active

    def _resolve_display_name(self, account_id: str) -> str:
        if self._account_resolver is not None:
            account = self._account_resolver.resolve(account_id)
            if account:
                return str(account.display_name)
        return account_id

    def _publish_event(self, event: Any) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(event)

    def get_default_room(self) -> Room | None:
        for room in self._store.load_rooms():
            if room.name == "default" and room.state == RoomState.ACTIVE:
                return room
        return self.create_room("default", created_by="system")


__all__ = ["RoomManager"]
