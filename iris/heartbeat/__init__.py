from __future__ import annotations

from typing import TYPE_CHECKING

from iris.event.event_bus import EventBus
from iris.kernel.plugin import PluginCategory, PluginManifest, PluginPhase, PluginProtocol

from .service import TimerService

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager

MANIFEST = PluginManifest(
    name="heartbeat",
    version="0.1.0",
    category=PluginCategory.CORE,
    phase=PluginPhase.CORE,
    dependencies={"EventBus"},
    provides=["TimerService"],
    description="定期的な鼓動(TimerTick)をEventBusに発行する",
)


class HeartbeatPlugin:
    MANIFEST = MANIFEST

    def init(self, manager: PluginManager) -> None:
        manager.register_manifest(MANIFEST)
        event_bus = manager.resolve(EventBus)
        interval = manager.config.timer.interval_sec
        self._service = TimerService(event_bus, interval)
        manager.provide(TimerService, self._service)

    def start(self, manager: PluginManager) -> None:
        self._service.start()

    def stop(self, manager: PluginManager) -> None:
        self._service.stop()


plugin: PluginProtocol = HeartbeatPlugin()

__all__ = ["TimerService"]
