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
    provides=["AccountProvider", "AccountStore"],
    description="アカウント管理（ユーザー識別・外部ID連携・セッション紐付け）",
)


class AccountPlugin:
    MANIFEST = MANIFEST

    def init(self, manager: PluginManager) -> None:
        manager.register_manifest(MANIFEST)

        from iris.account.handler import _AccountEventHandler
        from iris.account.provider import AccountProvider
        from iris.account.store import AccountStore
        from iris.event.event_bus import EventBus

        cfg = manager.get_plugin_config("account")
        accounts_path = str(cfg.get("accounts_path", ".iris/data/accounts.jsonl"))
        bindings_path = str(cfg.get("bindings_path", ".iris/data/account_bindings.jsonl"))

        store = AccountStore(accounts_path=accounts_path, bindings_path=bindings_path)
        event_bus = manager.resolve(EventBus)
        provider = AccountProvider(store=store, event_bus=event_bus)

        handler = _AccountEventHandler(account_provider=provider)

        manager.provide(AccountStore, store)
        manager.provide(AccountProvider, provider)
        manager.provide(_AccountEventHandler, handler)

        from iris.account.hooks import register_hooks

        register_hooks(manager)

    def start(self, manager: PluginManager) -> None:
        pass

    def stop(self, manager: PluginManager) -> None:
        pass


plugin: PluginProtocol = AccountPlugin()
