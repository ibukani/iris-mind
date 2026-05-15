from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from iris.kernel.io.models import AuthMessage, ConnectionMode, OutputMessage
from iris.kernel.io.session_manager import SessionConfig, SessionManager


def _get_session_id(manager: SessionManager, mode: ConnectionMode) -> str:
    conn = MagicMock()
    msg = AuthMessage(mode=mode)
    response = manager.on_control_connect(conn, msg)
    assert response.session_id is not None
    return response.session_id


class TestSessionManager:
    @pytest.fixture
    def manager(self) -> SessionManager:
        return SessionManager(SessionConfig())

    def test_on_control_connect_generates_session_id(self, manager: SessionManager) -> None:
        conn = MagicMock()
        msg = AuthMessage(mode=ConnectionMode.BIDIRECTIONAL)
        response = manager.on_control_connect(conn, msg)

        assert response.msg_type == "auth_success"
        assert response.session_id is not None
        assert len(response.session_id) == 16
        assert manager.is_session_active(response.session_id) is False

    def test_on_control_connect_rejects_empty_mode(self, manager: SessionManager) -> None:
        conn = MagicMock()
        msg = AuthMessage(mode=ConnectionMode.BIDIRECTIONAL)
        response = manager.on_control_connect(conn, msg)

        assert response.msg_type == "auth_success"
        assert response.session_id is not None

    def test_on_input_connect_activates_input_only_session(self, manager: SessionManager) -> None:
        session_id = _get_session_id(manager, ConnectionMode.INPUT_ONLY)
        input_conn = MagicMock()
        result = manager.on_input_connect(session_id, input_conn)

        assert result is True
        assert manager.is_session_active(session_id) is True

    def test_on_output_connect_activates_output_only_session(self, manager: SessionManager) -> None:
        session_id = _get_session_id(manager, ConnectionMode.OUTPUT_ONLY)
        output_conn = MagicMock()
        result = manager.on_output_connect(session_id, output_conn)

        assert result is True
        assert manager.is_session_active(session_id) is True

    def test_on_input_connect_rejects_for_output_only_mode(self, manager: SessionManager) -> None:
        session_id = _get_session_id(manager, ConnectionMode.OUTPUT_ONLY)
        input_conn = MagicMock()
        result = manager.on_input_connect(session_id, input_conn)

        assert result is False

    def test_on_output_connect_rejects_for_input_only_mode(self, manager: SessionManager) -> None:
        session_id = _get_session_id(manager, ConnectionMode.INPUT_ONLY)
        output_conn = MagicMock()
        result = manager.on_output_connect(session_id, output_conn)

        assert result is False

    def test_bidirectional_session_requires_both_connections(self, manager: SessionManager) -> None:
        session_id = _get_session_id(manager, ConnectionMode.BIDIRECTIONAL)

        input_conn = MagicMock()
        manager.on_input_connect(session_id, input_conn)
        assert manager.is_session_active(session_id) is False

        output_conn = MagicMock()
        manager.on_output_connect(session_id, output_conn)
        assert manager.is_session_active(session_id) is True

    def test_remove_session_cleans_up(self, manager: SessionManager) -> None:
        session_id = _get_session_id(manager, ConnectionMode.INPUT_ONLY)
        manager.on_input_connect(session_id, MagicMock())

        manager.remove_session(session_id)
        assert manager.is_session_active(session_id) is False

    def test_get_session_mode(self, manager: SessionManager) -> None:
        session_id = _get_session_id(manager, ConnectionMode.INPUT_ONLY)
        mode = manager.get_session_mode(session_id)
        assert mode == ConnectionMode.INPUT_ONLY

    def test_get_session_mode_returns_none_for_unknown(self, manager: SessionManager) -> None:
        assert manager.get_session_mode("unknown") is None

    def test_route_output_with_no_output_connection(self, manager: SessionManager) -> None:
        session_id = _get_session_id(manager, ConnectionMode.INPUT_ONLY)
        manager.on_input_connect(session_id, MagicMock())

        output_msg = OutputMessage(session_id=session_id, msg_type="test", content="hello")
        manager.route_output(session_id, output_msg)

    def test_get_active_sessions(self, manager: SessionManager) -> None:
        session_id1 = _get_session_id(manager, ConnectionMode.INPUT_ONLY)
        manager.on_input_connect(session_id1, MagicMock())

        _get_session_id(manager, ConnectionMode.OUTPUT_ONLY)

        active = manager.get_active_sessions()
        assert len(active) == 1
        assert active[0].session_id == session_id1

    def test_session_ids_are_unique(self, manager: SessionManager) -> None:
        session_id1 = _get_session_id(manager, ConnectionMode.BIDIRECTIONAL)
        session_id2 = _get_session_id(manager, ConnectionMode.BIDIRECTIONAL)

        assert session_id1 != session_id2
