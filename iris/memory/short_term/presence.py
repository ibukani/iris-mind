from __future__ import annotations

from iris.memory.short_term.models import ActiveUser


class PresenceTracker:
    """active users / room users の管理。"""

    def __init__(self) -> None:
        self._active_users: dict[str, str] = {}
        self._room_users: dict[str, list[str]] = {}

    def add_user(self, account_id: str, display_name: str, room_id: str = "") -> None:
        self._active_users[account_id] = display_name
        if room_id:
            self._add_room_user(room_id, account_id)

    def remove_user(self, account_id: str, room_id: str = "") -> None:
        if room_id:
            self._remove_room_user(room_id, account_id)
        else:
            for uid_list in self._room_users.values():
                while account_id in uid_list:
                    uid_list.remove(account_id)

        still_present = any(account_id in users for users in self._room_users.values())
        if not still_present:
            self._active_users.pop(account_id, None)

    def get_active_users(self) -> list[ActiveUser]:
        return [ActiveUser(account_id=uid, display_name=nick) for uid, nick in self._active_users.items()]

    def get_users_by_room(self, room_id: str) -> list[ActiveUser]:
        uid_list = self._room_users.get(room_id, [])
        return [
            ActiveUser(account_id=uid, display_name=self._active_users.get(uid, uid))
            for uid in uid_list
            if uid in self._active_users
        ]

    def _add_room_user(self, room_id: str, account_id: str) -> None:
        uid_list = self._room_users.setdefault(room_id, [])
        if account_id not in uid_list:
            uid_list.append(account_id)

    def _remove_room_user(self, room_id: str, account_id: str) -> None:
        uid_list = self._room_users.get(room_id, [])
        if account_id in uid_list:
            uid_list.remove(account_id)

    def clear(self) -> None:
        self._active_users.clear()
        self._room_users.clear()
