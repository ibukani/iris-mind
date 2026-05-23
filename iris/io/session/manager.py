from __future__ import annotations

import contextlib
from dataclasses import dataclass
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
)

if TYPE_CHECKING:
    from iris.event.event_bus import EventBus


from loguru import logger


@dataclass
class SessionConfig:
    host: str = "127.0.0.1"
    port: int = 9876
    access_token: str = ""


_MSG_PERMISSION_MAP: dict[str, Permission] = {
    "chat": Permission.PERMISSION_RECEIVE_CHAT,
    "execute": Permission.PERMISSION_EXECUTE_ACTION,
    "execute_result": Permission.PERMISSION_EXECUTE_ACTION,
    "ack": Permission.PERMISSION_RECEIVE_CHAT,
    "system": Permission.PERMISSION_RECEIVE_CHAT,
    "error": Permission.PERMISSION_RECEIVE_CHAT,
    "interrupt": Permission.PERMISSION_INTERRUPT,
    "command": Permission.PERMISSION_RECEIVE_COMMAND,
}

_INPUT_PERMISSION_MAP: dict[str, Permission] = {
    "chat": Permission.PERMISSION_SEND_CHAT,
    "system": Permission.PERMISSION_SEND_CHAT,
    "interrupt": Permission.PERMISSION_INTERRUPT,
    "execute_result": Permission.PERMISSION_EXECUTE_ACTION,
    "command": Permission.PERMISSION_SEND_COMMAND,
}


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
        offline_duration = ""
        with self._lock:
            success, error = self._authenticator.authenticate(msg)
            if not success:
                return ControlMessage(msg_type="auth_failure", error_message=error)

            if msg.identity:
                for sid, s in list(self._sessions.items()):
                    if s.identity == msg.identity and s.state == SessionState.ACTIVE:
                        s.state = SessionState.CLOSED
                        if s.conn is not None:
                            with contextlib.suppress(Exception):
                                s.conn.close()
                        del self._sessions[sid]
                        logger.info("SessionManager: replaced duplicate session {} (identity={})", sid, msg.identity)

            now = datetime.now()
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

            key = f"{session.role}:{session.identity}" if session.identity else session.role
            if key in self._last_disconnect_times:
                disc_time = self._last_disconnect_times[key]
                diff = now - disc_time
                secs = int(diff.total_seconds())
                if secs < 60:
                    offline_duration = "たった今"
                elif secs < 3600:
                    offline_duration = f"{secs // 60}分間"
                elif secs < 86400:
                    offline_duration = f"{secs // 3600}時間{(secs % 3600) // 60}分間"
                else:
                    offline_duration = f"{secs // 86400}日間"

            logger.info("Session created: {} (role={})", session_id, msg.role)

        if self._event_bus:
            from iris.event.event_types import ClientSessionEvent

            self._event_bus.publish(
                ClientSessionEvent(
                    timestamp=now,
                    source="session",
                    session_id=session_id,
                    action="connected",
                    role=session.role,
                    identity=session.identity,
                    offline_duration=offline_duration,
                )
            )

        return ControlMessage(msg_type="auth_success", session_id=session_id)

    def route_message(self, msg: Message) -> None:
        # Get target session(s) under lock, then send outside lock
        session: SessionInfo | None = None
        targets: list[SessionInfo] = []

        with self._lock:
            if msg.session_id:
                s = self._sessions.get(msg.session_id)
                if s is not None and s.state == SessionState.ACTIVE and s.conn is not None:
                    session = s
            elif msg.target_role == "*":
                targets = [s for s in self._sessions.values() if s.state == SessionState.ACTIVE and s.conn is not None]
            else:
                targets = [
                    s
                    for s in self._sessions.values()
                    if s.state == SessionState.ACTIVE and s.role == msg.target_role and s.conn is not None
                ]

        if session is not None:
            self._send_to_session(session, msg)
            return

        permission = _MSG_PERMISSION_MAP.get(msg.msg_type)
        for s in targets:
            if permission is not None and permission not in s.permissions:
                continue
            self._send_to_session(s, msg)

    def route_command_output(self, session_id: str, msg: CommandOutput) -> None:
        with self._lock:
            session = self._sessions.get(session_id)

        if session is None:
            logger.warning("Command output route for unknown session: {}", session_id)
            return
        if session.state != SessionState.ACTIVE:
            return
        if session.conn is None:
            return
        if Permission.PERMISSION_RECEIVE_COMMAND not in session.permissions:
            logger.warning("Command output denied for session={} (no receive_command)", session_id)
            return
        self._send_to_session(session, msg)

    @staticmethod
    def _send_to_session(session: SessionInfo, msg: Message | CommandOutput) -> None:
        conn = session.conn
        if conn is None:
            return
        raw = msg.model_dump_json().encode("utf-8")
        try:
            conn.send_bytes(raw)
            session.last_activity = datetime.now()
        except (BrokenPipeError, ConnectionError, EOFError):
            logger.warning("Connection lost for session: {}", session.session_id)
            session.conn = None

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

        if session and self._event_bus:
            from iris.event.event_types import ClientSessionEvent

            self._event_bus.publish(
                ClientSessionEvent(
                    timestamp=now,
                    source="session",
                    session_id=session_id,
                    action="disconnected",
                    role=session.role,
                    identity=session.identity,
                )
            )

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
