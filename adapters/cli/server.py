"""
CLI Adapter — ターミナル上の対話インターフェース。

AgentKernel を起動し、ユーザー入力 ←→ EventBus を橋渡しする。
自発発話（ProactiveSpeechEvent）および会話応答（AgentResponseEvent）を
Rich パネルでリアルタイム表示する。
"""

from __future__ import annotations

import logging
from datetime import datetime

from rich.console import Console
from rich.panel import Panel

from iris.kernel.agent_kernel import AgentKernel
from iris.kernel.agent_state import AgentStateManager
from iris.kernel.config import Config
from iris.kernel.conversation import ConversationService
from iris.kernel.event_bus import (
    AgentResponseEvent,
    EventBus,
    ProactiveSpeechEvent,
    UserInputEvent,
)
from iris.kernel.memory_manager import MemoryManager
from iris.kernel.proactive import ProactiveEngine
from iris.llm.llm_bridge import LLMBridge
from iris.personality.personality import Personality
from memory.stores import EpisodicStore, SemanticStore
from memory.vector_store import VectorStore

logger = logging.getLogger(__name__)
console = Console()


class CLIAdapter:
    """
    CLI アダプター — ターミナル対話インターフェース。

    使用方法:
        adapter = CLIAdapter()
        adapter.run()
    """

    def __init__(self, config_path: str = "config.yaml") -> None:
        self._config = Config.load(config_path)
        self._init_kernel()
        self._init_events()

    def _init_kernel(self) -> None:
        """カーネルコンポーネントを初期化する。"""
        self._event_bus = EventBus()
        self._state = AgentStateManager(event_bus=self._event_bus)

        # 記憶ストア（旧 memory/ からインスタンス化）
        cfg = self._config.memory
        self._episodic = EpisodicStore(
            path=cfg.episodic_path,
            max_entries=cfg.episodic_max_entries,
        )
        self._semantic = SemanticStore(
            path=cfg.semantic_path,
            max_entries=cfg.semantic_max_entries,
            vector_db_path=cfg.vector_db_path,
        )
        self._vector = VectorStore(path=cfg.vector_db_path)
        self._memory = MemoryManager(
            episodic=self._episodic,
            semantic=self._semantic,
            vector_store=self._vector,
        )

        # 自発発話エンジン
        self._proactive = ProactiveEngine(
            config=self._config.proactive,
            event_bus=self._event_bus,
            state_manager=self._state,
            memory=self._memory,
        )

        # カーネル（先に起動 → UserInputEvent を先に購読させる）
        self._kernel = AgentKernel(
            event_bus=self._event_bus,
            state_manager=self._state,
            proactive=self._proactive,
            memory=self._memory,
            config=self._config.proactive,
        )
        self._kernel.startup()

        # 会話サービス（カーネルの後に購読 → ハンドラ実行順を保証）
        self._llm = LLMBridge(
            model_name=self._config.model.base_model,
            base_url=self._config.model.base_url,
            num_gpu=self._config.model.num_gpu,
            num_ctx=self._config.model.num_ctx,
        )
        self._personality = Personality(name=self._config.personality.name)
        self._conversation = ConversationService(
            event_bus=self._event_bus,
            memory=self._memory,
            llm=self._llm,
            personality=self._personality,
            config=self._config,
        )

    def _init_events(self) -> None:
        """イベントハンドラを購読する。"""
        self._event_bus.subscribe(
            "ProactiveSpeechEvent", self._on_proactive_speech
        )
        self._event_bus.subscribe(
            "AgentResponseEvent", self._on_agent_response
        )

    # ── ライフサイクル ────────────────────────────────────

    def run(self) -> None:
        """メインループを開始する。"""
        console.print()
        console.print(
            Panel.fit(
                "[bold cyan]Iris CLI[/bold cyan]\n"
                "Type your message. [dim]Ctrl+C or 'exit' to quit.[/dim]",
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

                self._event_bus.publish(
                    UserInputEvent(
                        timestamp=datetime.now(),
                        source="user_input",
                        content=text,
                    )
                )
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """カーネルを停止する。"""
        self._kernel.shutdown()
        console.print("[dim]Shutdown complete.[/dim]")

    # ── イベントハンドラ ──────────────────────────────────

    def _on_proactive_speech(self, event: ProactiveSpeechEvent) -> None:
        """自発発話イベントを Rich パネルで表示する。"""
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


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    adapter = CLIAdapter()
    adapter.run()


if __name__ == "__main__":
    main()
