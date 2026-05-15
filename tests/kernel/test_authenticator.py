from __future__ import annotations

from iris.kernel.io.authenticator import Authenticator
from iris.kernel.io.models import AuthMessage, ConnectionMode


class TestAuthenticator:
    def test_authenticate_with_valid_message(self) -> None:
        auth = Authenticator()
        msg = AuthMessage(mode=ConnectionMode.BIDIRECTIONAL)
        success, error = auth.authenticate(msg)
        assert success is True
        assert error is None

    def test_authenticate_with_token(self) -> None:
        auth = Authenticator()
        msg = AuthMessage(auth_token="some-token", mode=ConnectionMode.BIDIRECTIONAL)
        success, error = auth.authenticate(msg)
        assert success is True
        assert error is None

    def test_authenticate_with_different_modes(self) -> None:
        auth = Authenticator()
        for mode in ConnectionMode:
            msg = AuthMessage(mode=mode)
            success, error = auth.authenticate(msg)
            assert success is True
            assert error is None
