"""Kernel 全体で使う共有 Protocol 型定義。

`iris-plugin-structure` の方針に従い、Plugin 間の境界は具象クラスではなく
Protocol 経由で結合する。Protocol は具象に依存せず、`runtime_checkable` を
付けてテストでの `isinstance` 検証も可能にしている。

各 Protocol の責務:
- EventPublisherProtocol: イベントを発行する最小契約 (EventBus)
- EventSubscriberProtocol: イベントを購読する最小契約 (EventBus)
- HookRegistryProtocol: フックポイント管理 (HookRegistry)
- DisplayNameResolverProtocol: Account の表示名解決
- AccountResolverProtocol: Account / AccountIdentity の解決
- RoomResolverProtocol: Room / RoomMember の解決
- MemoryReaderProtocol: memory 検索の最小契約
- ProviderResolverProtocol: LLM provider の解決
- ToolRegistryProtocol: tool 検索・実行
- StateProviderProtocol: 状態スナップショット提供
- InterruptibleProtocol: 実行キャンセル
- ConfigProtocol: 設定値の読み取り
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from iris.event.base import Event


@runtime_checkable
class EventPublisherProtocol(Protocol):
    """イベントを発行する最小契約。`EventBus` が実装する。"""

    def publish(self, event: Event, *, strict: bool = False) -> None: ...


@runtime_checkable
class EventSubscriberProtocol(Protocol):
    """イベントを購読する最小契約。`EventBus` が実装する。"""

    def subscribe(
        self,
        event_type: type[Event] | str,
        handler: Callable[[Any], None],
    ) -> None: ...

    def unsubscribe(
        self,
        event_type: type[Event] | str,
        handler: Callable[[Any], None],
    ) -> None: ...


@runtime_checkable
class HookRegistryProtocol(Protocol):
    """Hook ポイントの登録・実行の最小契約。"""

    def register(self, hook_name: str, handler: Callable[..., Any], priority: int = 500) -> None: ...

    def execute_sync(self, hook_name: str, data: Any, **ctx: Any) -> Any: ...


@runtime_checkable
class DisplayNameResolverProtocol(Protocol):
    """Account ID から表示名を解決する最小契約。"""

    def resolve_display_name(self, account_id: str) -> str: ...


@runtime_checkable
class AccountResolverProtocol(Protocol):
    """Account / Identity を解決する最小契約。"""

    def resolve(self, account_id: str) -> Any | None: ...


@runtime_checkable
class RoomResolverProtocol(Protocol):
    """Room / RoomMember を解決する最小契約。"""

    def get_room(self, room_id: str) -> Any | None: ...

    def get_members(self, room_id: str) -> list[Any]: ...


@runtime_checkable
class MemoryReaderProtocol(Protocol):
    """memory 層の読み取り最小契約。検索系の薄い facade。"""

    def search(
        self,
        query: str,
        *,
        stream: str = "semantic",
        max_results: int = 5,
        room_id: str = "",
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class ProviderResolverProtocol(Protocol):
    """LLM provider の解決。"""

    def get_provider(self, model_name: str) -> Any: ...


@runtime_checkable
class ToolRegistryProtocol(Protocol):
    """Tool 登録の最小契約。"""

    def list_tools(self) -> list[dict[str, Any]]: ...

    def get(self, name: str) -> Any | None: ...


@runtime_checkable
class StateProviderProtocol(Protocol):
    """状態スナップショットを返す最小契約。"""

    def get_state(self) -> dict[str, Any]: ...


@runtime_checkable
class InterruptibleProtocol(Protocol):
    """実行中フローのキャンセル契約。"""

    def cancel_execution(self) -> None: ...


@runtime_checkable
class ConfigProtocol(Protocol):
    """設定値の読み取り最小契約。"""

    def get(self, key: str, default: Any = None) -> Any: ...


__all__ = [
    "AccountResolverProtocol",
    "ConfigProtocol",
    "DisplayNameResolverProtocol",
    "EventPublisherProtocol",
    "EventSubscriberProtocol",
    "HookRegistryProtocol",
    "InterruptibleProtocol",
    "MemoryReaderProtocol",
    "ProviderResolverProtocol",
    "RoomResolverProtocol",
    "StateProviderProtocol",
    "ToolRegistryProtocol",
]
