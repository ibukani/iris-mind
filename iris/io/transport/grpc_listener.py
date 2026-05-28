from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
import threading

from loguru import logger

from iris.io.models import CommandInput, Message, SystemMessage
from iris.io.session.manager import SessionManager
from iris.io.transport.grpc_server import GrpcServer


class GrpcListener:
    """GrpcListener。同期スレッド上でgRPCサーバーを管理する。"""

    def __init__(
        self,
        session_manager: SessionManager,
        on_message: Callable[[Message], None] | None = None,
        on_command: Callable[[CommandInput], None] | None = None,
        on_system_message: Callable[[SystemMessage, str, str], None] | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._on_message = on_message
        self._on_command = on_command
        self._on_system_message = on_system_message
        self._server_impl: GrpcServer | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def set_on_message(self, on_message: Callable[[Message], None]) -> None:
        self._on_message = on_message
        if self._server_impl:
            self._server_impl.set_on_message(on_message)

    def set_on_command(self, on_command: Callable[[CommandInput], None]) -> None:
        self._on_command = on_command
        if self._server_impl:
            self._server_impl.set_on_command(on_command)

    def set_on_system_message(self, on_system_message: Callable[[SystemMessage, str, str], None]) -> None:
        self._on_system_message = on_system_message
        if self._server_impl:
            self._server_impl.set_on_system_message(on_system_message)

    def start(self, host: str, port: int) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_server, args=(host, port), daemon=True, name="grpc-listener")
        self._thread.start()

    def stop(self) -> None:
        loop = self._loop
        server = self._server_impl
        if loop is not None and server is not None:

            async def _cleanup() -> None:
                try:
                    await server.stop()
                except Exception:
                    logger.exception("Error stopping gRPC server")
                finally:
                    tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task() and not t.done()]
                    for t in tasks:
                        t.cancel()
                    if tasks:
                        await asyncio.wait(tasks, timeout=2.0)
                    loop.stop()

            if loop.is_running():
                asyncio.run_coroutine_threadsafe(_cleanup(), loop)
            else:
                loop.stop()

        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

        if loop is not None:
            with contextlib.suppress(Exception):
                loop.close()
            self._loop = None
        logger.info("GrpcListener stopped")

    def _run_server(self, host: str, port: int) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._server_impl = GrpcServer(
            self._session_manager,
            on_message=self._on_message,
            on_command=self._on_command,
            on_system_message=self._on_system_message,
        )
        try:
            self._loop.run_until_complete(self._server_impl.start(host, port))
            self._loop.run_forever()
        except Exception:
            logger.exception("GrpcListener server thread encountered an error")
