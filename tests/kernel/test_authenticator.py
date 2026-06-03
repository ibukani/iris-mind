from __future__ import annotations

from iris.io.auth.authenticator import Authenticator
from iris.io.models import AuthMessage, Permission


class TestAuthenticator:
    def test_authenticate_with_valid_message(self) -> None:
        auth = Authenticator()
        msg = AuthMessage(role="cli", permissions=[Permission.PERMISSION_SEND_CHAT])
        success, error = auth.authenticate(msg)
        assert success is True
        assert error is None

    def test_authenticate_with_access_token(self) -> None:
        auth = Authenticator(access_token="my-secret")
        msg = AuthMessage(access_token="my-secret", role="cli", permissions=[Permission.PERMISSION_SEND_CHAT])
        success, error = auth.authenticate(msg)
        assert success is True
        assert error is None

    def test_authenticate_rejects_wrong_token(self) -> None:
        auth = Authenticator(access_token="my-secret")
        msg = AuthMessage(access_token="wrong-token", role="cli")
        success, error = auth.authenticate(msg)
        assert success is False
        assert error == "invalid access_token"

    def test_authenticate_rejects_missing_token(self) -> None:
        auth = Authenticator(access_token="my-secret")
        msg = AuthMessage(role="cli")
        success, error = auth.authenticate(msg)
        assert success is False
        assert error == "invalid access_token"

    def test_authenticate_with_permissions(self) -> None:
        auth = Authenticator()
        msg = AuthMessage(role="cli", permissions=[Permission.PERMISSION_SEND_CHAT, Permission.PERMISSION_RECEIVE_CHAT])
        success, error = auth.authenticate(msg)
        assert success is True
        assert error is None
