from __future__ import annotations

from uuid import uuid4

from loguru import logger

from iris.memory.base import _JsonlStore


class UserStore:
    """ユーザーID↔ニックネームの永続マッピング。

    JSONL 形式で保存。各エントリは {"user_id": "...", "nickname": "...", "created_at": "..."}。
    """

    def __init__(self, path: str = ".iris/data/users.jsonl") -> None:
        self._store = _JsonlStore(path)

    def register(self, user_id: str, nickname: str) -> None:
        entries = self._store.load_all()
        for e in entries:
            if e.get("user_id") == user_id:
                return
        from datetime import UTC, datetime

        self._store._add_entry(
            {"user_id": user_id, "nickname": nickname, "created_at": datetime.now(UTC).isoformat()},
            max_entries=1000,
        )
        logger.info("UserStore: registered user_id={} nickname={}", user_id, nickname)

    def create(self, nickname: str) -> tuple[str, str]:
        user_id = uuid4().hex[:16]
        self.register(user_id, nickname)
        return user_id, nickname

    def set_nickname(self, user_id: str, nickname: str) -> None:
        entries = self._store.load_all()
        updated = False
        for e in entries:
            if e.get("user_id") == user_id:
                e["nickname"] = nickname
                updated = True
                break
        if updated:
            self._store._write_file(entries)
            logger.info("UserStore: updated user_id={} nickname={}", user_id, nickname)
        else:
            self.register(user_id, nickname)

    def get(self, user_id: str) -> str | None:
        for e in self._store.load_all():
            if isinstance(e, dict) and e.get("user_id") == user_id:
                nickname = e.get("nickname")
                if isinstance(nickname, str):
                    return nickname
        return None

    def resolve(self, user_id: str) -> str:
        nickname = self.get(user_id)
        return nickname if nickname else user_id

    def get_all(self) -> list[dict]:
        return list(self._store.load_all())
