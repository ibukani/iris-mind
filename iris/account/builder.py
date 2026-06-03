"""account Plugin のコンポーネント組み立て。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager


def build_account(manager: PluginManager) -> dict[str, object]:
    """Account Plugin の component を組み立てる。"""
    from iris.account.dispatcher import AccountDispatcher
    from iris.account.manager import AccountManager
    from iris.account.store import AccountStore
    from iris.event.event_bus import EventBus

    cfg = manager.get_plugin_config("account")
    accounts_path = str(cfg.get("accounts_path", ".iris/data/accounts.jsonl"))
    identities_path = str(cfg.get("identities_path", ".iris/data/account_identities.jsonl"))

    store = AccountStore(accounts_path=accounts_path, identities_path=identities_path)
    event_bus = manager.resolve(EventBus)
    account_manager = AccountManager(store=store, event_bus=event_bus)
    dispatcher = AccountDispatcher(account_manager=account_manager)
    return {
        "store": store,
        "event_bus": event_bus,
        "account_manager": account_manager,
        "dispatcher": dispatcher,
    }


__all__ = ["build_account"]
