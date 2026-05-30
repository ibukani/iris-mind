from __future__ import annotations

from typing import TYPE_CHECKING

from iris.kernel.plugin import PluginCategory, PluginManifest, PluginPhase, PluginProtocol

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager

MANIFEST = PluginManifest(
    name="account",
    version="0.1.0",
    category=PluginCategory.LAYER,
    phase=PluginPhase.STORE,
    dependencies={"EventBus"},
    provides=["AccountManager", "AccountStore", "_AccountDispatcher"],
    description="アカウント管理（ユーザー識別・外部ID連携）",
)


class AccountPlugin(PluginProtocol):
    MANIFEST = MANIFEST

    def init(self, manager: PluginManager) -> None:
        manager.register_manifest(MANIFEST)

        from iris.account.dispatcher import _AccountDispatcher
        from iris.account.manager import AccountManager
        from iris.account.store import AccountStore
        from iris.event.event_bus import EventBus

        cfg = manager.get_plugin_config("account")
        accounts_path = str(cfg.get("accounts_path", ".iris/data/accounts.jsonl"))
        identities_path = str(cfg.get("identities_path", ".iris/data/account_identities.jsonl"))

        store = AccountStore(accounts_path=accounts_path, identities_path=identities_path)
        event_bus = manager.resolve(EventBus)
        manager_inst = AccountManager(store=store, event_bus=event_bus)

        dispatcher = _AccountDispatcher(account_manager=manager_inst)

        manager.provide(AccountStore, store)
        manager.provide(AccountManager, manager_inst)
        manager.provide(_AccountDispatcher, dispatcher)

        from iris.account.hooks import register_hooks

        register_hooks(manager)

    def start(self, manager: PluginManager) -> None:
        pass

    def stop(self, manager: PluginManager) -> None:
        pass


plugin: PluginProtocol = AccountPlugin()
