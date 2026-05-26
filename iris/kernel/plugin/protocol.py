from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager


@runtime_checkable
class PluginProtocol(Protocol):
    def init(self, manager: PluginManager) -> None: ...

    def start(self, manager: PluginManager) -> None: ...

    def stop(self, manager: PluginManager) -> None: ...
