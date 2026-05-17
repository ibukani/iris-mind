from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from iris.io.models import AuthMessage, ConnectionMode, OutputMessage, SessionRole
from iris.io.session.manager import SessionConfig, SessionManager


def _get_session_id(manager: SessionManager, mode: ConnectionMode) -> str:
    conn = MagicMock()
    msg = AuthMessage(mode=mode)
    response = manager.authenticate(conn, msg)
    assert response.session_id is not None
    return response.session_id


class TestSessionManager:
    @pytest.fixture
    def manager(self) -> SessionManager:
        return SessionManager(SessionConfig())

    def test_authenticate_generates_session_id(self, manager: SessionManager) -> None:
        conn = MagicMock()
        msg = AuthMessage(mode=ConnectionMode.BIDIRECTIONAL)
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
        msg = AuthMessage(mode=ConnectionMode.BIDIRECTIONAL)
        response = manager.authenticate(conn, msg)
        assert response.session_id is not None

        session_id = response.session_id
        assert manager.is_session_active(session_id) is True

    def test_session_active_immediately_after_auth(self, manager: SessionManager) -> None:
        session_id = _get_session_id(manager, ConnectionMode.BIDIRECTIONAL)
        assert manager.is_session_active(session_id) is True

    def test_session_active_for_input_only(self, manager: SessionManager) -> None:
        session_id = _get_session_id(manager, ConnectionMode.INPUT_ONLY)
        assert manager.is_session_active(session_id) is True

    def test_session_active_for_output_only(self, manager: SessionManager) -> None:
        session_id = _get_session_id(manager, ConnectionMode.OUTPUT_ONLY)
        assert manager.is_session_active(session_id) is True

    def test_remove_session_cleans_up(self, manager: SessionManager) -> None:
        session_id = _get_session_id(manager, ConnectionMode.INPUT_ONLY)

        manager.remove_session(session_id)
        assert manager.is_session_active(session_id) is False

    def test_get_session_mode(self, manager: SessionManager) -> None:
        session_id = _get_session_id(manager, ConnectionMode.INPUT_ONLY)
        mode = manager.get_session_mode(session_id)
        assert mode == ConnectionMode.INPUT_ONLY

    def test_get_session_mode_returns_none_for_unknown(self, manager: SessionManager) -> None:
        assert manager.get_session_mode("unknown") is None

    def test_route_output_rejects_input_only(self, manager: SessionManager) -> None:
        session_id = _get_session_id(manager, ConnectionMode.INPUT_ONLY)

        output_msg = OutputMessage(msg_type="test", content="hello")
        manager.route_output(session_id, output_msg)

    def test_route_output_delivers_to_conn(self, manager: SessionManager) -> None:
        conn = MagicMock()
        msg = AuthMessage(mode=ConnectionMode.BIDIRECTIONAL)
        response = manager.authenticate(conn, msg)
        assert response.session_id is not None
        assert manager.is_session_active(response.session_id) is True

        output_msg = OutputMessage(msg_type="test", content="hello")
        manager.route_output(response.session_id, output_msg)
        conn.send_bytes.assert_called_once()

    def test_route_output_broadcasts_to_all_active_sessions(self, manager: SessionManager) -> None:
        conn1 = MagicMock()
        conn2 = MagicMock()
        msg1 = AuthMessage(mode=ConnectionMode.BIDIRECTIONAL)
        msg2 = AuthMessage(mode=ConnectionMode.BIDIRECTIONAL)
        r1 = manager.authenticate(conn1, msg1)
        r2 = manager.authenticate(conn2, msg2)
        assert r1.session_id is not None
        assert r2.session_id is not None

        output_msg = OutputMessage(msg_type="broadcast", content="hello")
        manager.route_output("", output_msg)

        conn1.send_bytes.assert_called_once()
        conn2.send_bytes.assert_called_once()

    def test_route_output_skips_input_only_on_broadcast(self, manager: SessionManager) -> None:
        conn1 = MagicMock()
        conn2 = MagicMock()
        r1 = manager.authenticate(conn1, AuthMessage(mode=ConnectionMode.BIDIRECTIONAL))
        r2 = manager.authenticate(conn2, AuthMessage(mode=ConnectionMode.INPUT_ONLY))
        assert r1.session_id is not None
        assert r2.session_id is not None

        output_msg = OutputMessage(msg_type="broadcast", content="hello")
        manager.route_output("", output_msg)

        conn1.send_bytes.assert_called_once()
        conn2.send_bytes.assert_not_called()

    def test_get_active_sessions(self, manager: SessionManager) -> None:
        _get_session_id(manager, ConnectionMode.INPUT_ONLY)
        _get_session_id(manager, ConnectionMode.OUTPUT_ONLY)

        active = manager.get_active_sessions()
        assert len(active) == 2

    def test_session_ids_are_unique(self, manager: SessionManager) -> None:
        session_id1 = _get_session_id(manager, ConnectionMode.BIDIRECTIONAL)
        session_id2 = _get_session_id(manager, ConnectionMode.BIDIRECTIONAL)

        assert session_id1 != session_id2

    def test_update_activity_touches_last_activity(self, manager: SessionManager) -> None:
        session_id = _get_session_id(manager, ConnectionMode.BIDIRECTIONAL)
        old = manager._sessions[session_id].last_activity

        manager.update_activity(session_id)
        new = manager._sessions[session_id].last_activity

        assert new > old

    def test_update_activity_unknown_session(self, manager: SessionManager) -> None:
        manager.update_activity("nonexistent")

    def test_route_output_removes_session_on_disconnect(self, manager: SessionManager) -> None:
        conn = MagicMock()
        conn.send_bytes.side_effect = BrokenPipeError
        msg = AuthMessage(mode=ConnectionMode.BIDIRECTIONAL)
        response = manager.authenticate(conn, msg)
        assert response.session_id is not None

        output_msg = OutputMessage(msg_type="test", content="x")
        manager.route_output(response.session_id, output_msg)

        assert manager.is_session_active(response.session_id) is False

    def test_authenticate_stores_roles(self, manager: SessionManager) -> None:
        conn = MagicMock()
        msg = AuthMessage(mode=ConnectionMode.BIDIRECTIONAL, roles=[SessionRole.LOG])
        response = manager.authenticate(conn, msg)
        assert response.session_id is not None

        info = manager._sessions[response.session_id]
        assert info.roles == [SessionRole.LOG]

    def test_authenticate_stores_identity_and_description(self, manager: SessionManager) -> None:
        conn = MagicMock()
        msg = AuthMessage(
            mode=ConnectionMode.BIDIRECTIONAL, identity="debug-console", description="Debug console on Mac mini"
        )
        response = manager.authenticate(conn, msg)
        assert response.session_id is not None

        info = manager._sessions[response.session_id]
        assert info.identity == "debug-console"
        assert info.description == "Debug console on Mac mini"

    def test_get_roles_summary_returns_empty_when_no_sessions(self, manager: SessionManager) -> None:
        assert manager.get_roles_summary() == ""

    def test_get_roles_summary_includes_active_sessions(self, manager: SessionManager) -> None:
        conn = MagicMock()
        manager.authenticate(
            conn,
            AuthMessage(
                mode=ConnectionMode.BIDIRECTIONAL,
                roles=[SessionRole.CONVERSATION_OUTPUT, SessionRole.LOG],
            ),
        )
        summary = manager.get_roles_summary()
        assert "conversation_output" in summary
        assert "log" in summary
        assert summary.startswith("Active sessions:")
