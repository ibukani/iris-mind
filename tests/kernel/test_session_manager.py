from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from iris.kernel.io.models import AuthMessage, ConnectionMode, OutputMessage
from iris.kernel.io.session_manager import SessionConfig, SessionManager


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

        output_msg = OutputMessage(session_id=session_id, msg_type="test", content="hello")
        manager.route_output(session_id, output_msg)

    def test_route_output_delivers_to_conn(self, manager: SessionManager) -> None:
        conn = MagicMock()
        msg = AuthMessage(mode=ConnectionMode.BIDIRECTIONAL)
        response = manager.authenticate(conn, msg)
        assert response.session_id is not None
        assert manager.is_session_active(response.session_id) is True

        output_msg = OutputMessage(session_id=response.session_id, msg_type="test", content="hello")
        manager.route_output(response.session_id, output_msg)
        conn.send_bytes.assert_called_once()

    def test_route_output_for_unknown_session(self, manager: SessionManager) -> None:
        output_msg = OutputMessage(session_id="unknown", msg_type="test", content="hello")
        manager.route_output("unknown", output_msg)

    def test_get_active_sessions(self, manager: SessionManager) -> None:
        _get_session_id(manager, ConnectionMode.INPUT_ONLY)
        _get_session_id(manager, ConnectionMode.OUTPUT_ONLY)

        active = manager.get_active_sessions()
        assert len(active) == 2

    def test_session_ids_are_unique(self, manager: SessionManager) -> None:
        session_id1 = _get_session_id(manager, ConnectionMode.BIDIRECTIONAL)
        session_id2 = _get_session_id(manager, ConnectionMode.BIDIRECTIONAL)

        assert session_id1 != session_id2
