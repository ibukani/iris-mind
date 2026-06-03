from __future__ import annotations

import os
import secrets

from loguru import logger

from iris.io.models import AuthMessage


class Authenticator:
    """セッション認証を担当する。"""

    def __init__(self, access_token: str = "") -> None:
        self._access_token = access_token or os.environ.get("IRIS_ACCESS_TOKEN", "")

    def authenticate(self, msg: AuthMessage) -> tuple[bool, str | None]:
        if self._access_token and msg.access_token != self._access_token:
            logger.warning("Auth failed: invalid access_token")
            return False, "invalid access_token"

        logger.debug("Authenticated connection (role={})", msg.role)
        return True, None

    def set_token(self, token: str) -> None:
        self._access_token = token

    def get_token(self) -> str:
        return self._access_token

    @staticmethod
    def generate_token() -> str:
        return secrets.token_urlsafe(32)
