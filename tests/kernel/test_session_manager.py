from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from iris.io.models import AuthMessage, Direction, Message, Permission
from iris.io.session.manager import SessionConfig, SessionManager


def _get_session_id(manager: SessionManager) -> str:
    conn = MagicMock()
    msg = AuthMessage(role="cli", permissions=[Permission.PERMISSION_RECEIVE_CHAT, Permission.PERMISSION_SEND_CHAT])
    response = manager.authenticate(conn, msg)
    assert response.session_id is not None
    return response.session_id


class TestSessionManager:
    @pytest.fixture
    def manager(self) -> SessionManager:
        return SessionManager(SessionConfig())

    def test_authenticate_generates_session_id(self, manager: SessionManager) -> None:
        conn = MagicMock()
        msg = AuthMessage(role="cli", permissions=[Permission.PERMISSION_RECEIVE_CHAT])
        response = manager.authenticate(conn, msg)

        assert response.msg_type == "auth_success"
        assert response.session_id is not None
        assert len(response.session_id) == 16
        assert manager.is_session_active(response.session_id) is True

    def test_authenticate_rejects_invalid_token(self) -> None:
        manager = SessionManager(SessionConfig(access_token="my-secret"))
        conn = MagicMock()
        msg = AuthMessage(access_token="wrong")
        response = manager.authenticate(conn, msg)

        assert response.msg_type == "auth_failure"
        assert response.error_message is not None

    def test_authenticate_stores_conn(self, manager: SessionManager) -> None:
        conn = MagicMock()
        msg = AuthMessage(role="cli", permissions=[Permission.PERMISSION_RECEIVE_CHAT])
        response = manager.authenticate(conn, msg)
        assert response.session_id is not None

        session_id = response.session_id
        assert manager.is_session_active(session_id) is True

    def test_session_active_immediately_after_auth(self, manager: SessionManager) -> None:
        session_id = _get_session_id(manager)
        assert manager.is_session_active(session_id) is True

    def test_remove_session_cleans_up(self, manager: SessionManager) -> None:
        session_id = _get_session_id(manager)

        manager.remove_session(session_id)
        assert manager.is_session_active(session_id) is False

    def test_route_message_delivers_to_conn(self, manager: SessionManager) -> None:
        conn = MagicMock()
        msg = AuthMessage(role="cli", permissions=[Permission.PERMISSION_RECEIVE_CHAT])
        response = manager.authenticate(conn, msg)
        assert response.session_id is not None

        m = Message(
            source_role="mind",
            target_role="cli",
            session_id=response.session_id,
            direction=Direction.RESPONSE,
            msg_type="chat",
            content="hello",
        )
        manager.route_message(m)
        conn.send_bytes.assert_called_once()

    def test_route_message_broadcasts_to_all_active_sessions(self, manager: SessionManager) -> None:
        conn1 = MagicMock()
        conn2 = MagicMock()
        r1 = manager.authenticate(conn1, AuthMessage(role="cli", permissions=[Permission.PERMISSION_RECEIVE_CHAT]))
        r2 = manager.authenticate(conn2, AuthMessage(role="cli", permissions=[Permission.PERMISSION_RECEIVE_CHAT]))
        assert r1.session_id is not None
        assert r2.session_id is not None

        m = Message(
            source_role="mind",
            target_role="*",
            session_id="",
            direction=Direction.EVENT,
            msg_type="chat",
            content="hello",
        )
        manager.route_message(m)

        conn1.send_bytes.assert_called_once()
        conn2.send_bytes.assert_called_once()

    def test_route_message_skips_wrong_permission(self, manager: SessionManager) -> None:
        conn = MagicMock()
        r = manager.authenticate(conn, AuthMessage(role="cli", permissions=[]))
        assert r.session_id is not None

        m = Message(
            source_role="mind",
            target_role="*",
            session_id="",
            direction=Direction.EVENT,
            msg_type="chat",
            content="hello",
        )
        manager.route_message(m)
        conn.send_bytes.assert_not_called()

    def test_get_active_sessions(self, manager: SessionManager) -> None:
        _get_session_id(manager)
        _get_session_id(manager)

        active = manager.get_active_sessions()
        assert len(active) == 2

    def test_session_ids_are_unique(self, manager: SessionManager) -> None:
        session_id1 = _get_session_id(manager)
        session_id2 = _get_session_id(manager)

        assert session_id1 != session_id2

    def test_update_activity_touches_last_activity(self, manager: SessionManager) -> None:
        session_id = _get_session_id(manager)
        old = manager._sessions[session_id].last_activity

        manager.update_activity(session_id)
        new = manager._sessions[session_id].last_activity

        assert new > old

    def test_update_activity_unknown_session(self, manager: SessionManager) -> None:
        manager.update_activity("nonexistent")

    def test_route_message_clears_conn_on_disconnect(self, manager: SessionManager) -> None:
        conn = MagicMock()
        conn.send_bytes.side_effect = BrokenPipeError
        msg = AuthMessage(role="cli", permissions=[Permission.PERMISSION_RECEIVE_CHAT])
        response = manager.authenticate(conn, msg)
        assert response.session_id is not None

        m = Message(
            source_role="mind",
            target_role="cli",
            session_id=response.session_id,
            direction=Direction.RESPONSE,
            msg_type="chat",
            content="x",
        )
        manager.route_message(m)

        info = manager.get_session_info(response.session_id)
        assert info is not None
        assert info.conn is None

    def test_authenticate_stores_permissions(self, manager: SessionManager) -> None:
        conn = MagicMock()
        msg = AuthMessage(role="cli", permissions=[Permission.PERMISSION_RECEIVE_LOG])
        response = manager.authenticate(conn, msg)
        assert response.session_id is not None

        info = manager._sessions[response.session_id]
        assert info.role == "cli"
        assert info.permissions == [Permission.PERMISSION_RECEIVE_LOG]

    def test_authenticate_stores_identity_and_description(self, manager: SessionManager) -> None:
        conn = MagicMock()
        msg = AuthMessage(
            role="cli",
            permissions=[Permission.PERMISSION_RECEIVE_CHAT],
            identity="debug-console",
            description="Debug console on Mac mini",
        )
        response = manager.authenticate(conn, msg)
        assert response.session_id is not None

        info = manager._sessions[response.session_id]
        assert info.identity == "debug-console"
        assert info.description == "Debug console on Mac mini"

    def test_get_sessions_summary_returns_empty_when_no_sessions(self, manager: SessionManager) -> None:
        assert manager.get_sessions_summary() == ""

    def test_get_sessions_summary_includes_active_sessions(self, manager: SessionManager) -> None:
        conn = MagicMock()
        manager.authenticate(
            conn,
            AuthMessage(
                role="cli",
                permissions=[Permission.PERMISSION_RECEIVE_CHAT, Permission.PERMISSION_RECEIVE_LOG],
            ),
        )
        summary = manager.get_sessions_summary()
        assert "cli" in summary
        assert "receive_chat" in summary
        assert "receive_log" in summary
        assert summary.startswith("Connected clients:")
