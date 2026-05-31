from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager


def register_hooks(manager: PluginManager) -> None:
    hooks = manager.hook_registry

    def _before_chat(messages: Any) -> Any:
        return messages

    def _after_chat(response: Any) -> Any:
        return response

    def _before_stream(chunk: Any) -> Any:
        return chunk

    hooks.register("llm.before_chat", _before_chat, priority=500)
    hooks.register("llm.after_chat", _after_chat, priority=500)
    hooks.register("llm.before_stream", _before_stream, priority=500)
