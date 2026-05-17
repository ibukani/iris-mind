from __future__ import annotations

import contextlib
import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from multiprocessing.connection import Connection
from uuid import uuid4

from iris.io.auth.authenticator import Authenticator
from iris.io.models import (
    AuthMessage,
    ConnectionMode,
    ControlMessage,
    OutputMessage,
    SessionInfo,
    SessionState,
)

logger = logging.getLogger(__name__)


@dataclass
class SessionConfig:
    host: str = "127.0.0.1"
    port: int = 9876
    access_token: str = ""


class SessionManager:
    """セッションのライフサイクルを管理する。"""

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
                mode=msg.mode,
                roles=msg.roles,
                identity=msg.identity,
                description=msg.description,
                conn=conn,
                created_at=now,
                last_activity=now,
            )
            self._sessions[session_id] = session

            logger.info("Session created: %s (mode=%s)", session_id, msg.mode.value)
            return ControlMessage(msg_type="auth_success", session_id=session_id)

    def route_output(self, session_id: str, message: OutputMessage) -> None:
        if not session_id:
            self._broadcast_output(message)
            return

        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                logger.warning("Output route for unknown session: %s", session_id)
                return

            if session.conn is None:
                logger.warning("Output route for session without connection: %s", session_id)
                return

            if session.mode == ConnectionMode.INPUT_ONLY:
                logger.warning("Output route rejected: session %s is INPUT_ONLY", session_id)
                return

            conn = session.conn
            session.last_activity = datetime.now()

        raw = message.model_dump_json().encode("utf-8")
        try:
            conn.send_bytes(raw)
        except (BrokenPipeError, ConnectionError, EOFError):
            logger.warning("Output connection lost for session: %s", session_id)
            self.remove_session(session_id)

    def _broadcast_output(self, message: OutputMessage) -> None:
        with self._lock:
            targets = list(self._sessions.items())

        for sid, session in targets:
            if session.state != SessionState.ACTIVE:
                continue
            if session.conn is None:
                continue
            if session.mode == ConnectionMode.INPUT_ONLY:
                continue
            raw = message.model_dump_json().encode("utf-8")
            try:
                session.conn.send_bytes(raw)
                session.last_activity = datetime.now()
            except (BrokenPipeError, ConnectionError, EOFError):
                self.remove_session(sid)

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

    def get_session_mode(self, session_id: str) -> ConnectionMode | None:
        with self._lock:
            session = self._sessions.get(session_id)
            return session.mode if session else None

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

    def get_roles_summary(self) -> str:
        with self._lock:
            sessions = [s for s in self._sessions.values() if s.state == SessionState.ACTIVE]
        if not sessions:
            return ""
        lines: list[str] = []
        for s in sessions:
            roles_str = ", ".join(r.value for r in s.roles)
            lines.append(f"[{roles_str}]")
        return "Active sessions:\n" + "\n".join(lines)
