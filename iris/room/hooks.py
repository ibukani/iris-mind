from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager


def register_hooks(manager: PluginManager) -> None:
    hooks = manager.hook_registry

    from iris.room.dispatcher import _RoomDispatcher

    dispatcher = manager.resolve(_RoomDispatcher)

    def _on_dispatch(ctx: dict[str, Any]) -> dict[str, Any]:
        msg = ctx["msg"]
        if ctx["type"] == "control" and msg.action.startswith("room."):
            ctx["response"] = dispatcher.handle_control_message(msg, ctx["session_id"])
        return ctx

    hooks.register("io.dispatch", _on_dispatch, priority=200)
