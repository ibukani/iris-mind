from __future__ import annotations

from typing import TYPE_CHECKING

from iris.account.models import ProfileUpdate, Provider, ResolvedIdentity, parse_identity
from iris.kernel.plugin import PluginCategory, PluginManifest, PluginPhase, PluginProtocol

from .builder import build_account

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager

__all__ = [
    "MANIFEST",
    "AccountPlugin",
    "ProfileUpdate",
    "Provider",
    "ResolvedIdentity",
    "parse_identity",
]

MANIFEST = PluginManifest(
    name="account",
    version="0.1.0",
    category=PluginCategory.LAYER,
    phase=PluginPhase.STORE,
    dependencies={"EventBus"},
    provides=["AccountManager", "AccountStore", "AccountDispatcher"],
    description="アカウント管理（ユーザー識別・外部ID連携）",
)


class AccountPlugin(PluginProtocol):
    MANIFEST = MANIFEST

    def init(self, manager: PluginManager) -> None:
        manager.register_manifest(MANIFEST)
        components = build_account(manager)

        from iris.account.dispatcher import AccountDispatcher
        from iris.account.manager import AccountManager
        from iris.account.store import AccountStore

        manager.provide(AccountStore, components["store"])
        manager.provide(AccountManager, components["account_manager"])
        manager.provide(AccountDispatcher, components["dispatcher"])

    def start(self, manager: PluginManager) -> None:
        pass

    def stop(self, manager: PluginManager) -> None:
        pass


plugin: PluginProtocol = AccountPlugin()
