from __future__ import annotations

import logging
import time

from rich.console import Console
from rich.live import Live
from rich.panel import Panel

from iris.kernel.core import KernelContext

logger = logging.getLogger(__name__)
console = Console()


class CLIAdapter:
    def __init__(self, kernel: KernelContext) -> None:
        self._ctx = kernel
        self._stream_live: Live | None = None
        self._stream_text: str = ""

    def run(self) -> None:
        console.print()
        console.print(
            Panel.fit(
                "[bold cyan]Iris CLI[/bold cyan]\nType your message. [dim]Ctrl+C or 'exit' to quit.[/dim]",
                border_style="cyan",
            )
        )
        console.print()

        self._running = True
        try:
            while self._running:
                try:
                    text = input(">>> ").strip()
                except (EOFError, KeyboardInterrupt):
                    console.print()
                    break
                if not text:
                    continue
                if text.lower() in ("exit", "quit"):
                    break

                if text.startswith("/"):
                    self._ctx.proactive.notify_user_activity()
                    parts = text[1:].strip().split(maxsplit=1)
                    cmd = parts[0].lower()
                    args = parts[1] if len(parts) > 1 else ""
                    response = self._ctx.cmd_handler.handle(cmd, args)
                    if response:
                        console.print(f"[bold cyan][System][/bold cyan] {response}")
                    continue

                self._stream_text = ""
                with Live(console=console, refresh_per_second=12, vertical_overflow="visible") as live:
                    self._stream_live = live
                    self._ctx.conversation.process_input(
                        text,
                        on_complete=lambda text: self._ctx.kernel.on_response_complete(text),
                    )
                    if self._stream_text:
                        live.update(
                            Panel(
                                self._stream_text,
                                title="[bold green]Iris[/bold green]",
                                border_style="green",
                                padding=(0, 1),
                                width=72,
                            )
                        )
                        time.sleep(0.3)
                self._stream_live = None
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        try:
            self._ctx.conversation.session_reflect()
        except (KeyboardInterrupt, SystemExit):
            logger.warning("Session reflect interrupted by user")
        except Exception:
            logger.exception("Session reflect failed")
        self._ctx.kernel.shutdown()
        console.print("[dim]Shutdown complete.[/dim]")
