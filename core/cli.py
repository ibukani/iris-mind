from __future__ import annotations

from pathlib import Path

from prompt_toolkit import HTML, PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

from capabilities.registry import CapabilityRegistry
from core.commands import CommandContext, _run_reflexion_and_save, handle_command
from core.config import Config
from core.context import ContextManager
from core.conversation import ConversationService
from core.executor import Executor
from core.llm_bridge import LLMBridge
from core.personality import Personality
from core.planner import Planner
from core.reflexion import Reflexion
from memory.persona_data import PersonaData
from memory.persona_profile import PersonaProfile
from memory.stores import AgentsMdStore, EpisodicStore, SemanticStore

console = Console(safe_box=True, legacy_windows=False)
PROJECT_ROOT = Path(__file__).parent.parent

_MODE_LABELS = {"auto": "AUTO", "deep": "DEEP", "stepwise": "STEP"}


_COMMANDS = [
    "/help",
    "/mode",
    "/compact",
    "/clear",
    "/exit",
    "/quit",
    "/capabilities",
    "/memory",
    "/memory-clear",
    "/persona",
]


def _make_prompt(mode: str, role: str, model: str, msg_count: int) -> HTML:
    label = _MODE_LABELS.get(mode, mode.upper())
    return HTML(
        f"<ansicyan> Mode:{label}</ansicyan> "
        f"<ansibrightblack>{role}[{model}] | {msg_count} msgs</ansibrightblack>\n"
        f"<ansicyan> You</ansicyan> > "
    )


class CliSession:
    """CLI セッション。UI（入力受付・表示）のみを担当し、会話ロジックは ConversationService に委譲する。"""

    def __init__(self, config: Config, llm: LLMBridge):
        self.config = config
        self.llm = llm

        self.personality = Personality(
            name=config.personality.name,
            prompt_file=str(PROJECT_ROOT / config.personality.prompt_file),
        )
        self.agents_md = AgentsMdStore(
            path=str(PROJECT_ROOT / config.memory.agents_md_path),
            max_bytes=config.memory.agents_md_max_bytes,
        )
        self.episodic = EpisodicStore(
            path=str(PROJECT_ROOT / config.memory.episodic_path),
            max_entries=config.memory.episodic_max_entries,
        )
        self.semantic = SemanticStore(
            path=str(PROJECT_ROOT / config.memory.semantic_path),
            max_entries=config.memory.semantic_max_entries,
            vector_db_path=str(PROJECT_ROOT / config.memory.vector_db_path),
        )

        self.registry = CapabilityRegistry()
        self.registry.discover_modules(str(PROJECT_ROOT / "capabilities"))
        console.print(f"[green]Loaded {len(self.registry._capabilities)} capabilities[/green]")

        self.persona_data = PersonaData()
        self.persona_profile = PersonaProfile(persona_data=self.persona_data)
        speech_style = self.persona_profile.get_speech_style()
        if speech_style:
            console.print(f"[dim]Speech: {speech_style[:60]}...[/dim]")
        traits = self.persona_profile.get_traits()
        if traits:
            console.print(f"[dim]Traits: {traits[:60]}...[/dim]")

        self.reflexion = Reflexion(llm=llm)
        self.planner = Planner(llm=llm)
        self.executor = Executor(llm=llm, registry=self.registry)

        self.context_manager = ContextManager(
            llm=llm,
            compact_model=config.model.base_model,
        )

        self.conversation = ConversationService(
            llm=llm,
            registry=self.registry,
            personality=self.personality,
            agents_md=self.agents_md,
            episodic=self.episodic,
            semantic=self.semantic,
            persona_profile=self.persona_profile,
            reflexion=self.reflexion,
            planner=self.planner,
            executor=self.executor,
            context_manager=self.context_manager,
            models=config.model.models,
            escalation_config=config.model.escalation,
            temperature=config.model.temperature,
            context_window=config.model.context_window,
            compaction_threshold=config.model.compaction_threshold,
            rag_max_results=config.memory.rag_max_results,
        )

        self.ctx = CommandContext(
            llm=llm,
            config=config,
            config_path=str(PROJECT_ROOT / "config.yaml"),
            registry=self.registry,
            reflexion=self.reflexion,
            episodic=self.episodic,
            semantic=self.semantic,
            planner=self.planner,
            executor=self.executor,
            persona_profile=self.persona_profile,
            context_manager=self.context_manager,
        )
        self.messages: list[dict] = []

    def run(self):
        console.print(
            Panel.fit(
                f"[bold cyan]Iris[/bold cyan] - v0.1.0\n"
                f"Models: {self.config.model.base_model} (base) / {self.config.model.smart_model} (smart)\n"
                f"Type /help for commands, /mode to change behavior mode",
                border_style="cyan",
            )
        )

        mode = self.config.personality.mode_default
        last_role = "base"
        msg_count_since_reflect = 0

        session: PromptSession = PromptSession(
            history=FileHistory(str(PROJECT_ROOT / ".iris_history")),
            completer=WordCompleter(_COMMANDS, ignore_case=True),
        )

        while True:
            try:
                current_model = self.config.model.base_model if last_role == "base" else self.config.model.smart_model
                user_input = session.prompt(lambda: _make_prompt(mode, last_role, current_model, len(self.messages)))
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Goodbye![/yellow]")
                self._cleanup()
                break

            if not user_input.strip():
                continue

            if user_input.startswith("/"):
                cmd_result = handle_command(user_input, self.ctx, self.messages, mode)
                if cmd_result.handled:
                    mode = cmd_result.mode
                    continue

            self.messages.append({"role": "user", "content": user_input})

            parts: list[str] = []
            streaming = mode != "stepwise"

            if streaming:
                live = Live(
                    Panel(Markdown(""), border_style="cyan"),
                    console=console,
                    refresh_per_second=10,
                    vertical_overflow="visible",
                )
                live.start()

                def on_token(tok: str):
                    parts.append(tok)
                    live.update(Panel(Markdown("".join(parts)), border_style="cyan"))
            else:
                live = None

                def on_token(tok: str):
                    parts.append(tok)

            try:
                result = self.conversation.process_input(
                    user_input,
                    self.messages,
                    mode,
                    last_role,
                    msg_count_since_reflect,
                    on_token=on_token if streaming else None,
                )
            finally:
                if live:
                    live.stop()

            msg = result.response_message
            mode = result.mode
            last_role = result.active_role
            msg_count_since_reflect = result.msg_count_since_reflect

            if result.escalated:
                console.print(f"[dim]Escalated to {result.active_model}[/dim]")

            if not streaming:
                display = "".join(parts) or msg.get("content", "")
                if display:
                    console.print()
                    console.print(Panel(Markdown(display), border_style="cyan"))

    def _cleanup(self):
        _run_reflexion_and_save(
            self.reflexion,
            self.messages,
            self.episodic,
            self.semantic,
            self.persona_profile,
        )
