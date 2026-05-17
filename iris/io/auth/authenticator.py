from __future__ import annotations

import logging
import os

from iris.io.models import AuthMessage

logger = logging.getLogger(__name__)


class Authenticator:
    """セッション認証を担当する。"""

    def __init__(self, access_token: str = "") -> None:
        self._access_token = access_token or os.environ.get("IRIS_ACCESS_TOKEN", "")

    def authenticate(self, msg: AuthMessage) -> tuple[bool, str | None]:
        if self._access_token and msg.access_token != self._access_token:
            logger.warning("Auth failed: invalid access_token")
            return False, "invalid access_token"

        logger.debug("Authenticated connection (mode=%s)", msg.mode.value)
        return True, None
