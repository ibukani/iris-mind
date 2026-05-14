from __future__ import annotations

from datetime import datetime

from iris.kernel.event import (
    AgentAnomalyEvent,
    AgentResponseEvent,
    AgentStreamEvent,
    ProactiveSpeechEvent,
)


def test_renderer_proactive_speech_does_not_crash() -> None:
    from debug_tools.cli.renderer import Renderer

    r = Renderer()
    event = ProactiveSpeechEvent(
        timestamp=datetime(2026, 1, 1), source="proactive", content="hello", trigger_type="time", confidence=0.9
    )
    r.handle(event)


def test_renderer_stream_token_does_not_crash() -> None:
    from debug_tools.cli.renderer import Renderer

    r = Renderer()
    r.handle(AgentStreamEvent(timestamp=datetime(2026, 1, 1), source="assistant", delta=""))
    r.handle(AgentStreamEvent(timestamp=datetime(2026, 1, 1), source="assistant", delta="Hello "))
    r.handle(AgentStreamEvent(timestamp=datetime(2026, 1, 1), source="assistant", delta="world"))
    r.handle(AgentStreamEvent(timestamp=datetime(2026, 1, 1), source="assistant", delta="", done=True))


def test_renderer_response_does_not_crash() -> None:
    from debug_tools.cli.renderer import Renderer

    r = Renderer()
    event = AgentResponseEvent(timestamp=datetime(2026, 1, 1), source="assistant", content="Hello world")
    r.handle(event)


def test_renderer_anomaly_does_not_crash() -> None:
    from debug_tools.cli.renderer import Renderer

    r = Renderer()
    event = AgentAnomalyEvent(
        timestamp=datetime(2026, 1, 1), source="system", anomaly_type="test", severity="info", detail="test anomaly"
    )
    r.handle(event)


def test_renderer_is_streaming_flag() -> None:
    from debug_tools.cli.renderer import Renderer

    r = Renderer()
    assert not r.is_streaming

    r.handle(AgentStreamEvent(timestamp=datetime(2026, 1, 1), source="assistant", delta=""))
    assert r.is_streaming

    r.handle(AgentStreamEvent(timestamp=datetime(2026, 1, 1), source="assistant", delta="", done=True))
    assert not r.is_streaming
