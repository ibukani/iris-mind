from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import datetime
import logging
from multiprocessing.connection import Connection
import threading
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

logger = logging.getLogger(__name__)


@dataclass
class SessionConfig:
    host: str = "127.0.0.1"
    port: int = 9876
    access_token: str = ""


_MSG_PERMISSION_MAP: dict[str, Permission] = {
    "chat": Permission.RECEIVE_CHAT,
    "proactive": Permission.RECEIVE_CHAT,
    "execute": Permission.EXECUTE_ACTION,
    "execute_result": Permission.SEND_CHAT,
    "ack": Permission.RECEIVE_CHAT,
    "system": Permission.RECEIVE_CHAT,
    "error": Permission.RECEIVE_CHAT,
    "interrupt": Permission.INTERRUPT,
}


class SessionManager:
    def __init__(self, config: SessionConfig | None = None) -> None:
        self._sessions: dict[str, SessionInfo] = {}
        cfg = config or SessionConfig()
        self._authenticator = Authenticator(access_token=cfg.access_token)
        self._config = cfg
        self._lock = threading.Lock()

    def authenticate(self, conn: Connection, msg: AuthMessage) -> ControlMessage:
        with self._lock:
            success, error = self._authenticator.authenticate(msg)
            if not success:
                return ControlMessage(msg_type="auth_failure", error_message=error)

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

            logger.info("Session created: %s (role=%s)", session_id, msg.role)
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
            logger.warning("Command output route for unknown session: %s", session_id)
            return
        if session.state != SessionState.ACTIVE:
            return
        if session.conn is None:
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
            logger.warning("Connection lost for session: %s", session.session_id)
            # remove_session is called by _serve loop on connection error;
            # avoid re-entrant lock issues by deferring cleanup.
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
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                session.state = SessionState.CLOSED
                if session.conn is not None:
                    with contextlib.suppress(Exception):
                        session.conn.close()
                logger.info("Session removed: %s", session_id)

    def get_active_sessions(self) -> list[SessionInfo]:
        with self._lock:
            return [s for s in self._sessions.values() if s.state == SessionState.ACTIVE]

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
