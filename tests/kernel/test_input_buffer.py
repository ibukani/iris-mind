from __future__ import annotations

import time

import pytest

from iris.memory.models import blocks_text
from iris.memory.sensory.manager import SensoryMemoryManager


@pytest.fixture
def buffer() -> SensoryMemoryManager:
    return SensoryMemoryManager(timeout_ms=100, max_fragments=10)


def test_add_fragment_accumulates(buffer: SensoryMemoryManager) -> None:
    buffer.add_fragment("hello ", is_final=False)
    buffer.add_fragment("world", is_final=True)
    assert buffer.accumulated_blocks == []
    assert buffer.fragment_count == 0


def test_add_fragment_no_flush_until_final(buffer: SensoryMemoryManager) -> None:
    buffer.add_fragment("hello ", is_final=False)
    assert buffer.fragment_count == 1
    assert blocks_text(buffer.accumulated_blocks) == "hello "


def test_flush_via_is_final() -> None:
    results: list[str] = []
    buf = SensoryMemoryManager(timeout_ms=1000)
    buf.set_flush_callback(lambda sid, blocks: results.append(blocks_text(blocks)))
    buf.add_fragment("hello ", is_final=False)
    buf.add_fragment("world", is_final=True)
    assert results == ["hello world"]


def test_flush_via_timeout() -> None:
    results: list[str] = []
    buf = SensoryMemoryManager(timeout_ms=50, max_fragments=10)
    buf.set_flush_callback(lambda sid, blocks: results.append(blocks_text(blocks)))
    buf.add_fragment("hello", is_final=False)
    time.sleep(0.15)
    assert results == ["hello"]


def test_flush_via_max_fragments() -> None:
    results: list[str] = []
    buf = SensoryMemoryManager(timeout_ms=1000, max_fragments=3)
    buf.set_flush_callback(lambda sid, blocks: results.append(blocks_text(blocks)))
    buf.add_fragment("a", is_final=False)
    buf.add_fragment("b", is_final=False)
    buf.add_fragment("c", is_final=False)
    assert results == ["abc"]


def test_explicit_flush() -> None:
    results: list[str] = []
    buf = SensoryMemoryManager(timeout_ms=1000)
    buf.set_flush_callback(lambda sid, blocks: results.append(blocks_text(blocks)))
    buf.add_fragment("hello", is_final=False)
    buf.flush()
    assert results == ["hello"]


def test_cancel_clears_and_stops_timer(buffer: SensoryMemoryManager) -> None:
    buffer.add_fragment("hello", is_final=False)
    buffer.cancel()
    assert buffer.fragment_count == 0
    assert buffer.accumulated_blocks == []


def test_close_prevents_further_additions(buffer: SensoryMemoryManager) -> None:
    buffer.close()
    buffer.add_fragment("hello", is_final=True)
    assert buffer.fragment_count == 0


def test_flush_empty_does_not_callback() -> None:
    results: list[str] = []
    buf = SensoryMemoryManager(timeout_ms=1000)
    buf.set_flush_callback(lambda sid, blocks: results.append(blocks_text(blocks)))
    buf.flush()
    assert results == []


def test_callback_receives_session_id() -> None:
    results: list[tuple[str, str]] = []
    buf = SensoryMemoryManager(timeout_ms=1000)
    buf.set_flush_callback(lambda sid, blocks: results.append((sid, blocks_text(blocks))))
    buf.add_fragment("data", is_final=True)
    assert results == [("", "data")]


def test_add_fragment_after_close(buffer: SensoryMemoryManager) -> None:
    buffer.add_fragment("before", is_final=False)
    buffer.close()
    buffer.add_fragment("after", is_final=True)
    assert buffer.accumulated_blocks == []


def test_reuse_after_flush() -> None:
    results: list[str] = []
    buf = SensoryMemoryManager(timeout_ms=1000)
    buf.set_flush_callback(lambda sid, blocks: results.append(blocks_text(blocks)))
    buf.add_fragment("first", is_final=True)
    buf.add_fragment("second", is_final=True)
    assert results == ["first", "second"]
