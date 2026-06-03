"""Fake SessionManager と SessionInfo。

These fakes intentionally do not depend on legacy ``iris.io`` models so that
target test collection stays clean.  Type hints reference ``Any`` for the
message types that legacy ``SessionManager`` would accept.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeSessionInfo:
    session_id: str = ""
    role: str = ""
    permissions: list = field(default_factory=list)
    identity: str = ""


class FakeSessionManager:
    def __init__(self) -> None:
        self.sent: list[Any] = []
        self._session_info: FakeSessionInfo | None = None

    def set_session_info(self, info: FakeSessionInfo) -> None:
        self._session_info = info

    def route_message(self, msg: Any) -> None:
        self.sent.append(msg)

    def route_command_output(self, session_id: str, msg: Any) -> None:
        self.sent.append(msg)

    def is_session_active(self, session_id: str) -> bool:
        return bool(session_id)

    def get_session_info(self, session_id: str) -> FakeSessionInfo | None:
        return self._session_info

    def get_sessions_summary(self) -> str:
        info = self._session_info
        if info and info.permissions:
            r = ", ".join(p.value if hasattr(p, "value") else str(p) for p in info.permissions)
            return f"Connected clients:\n{info.role}: {r}"
        return ""


__all__ = ["FakeSessionInfo", "FakeSessionManager"]
