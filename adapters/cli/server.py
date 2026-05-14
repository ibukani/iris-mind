"""
CLI Adapter — ターミナル上の対話インターフェース。

AgentKernel を起動し、ユーザー入力 ←→ EventBus を橋渡しする。
自発発話（ProactiveSpeechEvent）および会話応答（AgentResponseEvent）を
Rich パネルでリアルタイム表示する。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

from rich.console import Console
from rich.panel import Panel

from iris.kernel.event_bus import (
    AgentAnomalyEvent,
    AgentResponseEvent,
    ProactiveSpeechEvent,
    UserInputEvent,
)
from iris.kernel.factory import KernelContext

logger = logging.getLogger(__name__)
console = Console()


class CLIAdapter:
    """
    CLI アダプター — ターミナル対話インターフェース。

    使用方法:
        ctx = KernelFactory.build(config)
        CLIAdapter(ctx).run()
    """

    def __init__(self, kernel: KernelContext) -> None:
        self._ctx = kernel
        self._proactive_pending_speech: float = 0.0
        self._init_events()

    def _init_events(self) -> None:
        """イベントハンドラを購読する。"""
        self._ctx.event_bus.subscribe("ProactiveSpeechEvent", self._on_proactive_speech)
        self._ctx.event_bus.subscribe("AgentResponseEvent", self._on_agent_response)
        self._ctx.event_bus.subscribe("AgentAnomalyEvent", self._on_anomaly)

    # ── ライフサイクル ────────────────────────────────────

    def run(self) -> None:
        """メインループを開始する。"""
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

                # 自発発話への反応追跡
                self._check_proactive_response(text)

                # コマンドハンドラで処理（/ で始まる入力をインターセプト）
                if text.startswith("/"):
                    self._ctx.proactive.notify_user_activity()
                    response = self._ctx.cmd_handler.handle(text)
                    if response:
                        console.print(f"[bold cyan][System][/bold cyan] {response}")
                    continue

                self._ctx.event_bus.publish(
                    UserInputEvent(
                        timestamp=datetime.now(),
                        source="user_input",
                        content=text,
                    )
                )
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """カーネルを停止し、セッション反省を実行する。"""
        try:
            self._ctx.conversation.session_reflect()
        except (KeyboardInterrupt, SystemExit):
            logger.warning("Session reflect interrupted by user")
        except Exception:
            logger.exception("Session reflect failed")
        self._ctx.kernel.shutdown()
        console.print("[dim]Shutdown complete.[/dim]")

    # ── イベントハンドラ ──────────────────────────────────

    def _check_proactive_response(self, text: str) -> None:
        """自発発話後のユーザー入力を判定し、ProactiveEngine に通知する。"""
        if not self._proactive_pending_speech:
            return
        elapsed = time.time() - self._proactive_pending_speech
        self._proactive_pending_speech = 0.0
        if elapsed > 60.0:
            return
        lower = text.strip().lower()
        if lower in ("やめて", "静かに", "stop", "やめろ", "黙れ", "うるさい", "やめてください", "shut up"):
            self._ctx.proactive.set_cooldown(600.0)
        else:
            self._ctx.proactive.notify_positive_response()

    def _on_proactive_speech(self, event: ProactiveSpeechEvent) -> None:
        """自発発話イベントを Rich パネルで表示する。"""
        self._proactive_pending_speech = time.time()
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

    def _on_agent_response(self, event: AgentResponseEvent) -> None:
        """会話応答イベントを Rich パネルで表示する。"""
        console.print(
            Panel(
                event.content,
                title="[bold green]Iris[/bold green]",
                border_style="green",
                padding=(0, 1),
                width=72,
            )
        )

    def _on_anomaly(self, event: AgentAnomalyEvent) -> None:
        """Tier3 異常検知イベントを表示する。"""
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
