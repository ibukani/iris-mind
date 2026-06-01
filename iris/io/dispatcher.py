"""IO層のメッセージディスパッチャ。

`io.dispatch` フックポイントに代わる、IO受信メッセージの振り分け。
ControlMessage (room.* / account.*) と CommandInput (/...) のルーティングを
優先度順に試行する。優先度が高い dispatcher から順に呼び、最初に None 以外を
返したものを採用する。

優先度 (高い方が先):
- account: 100 (account.* action のみマッチ)
- room: 200 (room.* action のみマッチ)
- command: 50 (CommandInput 用)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iris.account.dispatcher import AccountDispatcher
    from iris.room.dispatcher import _RoomDispatcher


@dataclass
class _ControlHandler:
    priority: int
    matcher: Callable[[Any], bool]
    handler: Callable[[Any, str], Any]


@dataclass
class _CommandHandler:
    priority: int
    handler: Callable[[str, str, str], str | None]


class DispatcherRegistry:
    """IO層のディスパッチャ登録。優先度順に試行する。"""

    def __init__(self) -> None:
        self._control_handlers: list[_ControlHandler] = []
        self._command_handlers: list[_CommandHandler] = []

    def register_control(
        self,
        priority: int,
        matcher: Callable[[Any], bool],
        handler: Callable[[Any, str], Any],
    ) -> None:
        self._control_handlers.append(_ControlHandler(priority=priority, matcher=matcher, handler=handler))
        self._control_handlers.sort(key=lambda x: x.priority, reverse=True)

    def register_command(
        self,
        priority: int,
        handler: Callable[[str, str, str], str | None],
    ) -> None:
        self._command_handlers.append(_CommandHandler(priority=priority, handler=handler))
        self._command_handlers.sort(key=lambda x: x.priority, reverse=True)

    def dispatch_control(self, ctx: dict[str, Any]) -> dict[str, Any]:
        msg = ctx["msg"]
        session_id = ctx.get("session_id", "")
        for entry in self._control_handlers:
            if entry.matcher(msg):
                response = entry.handler(msg, session_id)
                if response is not None:
                    ctx["response"] = response
                    return ctx
        return ctx

    def dispatch_command(self, ctx: dict[str, Any]) -> dict[str, Any]:
        name = ctx.get("name", "")
        args = ctx.get("args", "")
        session_id = ctx.get("session_id", "")
        for entry in self._command_handlers:
            response = entry.handler(name, args, session_id)
            if response is not None:
                ctx["response"] = response
                return ctx
        return ctx


def build_default_registry(
    account_dispatcher: AccountDispatcher | None = None,
    room_dispatcher: _RoomDispatcher | None = None,
    command_handler: Callable[[str, str, str], str | None] | None = None,
) -> DispatcherRegistry:
    """標準の dispatcher 登録を構築する。"""
    reg = DispatcherRegistry()
    if account_dispatcher is not None:

        def _account_match(msg: Any) -> bool:
            return str(getattr(msg, "action", "")).startswith("account.")

        reg.register_control(
            100,
            _account_match,
            lambda m, s: account_dispatcher.handle_control_message(m),
        )
    if room_dispatcher is not None:

        def _room_match(msg: Any) -> bool:
            return str(getattr(msg, "action", "")).startswith("room.")

        reg.register_control(200, _room_match, lambda m, s: room_dispatcher.handle_control_message(m, s))
    if command_handler is not None:
        reg.register_command(50, command_handler)
    return reg


__all__ = [
    "DispatcherRegistry",
    "build_default_registry",
]
