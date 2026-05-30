from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager


def register_hooks(manager: PluginManager) -> None:
    """Account Plugin のフック登録。"""
    hooks = manager.hook_registry

    from iris.account.handler import _AccountEventHandler

    handler = manager.resolve(_AccountEventHandler)

    def _on_dispatch(ctx: dict[str, Any]) -> dict[str, Any]:
        msg = ctx["msg"]
        if ctx["type"] == "control" and msg.action.startswith("account."):
            ctx["response"] = handler.handle_control_message(msg, ctx["session_id"])
        return ctx

    hooks.register("io.dispatch", _on_dispatch, priority=100)
