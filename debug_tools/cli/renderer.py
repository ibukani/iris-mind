from __future__ import annotations

import time

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from iris.kernel.io.models import OutputMessage

console = Console()


class Renderer:
    def __init__(self) -> None:
        self._stream_live: Live | None = None
        self._stream_text: str = ""

    def handle(self, message: OutputMessage) -> None:
        handler = {
            "stream": self._on_stream,
            "response": self._on_response,
            "proactive": self._on_proactive,
            "command": self._on_command,
            "error": self._on_error,
        }.get(message.msg_type)
        if handler is not None:
            handler(message)

    def _on_stream(self, message: OutputMessage) -> None:
        if message.metadata.get("done"):
            self._finalize_stream()
            return
        if self._stream_live is None:
            self._stream_live = Live(console=console, refresh_per_second=12, vertical_overflow="visible")
            self._stream_live.__enter__()
        if message.content:
            self._stream_text += message.content
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

    def _on_response(self, message: OutputMessage) -> None:
        if self._stream_live is not None:
            return
        console.print(
            Panel(
                message.content,
                title="[bold green]Iris[/bold green]",
                border_style="green",
                padding=(0, 1),
                width=72,
            )
        )

    def _on_proactive(self, message: OutputMessage) -> None:
        console.print(
            Panel(
                f"[italic]{message.content}[/italic]",
                title="[bold yellow]Iris[/bold yellow]",
                border_style="yellow",
                padding=(0, 1),
                width=60,
            )
        )

    def _on_command(self, message: OutputMessage) -> None:
        console.print(message.content)

    def _on_error(self, message: OutputMessage) -> None:
        severity = message.metadata.get("severity", "warning")
        style = "bold red" if severity == "warning" else "bold yellow"
        console.print(
            Panel(
                f"[{style}]{message.content}[/{style}]",
                title=f"[{style}]Error[/{style}]",
                border_style="red" if severity == "warning" else "yellow",
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
            time.sleep(0.3)
        self._stream_text = ""

    @property
    def is_streaming(self) -> bool:
        return self._stream_live is not None
