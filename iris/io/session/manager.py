from __future__ import annotations

import contextlib
from datetime import datetime
import threading
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from iris.io.auth.authenticator import Authenticator
from iris.io.models import (
    AuthMessage,
    AuthResult,
    SessionInfo,
    SessionState,
)

if TYPE_CHECKING:
    from iris.event.event_bus import EventBus


from loguru import logger

from .config import SessionConfig
from .permissions import _INPUT_PERMISSION_MAP
from .router import _SessionRouter


class SessionManager:
    def __init__(self, config: SessionConfig | None = None, event_bus: EventBus | None = None) -> None:
        self._sessions: dict[str, SessionInfo] = {}
        cfg = config or SessionConfig()
        self._authenticator = Authenticator(access_token=cfg.access_token)
        self._config = cfg
        self._lock = threading.Lock()
        self._event_bus = event_bus
        self._last_disconnect_times: dict[str, datetime] = {}
        self._router = _SessionRouter(self._sessions, self._lock, self._last_disconnect_times)

    def authenticate(self, conn: Any, msg: AuthMessage) -> AuthResult:
        with self._lock:
            success, error = self._authenticator.authenticate(msg)
            if not success:
                return AuthResult(msg_type="auth_failure", error_message=error)

            self._replace_duplicate_session(msg.session_tag)

            now = datetime.now()
            session = self._create_session(conn, msg, now)
            session_id = session.session_id

            logger.info("Session created: {} (role={})", session_id, msg.role)

        return AuthResult(msg_type="auth_success", session_id=session_id)

    def _replace_duplicate_session(self, session_tag: str | None) -> None:
        if not session_tag:
            return
        for sid, s in list(self._sessions.items()):
            if s.session_tag == session_tag and s.state == SessionState.ACTIVE:
                s.state = SessionState.CLOSED
                if s.conn is not None:
                    with contextlib.suppress(Exception):
                        s.conn.close()
                del self._sessions[sid]
                logger.info("SessionManager: replaced duplicate session {} (session_tag={})", sid, session_tag)

    def _create_session(self, conn: Any, msg: AuthMessage, now: datetime) -> SessionInfo:
        session_id = uuid4().hex[:16]
        session = SessionInfo(
            session_id=session_id,
            state=SessionState.ACTIVE,
            role=msg.role or "external",
            permissions=msg.permissions[:],
            session_tag=msg.session_tag,
            description=msg.description,
            conn=conn,
            created_at=now,
            last_activity=now,
        )
        self._sessions[session_id] = session
        return session

    @property
    def router(self) -> _SessionRouter:
        return self._router

    def update_activity(self, session_id: str | None) -> None:
        if session_id is None:
            return
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.last_activity = datetime.now()

    def is_session_active(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            return session is not None and session.state == SessionState.ACTIVE

    def get_session_info(self, session_id: str) -> SessionInfo | None:
        with self._lock:
            return self._sessions.get(session_id)

    def remove_session(self, session_id: str) -> None:
        now = datetime.now()
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                session.state = SessionState.CLOSED
                if session.conn is not None:
                    with contextlib.suppress(Exception):
                        session.conn.close()
                logger.info("Session removed: {}", session_id)
                key = f"{session.role}:{session.session_tag}" if session.session_tag else session.role
                self._last_disconnect_times[key] = now

        if session is not None and self._event_bus is not None:
            from iris.event.event_types import SessionDisconnectEvent

            self._event_bus.publish(
                SessionDisconnectEvent(
                    timestamp=None,
                    source="session",
                    session_id=session_id,
                    session_tag=session.session_tag,
                ),
            )

    def has_active_sessions(self) -> bool:
        with self._lock:
            return any(s.state == SessionState.ACTIVE for s in self._sessions.values())

    def get_active_sessions(self) -> list[SessionInfo]:
        with self._lock:
            return [s for s in self._sessions.values() if s.state == SessionState.ACTIVE]

    def check_send_permission(self, session_id: str, msg_type: str) -> bool:
        required = _INPUT_PERMISSION_MAP.get(msg_type)
        if required is None:
            return True
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            return required in session.permissions

    def get_sessions_summary(self) -> str:
        with self._lock:
            sessions = [s for s in self._sessions.values() if s.state == SessionState.ACTIVE]
        if not sessions:
            return ""
        lines: list[str] = []
        for s in sessions:
            perms = ", ".join(p.value for p in s.permissions)
            lines.append(f"{s.role or 'unknown'}: {perms}")
        return "Connected clients:\n" + "\n".join(lines)
