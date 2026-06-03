from __future__ import annotations

from typing import Any, cast


class ServiceContainer:
    """依存性注入コンテナ。型キーまたは名前付きキーでサービスを管理する。"""

    def __init__(self) -> None:
        self._services: dict[tuple[type[Any], str], Any] = {}
        self._frozen = False

    def provide[T](self, key: type[T], instance: T, *, name: str = "default") -> None:
        """サービスを登録する。

        Args:
            key: サービスの型。
            instance: サービスのインスタンス。
            name: 名前付き登録用の識別子（デフォルト: "default"）。
        """
        if self._frozen:
            raise RuntimeError(f"ServiceContainer is frozen, cannot provide '{key.__name__}'")
        self._services[(key, name)] = instance

    def resolve[T](self, key: type[T], *, name: str = "default") -> T:
        """サービスを解決する。

        Args:
            key: サービスの型。
            name: 名前付き登録用の識別子（デフォルト: "default"）。

        Raises:
            KeyError: サービスが見つからない場合。
        """
        service_key = (key, name)
        if service_key not in self._services:
            names = [f"{k[0].__name__}('{k[1]}')" for k in self._services]
            raise KeyError(f"Service '{key.__name__}' (name='{name}') not found. Available: {names}")
        return cast(T, self._services[service_key])

    def resolve_optional[T](self, key: type[T], *, name: str = "default") -> T | None:
        """サービスを解決する。見つからない場合は None を返す。"""
        return cast(T | None, self._services.get((key, name)))

    def has[T](self, key: type[T], *, name: str = "default") -> bool:
        """サービスが登録されているか確認する。"""
        return (key, name) in self._services

    def list_services(self) -> list[tuple[type[Any], str]]:
        """登録されている全サービスのキーを返す。"""
        return list(self._services.keys())

    def freeze(self) -> None:
        self._frozen = True

    @property
    def frozen(self) -> bool:
        return self._frozen
