from __future__ import annotations

from datetime import datetime
from typing import Any

from iris.kernel.event import AgentResponseEvent, UserInputEvent


class _FakeConversationService:
    def __init__(self) -> None:
        self.last_input: str = ""

    def process_input(self, content: str) -> None:
        self.last_input = content


class _FakeCmdHandler:
    def __init__(self) -> None:
        self.last_command: str = ""

    def handle(self, text: str) -> str:
        self.last_command = text
        return f"Handled: {text}"


class _FakeProactive:
    def __init__(self) -> None:
        self.activity_count: int = 0

    def notify_user_activity(self) -> None:
        self.activity_count += 1


class _FakeEventBus:
    def __init__(self) -> None:
        self.subs: dict[str, Any] = {}
        self.published: list[Any] = []

    def subscribe(self, event_type: str, handler: Any) -> None:
        self.subs[event_type] = handler

    def publish(self, event: Any) -> None:
        self.published.append(event)

    def unsubscribe(self, event_type: str, handler: Any) -> None:
        pass


def _make_router() -> tuple[Any, Any, Any, Any, Any]:
    from iris.kernel.ipc import CommandRouter

    cmd = _FakeCmdHandler()
    pro = _FakeProactive()
    bus = _FakeEventBus()
    conv = _FakeConversationService()
    router = CommandRouter(cmd_handler=cmd, proactive=pro, event_bus=bus, conversation=conv)
    return router, cmd, pro, bus, conv


def test_command_router_handles_slash_commands() -> None:
    router, cmd, pro, bus, conv = _make_router()

    bus.subs["UserInputEvent"](UserInputEvent(timestamp=datetime(2026, 1, 1), source="test", content="/help"))

    assert cmd.last_command == "/help"
    assert pro.activity_count == 1
    assert len(bus.published) == 1
    assert isinstance(bus.published[0], AgentResponseEvent)
    assert "Handled: /help" in bus.published[0].content
    assert conv.last_input == ""  # コマンドは会話サービスに渡らない


def test_command_router_forwards_normal_input() -> None:
    router, cmd, pro, bus, conv = _make_router()

    bus.subs["UserInputEvent"](UserInputEvent(timestamp=datetime(2026, 1, 1), source="test", content="hello"))

    assert cmd.last_command == ""
    assert pro.activity_count == 0
    assert len(bus.published) == 0
    assert conv.last_input == "hello"


def test_command_router_empty_response_does_not_publish() -> None:
    from iris.kernel.ipc import CommandRouter

    class NoopHandler:
        def handle(self, text: str) -> str:  # noqa: ARG002
            return ""

    bus = _FakeEventBus()
    pro = _FakeProactive()
    conv = _FakeConversationService()
    CommandRouter(cmd_handler=NoopHandler(), proactive=pro, event_bus=bus, conversation=conv)

    bus.subs["UserInputEvent"](UserInputEvent(timestamp=datetime(2026, 1, 1), source="test", content="/sleep"))

    assert len(bus.published) == 0
