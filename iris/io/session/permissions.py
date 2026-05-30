from __future__ import annotations

from datetime import datetime

from loguru import logger

from iris.io.models import CommandOutput, Message, Permission, SessionInfo, SystemMessage

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
    "voice_indicator": Permission.PERMISSION_SEND_VOICE_INDICATOR,
}


def send_bytes_to_session(session: SessionInfo, msg: Message | CommandOutput | SystemMessage) -> None:
    conn = session.conn
    if conn is None:
        return
    raw = msg.model_dump_json().encode("utf-8")
    try:
        conn.send_bytes(raw)
        session.last_activity = datetime.now()
        logger.debug("Sent {} bytes to session={}", len(raw), session.session_id)
    except (BrokenPipeError, ConnectionError, EOFError):
        logger.warning("Connection lost for session: {}", session.session_id)
        session.conn = None
