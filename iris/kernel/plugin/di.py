from __future__ import annotations

from typing import Any


class ServiceContainer:
    def __init__(self) -> None:
        self._services: dict[str, Any] = {}
        self._frozen = False

    def provide(self, name: str, instance: Any) -> None:
        if self._frozen:
            raise RuntimeError(f"ServiceContainer is frozen, cannot provide '{name}'")
        self._services[name] = instance

    def resolve(self, name: str) -> Any:
        if name not in self._services:
            raise KeyError(f"Service '{name}' not found. Available: {list(self._services.keys())}")
        return self._services[name]

    def resolve_optional(self, name: str) -> Any:
        return self._services.get(name)

    def freeze(self) -> None:
        self._frozen = True

    @property
    def frozen(self) -> bool:
        return self._frozen
