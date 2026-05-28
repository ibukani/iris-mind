from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from iris.io.transport.grpc_listener import GrpcListener

if TYPE_CHECKING:
    from iris.io.gateway import _IOGateway
    from iris.io.models import Message, SystemMessage
    from iris.io.session.manager import SessionManager


class IOManager:
    def __init__(
        self,
        gateway: _IOGateway,
        session_manager: SessionManager,
        grpc_listener: GrpcListener,
    ) -> None:
        self._gateway = gateway
        self._session_mgr = session_manager
        self._grpc_listener = grpc_listener
        self._host: str = ""
        self._port: int = 0

        self._grpc_listener.set_on_message(gateway.on_grpc_message)
        self._grpc_listener.set_on_command(gateway.on_grpc_command)
        self._grpc_listener.set_on_system_message(gateway.on_grpc_system)

    def set_command_handler(self, handler: Callable[[str, str], str]) -> None:
        self._gateway.set_command_handler(handler)

    def set_system_handler(self, handler: Callable[[SystemMessage, str], SystemMessage | None]) -> None:
        """system メッセージハンドラを設定する。

        handler は SystemMessage と session_id を受け取り、
        レスポンスの SystemMessage または None を返す。
        EventBus の publish/subscribe は handler 内で完結する。
        """
        self._gateway.set_system_handler(handler)

    def set_message_handler(self, handler: Callable[[Message], None]) -> None:
        """通常メッセージハンドラを設定する。

        handler は Message を受け取り、EventBus への publish を含む処理を行う。
        Gateway は IO アダプタとしての責務のみを持ち、EventBus を直接操作しない。
        """
        self._gateway.set_message_handler(handler)

    def start(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._grpc_listener.start(host=host, port=port)

    def stop(self) -> None:
        self._grpc_listener.stop()

    def get_state(self) -> dict:
        sessions = self._session_mgr.get_sessions_summary() if self._session_mgr else ""
        return {
            "listening": f"{self._host}:{self._port}" if self._host else "not started",
            "sessions": len(sessions.splitlines()) if sessions else 0,
        }
