from __future__ import annotations

from pathlib import Path
import threading

from loguru import logger
import orjson

from iris.room.models import Room, RoomMember, RoomState


class RoomStore:
    """ルーム・メンバーシップの永続化。

    - rooms.jsonl: ルーム情報
    - room_members.jsonl: メンバーシップ情報
    """

    def __init__(
        self,
        rooms_path: str = ".iris/data/rooms.jsonl",
        members_path: str = ".iris/data/room_members.jsonl",
    ) -> None:
        self._rooms_path = Path(rooms_path)
        self._members_path = Path(members_path)
        self._lock = threading.Lock()
        self._rooms_cache: list[dict] | None = None
        self._members_cache: list[dict] | None = None

    def load_rooms(self) -> list[Room]:
        raw = self._load_jsonl(self._rooms_path, "_rooms_cache")
        return [Room.from_dict(e) for e in raw]

    def load_members(self) -> list[RoomMember]:
        raw = self._load_jsonl(self._members_path, "_members_cache")
        return [RoomMember.from_dict(e) for e in raw]

    def save_rooms(self, rooms: list[Room]) -> None:
        self._write_jsonl(self._rooms_path, [r.to_dict() for r in rooms], "_rooms_cache")

    def save_members(self, members: list[RoomMember]) -> None:
        self._write_jsonl(self._members_path, [m.to_dict() for m in members], "_members_cache")

    def add_room(self, room: Room) -> None:
        with self._lock:
            rooms = self.load_rooms()
            rooms.append(room)
            self.save_rooms(rooms)
            logger.info("RoomStore: added room_id={} name={}", room.room_id, room.name)

    def update_room(self, room: Room) -> None:
        with self._lock:
            rooms = self.load_rooms()
            for i, r in enumerate(rooms):
                if r.room_id == room.room_id:
                    rooms[i] = room
                    break
            self.save_rooms(rooms)

    def delete_room(self, room_id: str) -> None:
        with self._lock:
            rooms = self.load_rooms()
            rooms = [r for r in rooms if r.room_id != room_id]
            self.save_rooms(rooms)
            members = self.load_members()
            members = [m for m in members if m.room_id != room_id]
            self.save_members(members)
            logger.info("RoomStore: deleted room_id={}", room_id)

    def add_member(self, member: RoomMember) -> None:
        with self._lock:
            members = self.load_members()
            members.append(member)
            self.save_members(members)
            logger.debug(
                "RoomStore: added member room_id={} account_id={}",
                member.room_id,
                member.account_id,
            )

    def update_member(self, member: RoomMember) -> None:
        with self._lock:
            members = self.load_members()
            for i, m in enumerate(members):
                if m.room_id == member.room_id and m.account_id == member.account_id:
                    members[i] = member
                    break
            self.save_members(members)

    def remove_member(self, room_id: str, account_id: str) -> None:
        with self._lock:
            members = self.load_members()
            members = [m for m in members if not (m.room_id == room_id and m.account_id == account_id)]
            self.save_members(members)

    def find_room_by_id(self, room_id: str) -> Room | None:
        for r in self.load_rooms():
            if r.room_id == room_id:
                return r
        return None

    def find_active_rooms(self) -> list[Room]:
        return [r for r in self.load_rooms() if r.state == RoomState.ACTIVE]

    def find_member(self, room_id: str, account_id: str) -> RoomMember | None:
        for m in self.load_members():
            if m.room_id == room_id and m.account_id == account_id:
                return m
        return None

    def find_members_by_room(self, room_id: str) -> list[RoomMember]:
        return [m for m in self.load_members() if m.room_id == room_id]

    def find_active_members_by_room(self, room_id: str) -> list[RoomMember]:
        return [m for m in self.load_members() if m.room_id == room_id and m.is_active]

    def find_active_member_by_session(self, session_id: str) -> RoomMember | None:
        for m in self.load_members():
            if m.session_id == session_id and m.is_active:
                return m
        return None

    def find_active_members_by_session(self, session_id: str) -> list[RoomMember]:
        return [m for m in self.load_members() if m.session_id == session_id and m.is_active]

    def find_active_members_by_account(self, account_id: str) -> list[RoomMember]:
        return [m for m in self.load_members() if m.account_id == account_id and m.is_active]

    def find_active_bindings_by_room(self, room_id: str) -> list[RoomMember]:
        return [m for m in self.load_members() if m.room_id == room_id and m.is_active]

    def find_rooms_by_account(self, account_id: str) -> list[Room]:
        member_room_ids = {m.room_id for m in self.load_members() if m.account_id == account_id}
        return [r for r in self.load_rooms() if r.room_id in member_room_ids]

    def _load_jsonl(self, path: Path, cache_attr: str) -> list[dict[str, object]]:
        cached = getattr(self, cache_attr, None)
        if cached is not None:
            return cached  # type: ignore[no-any-return]
        if not path.exists():
            setattr(self, cache_attr, [])
            return []
        entries: list[dict[str, object]] = []
        for line in path.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                raw = orjson.loads(line.encode("utf-8"))
                if isinstance(raw, dict):
                    entries.append(raw)
            except orjson.JSONDecodeError:
                logger.warning("RoomStore: skipping corrupt entry: {:.80}", line)
        setattr(self, cache_attr, entries)
        return entries

    def _write_jsonl(self, path: Path, entries: list[dict], cache_attr: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            "\n".join(orjson.dumps(e).decode("utf-8") for e in entries),
            encoding="utf-8",
        )
        tmp.replace(path)
        setattr(self, cache_attr, None)
