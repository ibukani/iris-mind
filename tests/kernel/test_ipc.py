from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from datetime import datetime

from iris.kernel.event import Event, TimerTick, UserInputEvent, new_trace_id
from iris.kernel.ipc import ReplayableTransport


@dataclass
class FakeTransport:
    sent: list[Event]
    to_recv: list[Event]

    @classmethod
    def receiver(cls, events: list[Event]) -> FakeTransport:
        return cls(sent=[], to_recv=list(events))

    @classmethod
    def sender(cls) -> FakeTransport:
        return cls(sent=[], to_recv=[])

    def send(self, event: Event) -> None:
        self.sent.append(event)

    def recv(self) -> Event:
        return self.to_recv.pop(0)


def test_replay_logs_sent_events() -> None:
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".jsonl", delete=False, encoding="utf-8") as tmp:
        logpath = tmp.name

    try:
        inner = FakeTransport.sender()
        replay = ReplayableTransport(inner, logpath)

        e1 = UserInputEvent(timestamp=datetime(2026, 1, 1), source="cli", content="hello", trace_id=new_trace_id())
        e2 = TimerTick(timestamp=datetime(2026, 1, 1), source="system", tick_count=1, trace_id=new_trace_id())
        replay.send(e1)
        replay.send(e2)

        assert inner.sent == [e1, e2]

        with open(logpath, encoding="utf-8") as f:
            lines = f.read().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["type"] == "UserInputEvent"
        assert json.loads(lines[1])["type"] == "TimerTick"
    finally:
        import os

        os.unlink(logpath)


def test_replay_logs_received_events() -> None:
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".jsonl", delete=False, encoding="utf-8") as tmp:
        logpath = tmp.name

    try:
        e1 = UserInputEvent(timestamp=datetime(2026, 1, 1), source="cli", content="ping", trace_id=new_trace_id())
        inner = FakeTransport.receiver([e1])
        replay = ReplayableTransport(inner, logpath)

        received = replay.recv()
        assert received == e1

        with open(logpath, encoding="utf-8") as f:
            lines = f.read().strip().split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0])["type"] == "UserInputEvent"
    finally:
        import os

        os.unlink(logpath)


def test_replay_preserves_order() -> None:
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".jsonl", delete=False, encoding="utf-8") as tmp:
        logpath = tmp.name

    try:
        from iris.kernel.event import UserInputEvent as UIEvent

        events: list[Event] = [
            UIEvent(timestamp=datetime(2026, 1, 1), source="cli", content=f"msg{i}", trace_id=new_trace_id())
            for i in range(5)
        ]
        inner = FakeTransport.receiver(events.copy())
        replay = ReplayableTransport(inner, logpath)

        for i in range(5):
            ev = replay.recv()
            assert isinstance(ev, UIEvent)
            assert ev.content == f"msg{i}"

        with open(logpath, encoding="utf-8") as f:
            lines = f.read().strip().split("\n")
        assert len(lines) == 5
        for i, line in enumerate(lines):
            assert json.loads(line)["content"] == f"msg{i}"
    finally:
        import os

        os.unlink(logpath)
