from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from loguru import logger


class HookRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, list[tuple[int, Callable]]] = defaultdict(list)
        self._frozen = False

    def register(self, hook_name: str, handler: Callable, priority: int = 500) -> None:
        if self._frozen:
            raise RuntimeError(f"HookRegistry is frozen, cannot register '{hook_name}'")
        self._handlers[hook_name].append((priority, handler))
        self._handlers[hook_name].sort(key=lambda x: x[0])

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
