from __future__ import annotations

from typing import Any, cast


class ServiceContainer:
    def __init__(self) -> None:
        self._services: dict[type[Any], Any] = {}
        self._frozen = False

    def provide[T](self, key: type[T], instance: T) -> None:
        if self._frozen:
            raise RuntimeError(f"ServiceContainer is frozen, cannot provide '{key.__name__}'")
        self._services[key] = instance

    def resolve[T](self, key: type[T]) -> T:
        if key not in self._services:
            names = [k.__name__ for k in self._services]
            raise KeyError(f"Service '{key.__name__}' not found. Available: {names}")
        return cast(T, self._services[key])

    def resolve_optional[T](self, key: type[T]) -> T | None:
        return cast(T | None, self._services.get(key))

    def freeze(self) -> None:
        self._frozen = True

    @property
    def frozen(self) -> bool:
        return self._frozen
