from __future__ import annotations

from datetime import datetime
import threading
from typing import TYPE_CHECKING

from loguru import logger

from iris.io.models import CommandOutput, ControlMessage, Message, Permission, SessionInfo, SessionState

if TYPE_CHECKING:
    from iris.room.store import RoomStore

from .permissions import _MSG_PERMISSION_MAP, send_bytes_to_session


def compute_offline_duration(
    last_disconnect_times: dict[str, datetime],
    session: SessionInfo,
    now: datetime | None = None,
) -> str:
    if now is None:
        now = datetime.now()
    key = f"{session.role}:{session.session_tag}" if session.session_tag else session.role
    disc_time = last_disconnect_times.get(key)
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


class _SessionRouter:
    def __init__(
        self,
        sessions: dict[str, SessionInfo],
        lock: threading.Lock,
        last_disconnect_times: dict[str, datetime],
    ) -> None:
        self._sessions = sessions
        self._lock = lock
        self._last_disconnect_times = last_disconnect_times

    def _resolve_route_targets(self, msg: Message) -> tuple[SessionInfo | None, list[SessionInfo]]:
        with self._lock:
            if msg.session_id:
                s = self._sessions.get(msg.session_id)
                if s is not None and s.state == SessionState.ACTIVE and s.conn is not None:
                    return s, []
                if s is None:
                    logger.debug("route_message: session {} not found", msg.session_id)
                else:
                    logger.debug("route_message: session {} not active or no conn", msg.session_id)
                return None, []
            if msg.target_role == "*":
                return None, [
                    s for s in self._sessions.values() if s.state == SessionState.ACTIVE and s.conn is not None
                ]
            return None, [
                s
                for s in self._sessions.values()
                if s.state == SessionState.ACTIVE and s.role == msg.target_role and s.conn is not None
            ]

    def _send_to_targets(self, msg: Message, targets: list[SessionInfo], log_prefix: str) -> None:
        permission = _MSG_PERMISSION_MAP.get(msg.msg_type)
        skipped: list[str] = []
        for s in targets:
            if permission is not None and permission not in s.permissions:
                skipped.append(s.session_id)
                continue
            send_bytes_to_session(s, msg)
        if skipped:
            logger.debug("{}: skipped {} session(s) due to permission: {}", log_prefix, len(skipped), skipped)
        if not targets:
            logger.debug("{}: no active sessions to route msg_type={}", log_prefix, msg.msg_type)

    def route_message(self, msg: Message) -> None:
        session, targets = self._resolve_route_targets(msg)
        if session is not None:
            send_bytes_to_session(session, msg)
            return
        self._send_to_targets(msg, targets, "route_message")

    def route_to_room(self, msg: Message, room_id: str, room_store: RoomStore) -> None:
        session_ids = room_store.find_all_session_ids_for_room(room_id)
        not_active: list[str] = []
        targets: list[SessionInfo] = []

        with self._lock:
            for sid in session_ids:
                s = self._sessions.get(sid)
                if s is not None and s.state == SessionState.ACTIVE and s.conn is not None:
                    targets.append(s)
                else:
                    not_active.append(sid)

        self._send_to_targets(msg, targets, "route_to_room")
        if not_active:
            logger.debug("route_to_room: {} session(s) not active in room {}", len(not_active), room_id)

    def route_control_message(self, control_msg: ControlMessage, session_id: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            logger.warning("Control message route for unknown session: {}", session_id)
            return
        if session.state != SessionState.ACTIVE or session.conn is None:
            return
        raw = control_msg.model_dump_json().encode("utf-8")
        session.conn.send_bytes(raw)

    def broadcast_control_message(self, control_msg: ControlMessage) -> None:
        with self._lock:
            targets = [
                s
                for s in self._sessions.values()
                if s.state == SessionState.ACTIVE
                and s.conn is not None
                and Permission.PERMISSION_RECEIVE_CHAT in s.permissions
            ]

        for session in targets:
            send_bytes_to_session(session, control_msg)

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
