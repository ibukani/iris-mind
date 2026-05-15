from __future__ import annotations

from iris.kernel.io.models import OutputMessage


def test_renderer_stream_chunks_and_is_streaming() -> None:
    from adapters.cli.renderer import Renderer

    r = Renderer()
    assert not r.is_streaming

    r.handle(OutputMessage(msg_type="stream", content="", metadata={"done": False}))
    assert r.is_streaming

    r.handle(OutputMessage(msg_type="stream", content="Hello ", metadata={"done": False}))
    assert r.is_streaming

    r.handle(OutputMessage(msg_type="stream", content="world", metadata={"done": False}))
    assert r.is_streaming

    r.handle(OutputMessage(msg_type="stream", content="", metadata={"done": True}))
    assert not r.is_streaming


def test_renderer_response_does_not_crash() -> None:
    from adapters.cli.renderer import Renderer

    r = Renderer()
    msg = OutputMessage(msg_type="response", content="Hello world")
    r.handle(msg)


def test_renderer_proactive_does_not_crash() -> None:
    from adapters.cli.renderer import Renderer

    r = Renderer()
    msg = OutputMessage(msg_type="proactive", content="Hey, how are you?")
    r.handle(msg)


def test_renderer_command_does_not_crash() -> None:
    from adapters.cli.renderer import Renderer

    r = Renderer()
    msg = OutputMessage(msg_type="command", content="/help")
    r.handle(msg)


def test_renderer_error_warning_severity() -> None:
    from adapters.cli.renderer import Renderer

    r = Renderer()
    msg = OutputMessage(msg_type="error", content="Something went wrong", metadata={"severity": "warning"})
    r.handle(msg)


def test_renderer_error_info_severity() -> None:
    from adapters.cli.renderer import Renderer

    r = Renderer()
    msg = OutputMessage(msg_type="error", content="FYI: rate limited", metadata={"severity": "info"})
    r.handle(msg)
