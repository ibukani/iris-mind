from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager


def register_hooks(manager: PluginManager) -> None:
    hooks = manager.hook_registry

    def _before_send(msg: Any) -> Any:
        return msg

    def _after_receive(msg: Any) -> Any:
        return msg

    hooks.register("io.before_send", _before_send, priority=500)
    hooks.register("io.after_receive", _after_receive, priority=500)
