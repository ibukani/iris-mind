from __future__ import annotations

import threading

from loguru import logger

from iris.room.models import Room, RoomMember, RoomState


class RoomStore:
    """ルーム・メンバーシップのインメモリ管理。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rooms: list[Room] = []
        self._members: list[RoomMember] = []

    def load_rooms(self) -> list[Room]:
        return list(self._rooms)

    def load_members(self) -> list[RoomMember]:
        return list(self._members)

    def save_rooms(self, rooms: list[Room]) -> None:
        self._rooms = list(rooms)

    def save_members(self, members: list[RoomMember]) -> None:
        self._members = list(members)

    def add_room(self, room: Room) -> None:
        with self._lock:
            self._rooms.append(room)
            logger.info("RoomStore: added room_id={} name={}", room.room_id, room.name)

    def update_room(self, room: Room) -> None:
        with self._lock:
            for i, r in enumerate(self._rooms):
                if r.room_id == room.room_id:
                    self._rooms[i] = room
                    break

    def delete_room(self, room_id: str) -> None:
        with self._lock:
            self._rooms = [r for r in self._rooms if r.room_id != room_id]
            self._members = [m for m in self._members if m.room_id != room_id]
            logger.info("RoomStore: deleted room_id={}", room_id)

    def add_member(self, member: RoomMember) -> None:
        with self._lock:
            self._members.append(member)
            logger.debug(
                "RoomStore: added member room_id={} account_id={}",
                member.room_id,
                member.account_id,
            )

    def update_member(self, member: RoomMember) -> None:
        with self._lock:
            for i, m in enumerate(self._members):
                if m.room_id == member.room_id and m.account_id == member.account_id:
                    self._members[i] = member
                    break

    def remove_member(self, room_id: str, account_id: str) -> None:
        with self._lock:
            self._members = [m for m in self._members if not (m.room_id == room_id and m.account_id == account_id)]

    def find_room_by_id(self, room_id: str) -> Room | None:
        for r in self._rooms:
            if r.room_id == room_id:
                return r
        return None

    def find_active_rooms(self) -> list[Room]:
        return [r for r in self._rooms if r.state == RoomState.ACTIVE]

    def find_member(self, room_id: str, account_id: str) -> RoomMember | None:
        for m in self._members:
            if m.room_id == room_id and m.account_id == account_id:
                return m
        return None

    def find_members_by_room(self, room_id: str) -> list[RoomMember]:
        return [m for m in self._members if m.room_id == room_id]

    def find_active_members_by_room(self, room_id: str) -> list[RoomMember]:
        return [m for m in self._members if m.room_id == room_id and m.is_active]

    def find_active_members_containing_session(self, session_id: str) -> list[RoomMember]:
        return [m for m in self._members if session_id in m.session_ids and m.is_active]

    def find_all_session_ids_for_room(self, room_id: str) -> list[str]:
        session_ids: list[str] = []
        for m in self._members:
            if m.room_id == room_id and m.is_active:
                session_ids.extend(m.session_ids)
        return session_ids

    def find_active_members_by_account(self, account_id: str) -> list[RoomMember]:
        return [m for m in self._members if m.account_id == account_id and m.is_active]

    def find_active_bindings_by_room(self, room_id: str) -> list[RoomMember]:
        return [m for m in self._members if m.room_id == room_id and m.is_active]

    def find_rooms_by_account(self, account_id: str) -> list[Room]:
        member_room_ids = {m.room_id for m in self._members if m.account_id == account_id}
        return [r for r in self._rooms if r.room_id in member_room_ids]
