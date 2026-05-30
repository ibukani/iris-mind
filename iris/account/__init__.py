from __future__ import annotations

from typing import TYPE_CHECKING, Any

from iris.kernel.plugin import PluginCategory, PluginManifest, PluginPhase, PluginProtocol
from iris.kernel.plugin.hooks import hook

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager

MANIFEST = PluginManifest(
    name="account",
    version="0.1.0",
    category=PluginCategory.LAYER,
    phase=PluginPhase.STORE,
    dependencies={"EventBus"},
    provides=["AccountProvider", "AccountStore", "_AccountEventHandler"],
    description="アカウント管理（ユーザー識別・外部ID連携）",
)


class AccountPlugin(PluginProtocol):
    MANIFEST = MANIFEST

    def init(self, manager: PluginManager) -> None:
        manager.register_manifest(MANIFEST)

        from iris.account.handler import _AccountEventHandler
        from iris.account.provider import AccountProvider
        from iris.account.store import AccountStore
        from iris.event.event_bus import EventBus

        cfg = manager.get_plugin_config("account")
        accounts_path = str(cfg.get("accounts_path", ".iris/data/accounts.jsonl"))
        identities_path = str(cfg.get("identities_path", ".iris/data/account_identities.jsonl"))

        store = AccountStore(accounts_path=accounts_path, identities_path=identities_path)
        event_bus = manager.resolve(EventBus)
        provider = AccountProvider(store=store, event_bus=event_bus)

        self._handler = _AccountEventHandler(account_provider=provider)

        manager.provide(AccountStore, store)
        manager.provide(AccountProvider, provider)
        manager.provide(_AccountEventHandler, self._handler)

        manager.hook_registry.register_decorated(self)

        from iris.account.hooks import register_hooks

        register_hooks(manager)

    @hook("io.dispatch", priority=100)
    def _on_dispatch(self, ctx: dict[str, Any]) -> dict[str, Any]:
        msg = ctx["msg"]
        if ctx["type"] == "control" and msg.action.startswith("account."):
            ctx["response"] = self._handler.handle_control_message(msg, ctx["session_id"])
        return ctx

    def start(self, manager: PluginManager) -> None:
        pass

    def stop(self, manager: PluginManager) -> None:
        pass


plugin: PluginProtocol = AccountPlugin()
