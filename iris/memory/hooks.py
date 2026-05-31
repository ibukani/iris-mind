from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager


def _before_store(episode: Any) -> Any:
    return episode


def _after_search(hits: Any) -> Any:
    return hits


def register_hooks(manager: PluginManager) -> None:
    hooks = manager.hook_registry

    hooks.register("memory.before_store", _before_store, priority=500)
    hooks.register("memory.after_search", _after_search, priority=500)
