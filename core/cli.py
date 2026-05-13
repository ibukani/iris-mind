from __future__ import annotations
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from prompt_toolkit import PromptSession, HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import WordCompleter

from core.config import Config
from core.llm_bridge import LLMBridge
from core.personality import Personality
from core.reflexion import Reflexion
from core.planner import Planner
from core.executor import Executor
from core.context import ContextManager
from core.conversation import ConversationService
from core.commands import CommandContext, handle_command, _run_reflexion_and_save
from memory.persona_profile import PersonaProfile
from memory.persona_data import PersonaData
from memory.stores import AgentsMdStore, EpisodicStore, SemanticStore
from capabilities.registry import CapabilityRegistry

console = Console(safe_box=True, legacy_windows=False)
PROJECT_ROOT = Path(__file__).parent.parent

_COMMANDS = [
    "/help", "/think", "/plan", "/compact", "/model", "/clear", "/exit", "/quit",
    "/capabilities", "/memory", "/memory-clear", "/persona",
]


def _make_prompt(thinking: bool, plan: bool, model: str, msg_count: int) -> HTML:
    t = "[ON]" if thinking else "[OFF]"
    p = "[ON]" if plan else "[OFF]"
    return HTML(
        f"<ansicyan> Thinking:{t}</ansicyan> "
        f"<ansiyellow>Plan:{p}</ansiyellow> "
        f"<ansibrightblack>{model} | {msg_count} msgs</ansibrightblack>\n"
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
            fast_model=config.model.fast_model,
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
            smart_model=config.model.smart_model,
            fast_model=config.model.fast_model,
            temperature=config.model.temperature,
            max_tokens=config.model.max_tokens,
            max_tokens_fast=config.model.max_tokens_fast,
            context_window=config.model.context_window,
            compaction_threshold=config.model.compaction_threshold,
            rag_max_results=config.memory.rag_max_results,
        )

        self.ctx = CommandContext(
            llm=llm, config=config,
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
        console.print(Panel.fit(
            f"[bold cyan]Iris[/bold cyan] - v0.1.0\n"
            f"Model: {self.config.model.smart_model} | Thinking mode: OFF\n"
            f"Type /help for commands, /think to toggle thinking mode",
            border_style="cyan",
        ))

        thinking_mode = self.config.personality.thinking_mode_default
        plan_mode = False
        active_model = self.config.model.fast_model or self.config.model.smart_model
        msg_count_since_reflect = 0

        session = PromptSession(
            history=FileHistory(str(PROJECT_ROOT / ".iris_history")),
            completer=WordCompleter(_COMMANDS, ignore_case=True),
        )

        while True:
            try:
                user_input = session.prompt(
                    lambda: _make_prompt(thinking_mode, plan_mode, active_model, len(self.messages))
                )
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Goodbye![/yellow]")
                self._cleanup()
                break

            if not user_input.strip():
                continue

            if user_input.startswith("/"):
                cmd_result = handle_command(user_input, self.ctx, self.messages, thinking_mode, plan_mode)
                if cmd_result.handled:
                    thinking_mode = cmd_result.thinking_mode
                    plan_mode = cmd_result.plan_mode
                    continue

            self.messages.append({"role": "user", "content": user_input})

            has_fast = self.config.model.fast_model is not None
            if has_fast:
                console.print("[dim]Classifying...[/dim]")

            parts: list[str] = []

            def on_token(tok: str):
                parts.append(tok)

            result = self.conversation.process_input(
                user_input,
                self.messages,
                thinking_mode,
                plan_mode,
                active_model,
                msg_count_since_reflect,
                on_token=on_token if not plan_mode else None,
            )

            msg = result.response_message
            thinking_mode = result.thinking_mode
            plan_mode = result.plan_mode
            active_model = result.active_model
            msg_count_since_reflect = result.msg_count_since_reflect

            content = msg.get("content", "")
            if not parts and content:
                console.print()
                console.print(Panel(Markdown(content), border_style="cyan"))

    def _cleanup(self):
        _run_reflexion_and_save(
            self.reflexion, self.messages,
            self.episodic, self.semantic, self.persona_profile,
        )
