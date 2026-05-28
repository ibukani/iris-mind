from __future__ import annotations

import contextlib
from datetime import datetime
import threading
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from iris.io.auth.authenticator import Authenticator
from iris.io.models import (
    AuthMessage,
    CommandOutput,
    ControlMessage,
    Message,
    Permission,
    SessionInfo,
    SessionState,
    SystemMessage,
)

if TYPE_CHECKING:
    from iris.event.event_bus import EventBus


from loguru import logger

from .config import SessionConfig
from .permissions import _INPUT_PERMISSION_MAP, _MSG_PERMISSION_MAP, send_bytes_to_session


class SessionManager:
    def __init__(self, config: SessionConfig | None = None, event_bus: EventBus | None = None) -> None:
        self._sessions: dict[str, SessionInfo] = {}
        cfg = config or SessionConfig()
        self._authenticator = Authenticator(access_token=cfg.access_token)
        self._config = cfg
        self._lock = threading.Lock()
        self._event_bus = event_bus
        self._last_disconnect_times: dict[str, datetime] = {}

    def authenticate(self, conn: Any, msg: AuthMessage) -> ControlMessage:
        with self._lock:
            success, error = self._authenticator.authenticate(msg)
            if not success:
                return ControlMessage(msg_type="auth_failure", error_message=error)

            self._replace_duplicate_session(msg.identity)

            now = datetime.now()
            session = self._create_session(conn, msg, now)
            session_id = session.session_id
            offline_duration = self._compute_offline_duration(session)

            logger.info("Session created: {} (role={})", session_id, msg.role)

        return ControlMessage(msg_type="auth_success", session_id=session_id)

    def _replace_duplicate_session(self, identity: str | None) -> None:
        if not identity:
            return
        for sid, s in list(self._sessions.items()):
            if s.identity == identity and s.state == SessionState.ACTIVE:
                s.state = SessionState.CLOSED
                if s.conn is not None:
                    with contextlib.suppress(Exception):
                        s.conn.close()
                del self._sessions[sid]
                logger.info("SessionManager: replaced duplicate session {} (identity={})", sid, identity)

    def _create_session(self, conn: Any, msg: AuthMessage, now: datetime) -> SessionInfo:
        session_id = uuid4().hex[:16]
        session = SessionInfo(
            session_id=session_id,
            state=SessionState.ACTIVE,
            role=msg.role or "external",
            permissions=msg.permissions[:],
            identity=msg.identity,
            description=msg.description,
            conn=conn,
            created_at=now,
            last_activity=now,
        )
        self._sessions[session_id] = session
        return session

    def _compute_offline_duration(self, session: SessionInfo, now: datetime | None = None) -> str:
        if now is None:
            now = datetime.now()
        key = f"{session.role}:{session.identity}" if session.identity else session.role
        disc_time = self._last_disconnect_times.get(key)
        if not disc_time:
            return ""
        diff = now - disc_time
        secs = int(diff.total_seconds())
        if secs < 60:
            return "たった今"
        if secs < 3600:
            return f"{secs // 60}分間"
        if secs < 86400:
            return f"{secs // 3600}時間{(secs % 3600) // 60}分間"
        return f"{secs // 86400}日間"

    def route_message(self, msg: Message) -> None:
        session: SessionInfo | None = None
        targets: list[SessionInfo] = []
        skipped: list[str] = []

        with self._lock:
            if msg.session_id:
                s = self._sessions.get(msg.session_id)
                if s is not None and s.state == SessionState.ACTIVE and s.conn is not None:
                    session = s
                elif s is None:
                    logger.debug("route_message: session {} not found", msg.session_id)
                else:
                    logger.debug("route_message: session {} not active or no conn", msg.session_id)
            elif msg.target_role == "*":
                targets = [s for s in self._sessions.values() if s.state == SessionState.ACTIVE and s.conn is not None]
            else:
                targets = [
                    s
                    for s in self._sessions.values()
                    if s.state == SessionState.ACTIVE and s.role == msg.target_role and s.conn is not None
                ]

        if session is not None:
            send_bytes_to_session(session, msg)
            return

        permission = _MSG_PERMISSION_MAP.get(msg.msg_type)
        for s in targets:
            if permission is not None and permission not in s.permissions:
                skipped.append(s.session_id)
                continue
            send_bytes_to_session(s, msg)

        if skipped:
            logger.debug("route_message: skipped {} session(s) due to permission: {}", len(skipped), skipped)
        if not targets:
            logger.debug("route_message: no active sessions to route msg_type={}", msg.msg_type)

    def route_system_message(self, sys_msg: SystemMessage, session_id: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            logger.warning("System message route for unknown session: {}", session_id)
            return
        if session.state != SessionState.ACTIVE or session.conn is None:
            return
        raw = sys_msg.model_dump_json().encode("utf-8")
        session.conn.send_bytes(raw)

    def route_command_output(self, session_id: str, msg: CommandOutput) -> None:
        with self._lock:
            session = self._sessions.get(session_id)

        if session is None:
            logger.warning("Command output route for unknown session: {}", session_id)
            return
        if session.state != SessionState.ACTIVE or session.conn is None:
            return
        if Permission.PERMISSION_RECEIVE_COMMAND not in session.permissions:
            logger.warning("Command output denied for session={} (no receive_command)", session_id)
            return
        send_bytes_to_session(session, msg)

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
                key = f"{session.role}:{session.identity}" if session.identity else session.role
                self._last_disconnect_times[key] = now

        if session is not None and self._event_bus is not None:
            from iris.event.event_types import SessionDisconnectEvent

            self._event_bus.publish(
                SessionDisconnectEvent(
                    timestamp=None,
                    source="session",
                    session_id=session_id,
                    identity=session.identity,
                )
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
