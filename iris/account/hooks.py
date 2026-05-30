from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager


def register_hooks(manager: PluginManager) -> None:
    hooks = manager.hook_registry

    from iris.account.dispatcher import _AccountDispatcher

    dispatcher = manager.resolve(_AccountDispatcher)

    def _on_dispatch(ctx: dict[str, Any]) -> dict[str, Any]:
        msg = ctx["msg"]
        if ctx["type"] == "control" and msg.action.startswith("account."):
            ctx["response"] = dispatcher.handle_control_message(msg, ctx["session_id"])
        return ctx

    hooks.register("io.dispatch", _on_dispatch, priority=100)
