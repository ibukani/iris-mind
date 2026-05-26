from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager


def register_hooks(manager: PluginManager) -> None:
    hooks = manager.hook_registry

    def _plan_decided(plan: Any) -> Any:
        return plan

    def _before_exec(state: Any) -> Any:
        return state

    hooks.register("agency.plan_decided", _plan_decided, priority=500)
    hooks.register("agency.before_exec", _before_exec, priority=500)
