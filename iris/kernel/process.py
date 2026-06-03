from __future__ import annotations

from typing import Protocol

from loguru import logger

from .config import Config
from .factory import KernelComponents, _KernelComponentsInternal, build_kernel, start_kernel_io


class KernelProcessProtocol(Protocol):
    def start(self) -> None: ...
    def shutdown(self) -> None: ...
    @property
    def cmd_handler(self) -> object | None: ...
    @property
    def shutdown_requested(self) -> bool: ...


class KernelProcess:
    """Kernel の起動・停止を担う。

    内部で `build_kernel` を呼び、`KernelComponents` を保持する。
    `start()` 後に `cmd_handler` / `diagnostics` などの component にアクセスできる。
    """

    def __init__(self, config: Config, debug: bool = False) -> None:
        self._config = config
        self._debug = debug
        self._components: KernelComponents | None = None

    # ── Accessors ──

    @property
    def shutdown_requested(self) -> bool:
        if self._components is None:
            return False
        return self._components.manager.shutdown_requested

    @property
    def cmd_handler(self) -> object | None:
        return self._components.cmd_handler if self._components is not None else None

    @property
    def diagnostics(self) -> object | None:
        return self._components.diagnostics if self._components is not None else None

    @property
    def config_host(self) -> str:
        return self._config.session.host

    @property
    def config_port(self) -> int:
        return self._config.session.port

    # ── Lifecycle ──

    def start(self) -> None:
        logger.info("KernelProcess: starting")
        try:
            self._components = build_kernel(self._config, debug=self._debug)
            start_kernel_io(self._components)
            self._components.manager.start_all()
        except Exception:
            logger.exception("KernelProcess: start failed, cleaning up")
            self._cleanup()
            raise
        logger.info("KernelProcess: started")

    def attach_components(self, components: _KernelComponentsInternal) -> None:
        """テストや差し込み用に components を直接設定する。"""
        self._components = KernelComponents(
            manager=components.manager,
            diagnostics=components.diagnostics,
            cmd_handler=components.cmd_handler,
            process=self,
            shutdown_fn=lambda: None,
        )

    def _cleanup(self) -> None:
        components = self._components
        if components is None:
            return
        try:
            components.manager.stop_all()
        except Exception:
            logger.exception("KernelProcess: cleanup error")
        self._components = None

    def shutdown(self) -> None:
        logger.info("KernelProcess: shutting down")
        components = self._components
        if components is None:
            logger.info("KernelProcess: shutdown complete (was not started)")
            return

        components.manager.request_shutdown()
        from iris.agency.manager import AgencyManager

        agency = components.manager.resolve_optional(AgencyManager)
        if agency is not None:
            agency.shutdown()
        self._cleanup()
        logger.info("KernelProcess: shutdown complete")


__all__ = ["KernelProcess", "KernelProcessProtocol"]
