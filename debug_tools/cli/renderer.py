from __future__ import annotations

import time as _time
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from iris.kernel.event import (
    AgentAnomalyEvent,
    AgentResponseEvent,
    AgentStreamEvent,
    ProactiveSpeechEvent,
)

console = Console()


class Renderer:
    def __init__(self) -> None:
        self._stream_live: Live | None = None
        self._stream_text: str = ""

    def handle(self, event: Any) -> None:
        if isinstance(event, ProactiveSpeechEvent):
            self.on_proactive_speech(event)
        elif isinstance(event, AgentStreamEvent):
            self.on_stream_token(event)
        elif isinstance(event, AgentResponseEvent):
            self.on_agent_response(event)
        elif isinstance(event, AgentAnomalyEvent):
            self.on_anomaly(event)

    def on_proactive_speech(self, event: ProactiveSpeechEvent) -> None:
        tier_label = "auto" if event.confidence >= 1.0 else "self-judge"
        console.print(
            Panel(
                f"[italic]{event.content}[/italic]\n"
                f"[dim]trigger={event.trigger_type} "
                f"confidence={event.confidence:.2f} "
                f"({tier_label})[/dim]",
                title="[bold yellow]Iris[/bold yellow]",
                border_style="yellow",
                padding=(0, 1),
                width=60,
            )
        )

    def on_stream_token(self, event: AgentStreamEvent) -> None:
        if event.done:
            self._finalize_stream()
            return
        if self._stream_live is None:
            self._stream_live = Live(console=console, refresh_per_second=12, vertical_overflow="visible")
            self._stream_live.__enter__()
        if event.delta:
            self._stream_text += event.delta
            self._stream_live.update(
                Panel(
                    self._stream_text,
                    title="[bold green]Iris[/bold green]",
                    border_style="green",
                    padding=(0, 1),
                    width=72,
                )
            )
        elif not self._stream_text:
            self._stream_live.update(Text("Thinking...", style="dim italic"))

    def on_agent_response(self, event: AgentResponseEvent) -> None:
        if self._stream_live is not None:
            return
        console.print(
            Panel(
                event.content,
                title="[bold green]Iris[/bold green]",
                border_style="green",
                padding=(0, 1),
                width=72,
            )
        )

    def on_anomaly(self, event: AgentAnomalyEvent) -> None:
        style = "bold red" if event.severity == "warning" else "bold yellow"
        console.print(
            Panel(
                f"[{style}]{event.detail}[/{style}]",
                title=f"[{style}]Tier3: {event.anomaly_type}[/{style}]",
                border_style="red" if event.severity == "warning" else "yellow",
                padding=(0, 1),
                width=60,
            )
        )

    def _finalize_stream(self) -> None:
        if self._stream_live is not None:
            self._stream_live.__exit__(None, None, None)
            self._stream_live = None
        if self._stream_text:
            console.print(
                Panel(
                    self._stream_text,
                    title="[bold green]Iris[/bold green]",
                    border_style="green",
                    padding=(0, 1),
                    width=72,
                )
            )
            _time.sleep(0.3)
        self._stream_text = ""

    @property
    def is_streaming(self) -> bool:
        return self._stream_live is not None


__all__ = ["Renderer"]
