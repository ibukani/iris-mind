from __future__ import annotations
import subprocess
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live
from rich.spinner import Spinner

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


def _ensure_ollama(config: Config) -> LLMBridge | None:
    llm = LLMBridge(
        model_name=config.model.smart_model,
        base_url=config.model.base_url,
        draft_model=config.model.draft_model,
        num_draft=config.model.num_draft,
        num_gpu=config.model.num_gpu,
        num_ctx=config.model.num_ctx,
    )
    if not llm.is_available():
        console.print("[yellow]Ollama is not running. Attempting to start it...[/yellow]")
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except FileNotFoundError:
            console.print(
                "[red]Could not find 'ollama' command![/red]\n"
                "Please install Ollama and ensure it is in your PATH:\n"
                "  https://ollama.com/download"
            )
            return None

        for _ in range(15):
            time.sleep(1)
            if llm.is_available():
                console.print(f"[green]Connected to Ollama ({config.model.smart_model})[/green]")
                break
        else:
            console.print(
                "[red]Ollama failed to start within 15 seconds.[/red]\n"
                f"Please start it manually:\n"
                f"  ollama pull {config.model.smart_model}\n"
                f"  ollama serve"
            )
            return None
    else:
        console.print(f"[green]Connected to Ollama ({config.model.smart_model})[/green]")

    if config.model.draft_model:
        try:
            models = llm.client.list()
            available = [m["name"] for m in models.get("models", [])]
            if config.model.draft_model not in available:
                console.print(
                    f"[yellow]Draft model '{config.model.draft_model}' not found.[/yellow]\n"
                    f"  Run: ollama pull {config.model.draft_model}\n"
                    f"  Then set: $env:OLLAMA_DRAFT_MODEL='{config.model.draft_model}'; ollama serve"
                )
            else:
                console.print(
                    f"[green]Draft model '{config.model.draft_model}' available.[/green]\n"
                    f"  [dim]To enable speculative decoding, restart Ollama with:\n"
                    f"  $env:OLLAMA_DRAFT_MODEL='{config.model.draft_model}'; ollama serve[/dim]"
                )
        except Exception:
            pass

    return llm


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
        self.persona_profile = PersonaProfile(store=self.agents_md, persona_data=self.persona_data)
        self.persona_profile.regenerate_view()
        speech_style = self.persona_profile.get_speech_style()
        if speech_style:
            console.print(f"[dim]Speech: {speech_style[:60]}...[/dim]")
        traits = self.persona_profile.get_traits()
        if traits:
            console.print(f"[dim]Traits: {traits[:60]}...[/dim]")
        console.print(
            f"[dim]Persona JSON: "
            f"{len(self.persona_profile._template.get('My Speech Style', ''))} speech, "
            f"{len(self.persona_profile._template.get('My Personality Traits', ''))} traits[/dim]"
        )

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
