from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from loguru import logger


def hook(hook_name: str, priority: int = 500) -> Callable[[Callable], Callable]:
    """プラグインのメソッドをHookに自動登録するデコレータ。

    使用例:
        class MyPlugin:
            @hook("llm.before_chat", priority=100)
            def _on_before_chat(self, messages: list) -> list:
                return messages

    PluginLifecycle が init 時にこのデコレータを検出し、
    HookRegistry に自動登録する。
    """

    def decorator(fn: Callable) -> Callable:
        fn._hook_metadata = (hook_name, priority)  # type: ignore[attr-defined]
        return fn

    return decorator


class HookRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, list[tuple[int, Callable]]] = defaultdict(list)
        self._frozen = False

    def register(self, hook_name: str, handler: Callable, priority: int = 500) -> None:
        if self._frozen:
            raise RuntimeError(f"HookRegistry is frozen, cannot register '{hook_name}'")
        self._handlers[hook_name].append((priority, handler))
        self._handlers[hook_name].sort(key=lambda x: x[0])

    def register_decorated(self, instance: Any) -> None:
        """@hook デコレータが付いたメソッドを自動登録する。

        Plugin の init() で manager.hook_registry.register_decorated(self) を呼ぶと、
        @hook デコレータ付きメソッドが全て登録される。
        """
        for attr_name in dir(instance):
            attr = getattr(instance, attr_name, None)
            if attr is None or not callable(attr):
                continue
            metadata = getattr(attr, "_hook_metadata", None)
            if metadata is not None:
                hook_name, priority = metadata
                self.register(hook_name, attr, priority)

    def freeze(self) -> None:
        self._frozen = True

    async def execute(self, hook_name: str, data: Any, **ctx: Any) -> Any:
        handlers = self._handlers.get(hook_name, ())
        for _priority, handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    data = await handler(data, **ctx)
                else:
                    data = handler(data, **ctx)
            except Exception:
                logger.exception("Hook '{}' handler failed: {}", hook_name, handler)
                continue
        return data

    def execute_sync(self, hook_name: str, data: Any, **ctx: Any) -> Any:
        handlers = self._handlers.get(hook_name, ())
        for _priority, handler in handlers:
            try:
                data = handler(data, **ctx)
            except Exception:
                logger.exception("Hook '{}' handler failed: {}", hook_name, handler)
                continue
        return data
