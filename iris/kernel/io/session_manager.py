from __future__ import annotations

import contextlib
import logging
import threading
from datetime import datetime
from multiprocessing.connection import Connection
from uuid import uuid4

from iris.kernel.io.authenticator import Authenticator
from iris.kernel.io.models import (
    AuthMessage,
    ConnectionMode,
    ControlMessage,
    OutputMessage,
    SessionInfo,
    SessionState,
)

logger = logging.getLogger(__name__)


class SessionConfig:
    auth_timeout_sec: int = 30
    pairing_timeout_sec: int = 60


class SessionManager:
    """セッションのライフサイクルを管理する。

    認証、Input/Output接続のペアリング、メッセージルーティングを担当。
    """

    def __init__(self, config: SessionConfig | None = None) -> None:
        self._sessions: dict[str, SessionInfo] = {}
        self._authenticator = Authenticator()
        self._config = config or SessionConfig()
        self._lock = threading.Lock()

    def on_control_connect(self, conn: Connection, msg: AuthMessage) -> ControlMessage:
        """Control接続時に認証処理を行い、session_idを生成する。"""
        with self._lock:
            success, error = self._authenticator.authenticate(msg)
            if not success:
                return ControlMessage(
                    msg_type="auth_failure",
                    error_message=error,
                )

            session_id = uuid4().hex[:16]
            session = SessionInfo(
                session_id=session_id,
                state=SessionState.AUTHENTICATING,
                mode=msg.mode,
                control_conn=conn,
            )
            self._sessions[session_id] = session

            if msg.mode == ConnectionMode.INPUT_ONLY:
                session.state = SessionState.WAITING_INPUT
            elif msg.mode == ConnectionMode.OUTPUT_ONLY:
                session.state = SessionState.WAITING_OUTPUT
            else:
                session.state = SessionState.WAITING_INPUT

            logger.info("Session created: %s (mode=%s)", session_id, msg.mode.value)
            return ControlMessage(msg_type="auth_success", session_id=session_id)

    def on_input_connect(self, session_id: str, conn: Connection) -> bool:
        """Input接続時にセッションと紐付ける。"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                logger.warning("Input connect for unknown session: %s", session_id)
                return False

            if session.mode == ConnectionMode.OUTPUT_ONLY:
                logger.warning("Input connect rejected: session %s is OUTPUT_ONLY", session_id)
                return False

            session.input_conn = conn
            session.last_activity = datetime.now()

            if session.mode == ConnectionMode.INPUT_ONLY:
                session.state = SessionState.ACTIVE
                logger.info("Session ACTIVE (INPUT_ONLY): %s", session_id)
            elif session.output_conn is not None:
                session.state = SessionState.ACTIVE
                logger.info("Session ACTIVE (BIDIRECTIONAL): %s", session_id)
            else:
                session.state = SessionState.WAITING_OUTPUT
                logger.info("Session waiting for output: %s", session_id)

            return True

    def on_output_connect(self, session_id: str, conn: Connection) -> bool:
        """Output接続時にセッションと紐付ける。"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                logger.warning("Output connect for unknown session: %s", session_id)
                return False

            if session.mode == ConnectionMode.INPUT_ONLY:
                logger.warning("Output connect rejected: session %s is INPUT_ONLY", session_id)
                return False

            session.output_conn = conn
            session.last_activity = datetime.now()

            if session.mode == ConnectionMode.OUTPUT_ONLY:
                session.state = SessionState.ACTIVE
                logger.info("Session ACTIVE (OUTPUT_ONLY): %s", session_id)
            elif session.input_conn is not None:
                session.state = SessionState.ACTIVE
                logger.info("Session ACTIVE (BIDIRECTIONAL): %s", session_id)
            else:
                session.state = SessionState.WAITING_INPUT
                logger.info("Session waiting for input: %s", session_id)

            return True

    def route_output(self, session_id: str, message: OutputMessage) -> None:
        """セッションに対応するOutput接続にメッセージをルーティングする。"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                logger.warning("Output route for unknown session: %s", session_id)
                return

            if session.output_conn is None:
                logger.warning("Output route for session without output connection: %s", session_id)
                return

            conn = session.output_conn

        message.session_id = session_id
        raw = message.model_dump_json().encode("utf-8")
        try:
            conn.send_bytes(raw)
        except (BrokenPipeError, ConnectionError, EOFError):
            logger.warning("Output connection lost for session: %s", session_id)
            with self._lock:
                session.output_conn = None

    def is_session_active(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            return session is not None and session.state == SessionState.ACTIVE

    def get_session_mode(self, session_id: str) -> ConnectionMode | None:
        with self._lock:
            session = self._sessions.get(session_id)
            return session.mode if session else None

    def remove_session(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                session.state = SessionState.CLOSED
                if session.control_conn:
                    with contextlib.suppress(Exception):
                        session.control_conn.close()
                if session.input_conn:
                    with contextlib.suppress(Exception):
                        session.input_conn.close()
                if session.output_conn:
                    with contextlib.suppress(Exception):
                        session.output_conn.close()
                logger.info("Session removed: %s", session_id)

    def get_active_sessions(self) -> list[SessionInfo]:
        with self._lock:
            return [s for s in self._sessions.values() if s.state == SessionState.ACTIVE]
