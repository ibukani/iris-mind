from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from iris.kernel.plugin import PluginCategory, PluginManifest, PluginPhase, PluginProtocol

from .orchestrator import LimbicOrchestrator

if TYPE_CHECKING:
    from iris.account.manager import AccountManager
    from iris.kernel.manager import PluginManager
    from iris.room.manager import RoomManager

MANIFEST = PluginManifest(
    name="limbic",
    version="0.1.0",
    category=PluginCategory.LAYER,
    phase=PluginPhase.LAYER,
    dependencies={"EventBus", "AccountManager", "RoomManager"},
    provides=["LimbicOrchestrator"],
    description="Appraisal理論ベースの感情・関係性システム (Limbic system)",
)


class LimbicPlugin(PluginProtocol):
    MANIFEST = MANIFEST

    def init(self, manager: PluginManager) -> None:
        manager.register_manifest(MANIFEST)

        account_mgr: AccountManager | None = None
        room_mgr: RoomManager | None = None
        with contextlib.suppress(Exception):
            account_mgr = manager.resolve(AccountManager)
        with contextlib.suppress(Exception):
            room_mgr = manager.resolve(RoomManager)

        self._account_manager = account_mgr
        self._room_manager = room_mgr
        self._orchestrator = LimbicOrchestrator(
            account_manager=account_mgr,
            room_manager=room_mgr,
        )
        manager.provide(LimbicOrchestrator, self._orchestrator)

    def start(self, manager: PluginManager) -> None:
        from .hooks import subscribe_events

        subscribe_events(
            manager,
            self._orchestrator,
            account_manager=self._account_manager,
            room_manager=self._room_manager,
        )

    def stop(self, manager: PluginManager) -> None:
        pass

    def get_state(self) -> dict:
        return self._orchestrator.get_state()


plugin = LimbicPlugin()

__all__ = ["LimbicOrchestrator"]
