from __future__ import annotations

from typing import TYPE_CHECKING

from iris.kernel.plugin import PluginCategory, PluginManifest, PluginPhase

from .orchestrator import LimbicOrchestrator

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager

MANIFEST = PluginManifest(
    name="limbic",
    version="0.1.0",
    category=PluginCategory.LAYER,
    phase=PluginPhase.LAYER,
    dependencies={"EventBus"},
    provides=["LimbicOrchestrator"],
    description="Appraisal理論ベースの感情・関係性システム (Limbic system)",
)


class LimbicPlugin:
    MANIFEST = MANIFEST

    def init(self, manager: PluginManager) -> None:
        manager.register_manifest(MANIFEST)
        self._orchestrator = LimbicOrchestrator()
        manager.provide(LimbicOrchestrator, self._orchestrator)

    def start(self, manager: PluginManager) -> None:
        from .hooks import subscribe_events

        subscribe_events(manager, self._orchestrator)

    def stop(self, manager: PluginManager) -> None:
        pass

    def get_state(self) -> dict:
        return self._orchestrator.get_state()


plugin = LimbicPlugin()

__all__ = ["LimbicOrchestrator"]
