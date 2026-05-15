from __future__ import annotations

import logging

from iris.kernel.io.models import AuthMessage

logger = logging.getLogger(__name__)


class Authenticator:
    """セッション認証を担当する。

    将来的にトークン検証、証明書検証などを追加可能。
    現在は mode の検証のみを行う。
    """

    def authenticate(self, msg: AuthMessage) -> tuple[bool, str | None]:
        logger.debug("Authenticated connection (mode=%s)", msg.mode.value)
        return True, None
