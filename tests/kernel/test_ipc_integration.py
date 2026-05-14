"""IPC 実通信テスト — Named Pipe 経由のイベント送受信を実環境で検証する。"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime

import pytest

from iris.kernel.event import Event, UserInputEvent
from iris.kernel.ipc import PipeClient, PipeServer

pytestmark = pytest.mark.skipif(
    not os.environ.get("IRIS_RUN_IPC_TESTS"),
    reason="Set IRIS_RUN_IPC_TESTS=1 to run IPC integration tests",
)


def test_ipc_roundtrip() -> None:
    """PipeServer / PipeClient でイベントを送受信できることを確認する。"""
    pipe_name = r"\\.\pipe\iris-test-roundtrip"

    received: list[Event] = []

    def server_thread() -> None:
        server = PipeServer(pipe_name)
        conn = server.accept()
        event = conn.recv()
        received.append(event)
        conn.close()
        server.close()

    t = threading.Thread(target=server_thread, daemon=True)
    t.start()
    time.sleep(0.3)

    client = PipeClient(pipe_name)
    original = UserInputEvent(
        timestamp=datetime(2026, 1, 1),
        source="test",
        content="hello ipc",
        trace_id="test-trace",
    )
    client.send(original)
    client.close()

    t.join(timeout=5)

    assert len(received) == 1
    assert isinstance(received[0], UserInputEvent)
    assert received[0].content == "hello ipc"
    assert received[0].trace_id == "test-trace"


def test_ipc_connection_refused() -> None:
    """存在しない Pipe に接続すると ConnectionError になることを確認する。"""
    nonexistent = r"\\.\pipe\iris-nonexistent-test"
    with pytest.raises((ConnectionError, FileNotFoundError, OSError)):
        PipeClient(nonexistent)
