from __future__ import annotations
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
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
from core.constants import (
    CLASSIFY_PROMPT, SCENARIOS,
    GREETING_WORDS, ENDING_WORDS, TOOL_HINTS, COMPLEX_TRIGGERS,
)
from core.llm_bridge import LLMBridge
from core.personality import Personality
from core.reflexion import Reflexion
from core.planner import Planner
from core.executor import Executor
from core.commands import CommandContext, handle_command, _run_reflexion_and_save
from memory.persona_profile import PersonaProfile
from memory.stores import AgentsMdStore, EpisodicStore, SemanticStore
from capabilities.registry import CapabilityRegistry

console = Console(safe_box=True, legacy_windows=False)
PROJECT_ROOT = Path(__file__).parent.parent
_RAG_EXECUTOR = ThreadPoolExecutor(max_workers=1)

_COMMANDS = [
    "/help", "/think", "/plan", "/model", "/clear", "/exit", "/quit",
    "/capabilities", "/memory", "/memory-clear", "/persona",
]


def _detect_complex(user_input: str) -> bool:
    return any(t in user_input.lower() for t in COMPLEX_TRIGGERS)


def _quick_classify(user_input: str, messages: list[dict] | None = None) -> str | None:
    lower = user_input.lower().strip()
    words = set(lower.split())
    is_short = len(lower) <= 15

    if is_short and any(e in lower for e in ENDING_WORDS):
        return "ending"

    if is_short:
        if words & GREETING_WORDS:
            return "greeting"
        if any(g in lower for g in GREETING_WORDS):
            return "greeting"

    if messages and len(messages) >= 2:
        prev = messages[-2].get("content", "").lower()
        if any(e in prev for e in ENDING_WORDS):
            return "ending"

    if any(h in lower for h in TOOL_HINTS):
        return "tool"
    if _detect_complex(user_input):
        return "complex"
    return None


def _classify_input(llm: LLMBridge, user_input: str, fast_model: str) -> str:
    prev = llm.model_name
    llm.set_model(fast_model)
    try:
        resp = llm.chat(
            messages=[{"role": "user",
                       "content": CLASSIFY_PROMPT.format(input=user_input)}],
            temperature=0,
            max_tokens=10,
        )
        raw = resp["message"].get("content", "").strip().lower()
        return raw if raw in SCENARIOS else "simple"
    except Exception:
        return "simple"
    finally:
        llm.set_model(prev)


def _trim_context(messages: list[dict], max_window: int) -> list[dict]:
    if max_window <= 0:
        return messages
    total = 0
    trimmed = []
    for msg in reversed(messages):
        rough = max(1, len(msg.get("content", "")) // 2)
        if total + rough > max_window:
            break
        total += rough
        trimmed.append(msg)
    return list(reversed(trimmed))


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


def _update_display(live: Live, parts: list[str]):
    try:
        live.update(Panel(Markdown("".join(parts)), border_style="cyan"))
    except Exception:
        pass


# ── 定数 ────────────────────────────────────────────────────
_SHORT_GREET_TOKENS = 64


class CliSession:
    """CLI セッション。対話ループとその補助ロジックをカプセル化する。"""

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

        self.persona_profile = PersonaProfile(store=self.agents_md, semantic=self.semantic)
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
        )
        self.messages: list[dict] = []

    # ── メインループ ──────────────────────────────────────────

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
            category = _quick_classify(user_input)
            if category is None and has_fast:
                console.print("[dim]Classifying...[/dim]")
                category = _classify_input(self.llm, user_input, self.config.model.fast_model)
            scenario = category or "simple"
            use_fast, scenario_max_tokens = SCENARIOS.get(scenario, (True, 256))

            force_smart = plan_mode or thinking_mode
            if force_smart or not use_fast or not has_fast:
                use_fast = False
                self.llm.set_model(self.config.model.smart_model)
                active_model = self.config.model.smart_model
                max_tokens = self.config.model.max_tokens
                tools_list = self.registry.list_tools()
                console.print(f"[blue]  Model:[/blue] {self.config.model.smart_model} [dim]({scenario})[/dim]")
            else:
                self.llm.set_model(self.config.model.fast_model)
                active_model = self.config.model.fast_model
                max_tokens = min(self.config.model.max_tokens_fast, scenario_max_tokens)
                tools_list = None
                console.print(f"[blue]  Model:[/blue] {self.config.model.fast_model} [dim]({scenario}, max_tokens={max_tokens})[/dim]")

            # 系統プロンプト構築
            _pref_results = self.semantic.search("ユーザーの好み user preference", max_results=3)
            _pref_text = "\n".join(f"- {p['content'][:120]}" for p in _pref_results) if _pref_results else ""
            system_prompt = self.personality.build_system_prompt(
                agents_md_content=self.agents_md.load(),
                speech_style=self.persona_profile.get_speech_style(),
                personality_traits=self.persona_profile.get_traits(),
                user_preferences=_pref_text,
            )

            recent_episodes = self.episodic.get_recent(3)
            if recent_episodes:
                system_prompt += "\n\n## Recent Sessions\n" + "\n".join(f"- {e}" for e in recent_episodes)

            # thinking mode 変換
            if thinking_mode:
                self.messages[-1] = self.messages[-1].copy()
                self.messages[-1]["content"] = self.personality.build_thinking_prompt(user_input)

            # ── プランニングフェーズ ────────────────────────────
            should_plan = False
            plan_result = None
            if not use_fast and (plan_mode or (thinking_mode and _detect_complex(user_input))):
                rag_future = _RAG_EXECUTOR.submit(self.semantic.search, user_input, max_results=self.config.memory.rag_max_results)
                console.print(f"[dim]Analyzing task ({self.config.model.smart_model})...[/dim]")
                plan_result = self.planner.analyze(user_input, system_prompt[:300])
                _rag_results = rag_future.result()
                if _rag_results:
                    system_prompt += "\n\n## Related Lessons\n" + "\n".join(f"- {e['content']}" for e in _rag_results)
                if not plan_mode:
                    should_plan = self.planner.is_complex(plan_result)

            # 短い挨拶のトークン制限
            if not use_fast and not plan_mode and not thinking_mode and user_input.strip().lower() in ("hello", "hi", "bye", "thanks", "ありがとう"):
                max_tokens = _SHORT_GREET_TOKENS

            # ── 実行フェーズ ────────────────────────────────────
            if should_plan:
                subtasks = plan_result.get("subtasks", [])
                console.print(f"[yellow]Planning mode: {len(subtasks)} subtasks[/yellow]")
                for st in subtasks:
                    console.print(f"  [dim]→ {st['name']}: {st['description'][:60]}[/dim]")

                def _on_step(i: int, name: str):
                    console.print(f"  [dim]Step {i+1}: {name}...[/dim]")

                with console.status(f"[cyan]{active_model} executing {len(subtasks)} subtasks...[/cyan]", spinner="dots"):
                    final_content = self.executor.execute_plan(
                        plan_result, user_input, self.config.personality.name, on_subtask=_on_step,
                    )

                self.messages.append({"role": "assistant", "content": final_content})
                if final_content:
                    console.print(Panel(Markdown(final_content), border_style="cyan"))
            else:
                parts: list[str] = []
                trimmed = _trim_context(self.messages, self.config.model.context_window)

                rag_future = _RAG_EXECUTOR.submit(self.semantic.search, user_input, max_results=self.config.memory.rag_max_results)

                spinner_text = "[cyan]Generating...[/cyan]"
                with Live(Panel(Spinner("dots", text=spinner_text), border_style="cyan"),
                          console=console, refresh_per_second=4, vertical_overflow="visible") as live:
                    _rag_results = rag_future.result()
                    if _rag_results:
                        system_prompt += "\n\n## Related Lessons\n" + "\n".join(f"- {e['content']}" for e in _rag_results)
                    live.update(Panel(Spinner("dots", text=spinner_text), border_style="cyan"))
                    response = self.llm.chat(
                        messages=[{"role": "system", "content": system_prompt}, *trimmed],
                        enable_thinking=thinking_mode,
                        temperature=self.config.model.temperature,
                        max_tokens=max_tokens,
                        tools=tools_list,
                        on_token=lambda tok: (
                            parts.append(tok),
                            _update_display(live, parts),
                        ),
                        keep_alive="0" if not use_fast else None,
                    )

                msg = response["message"]
                self.messages.append(msg)

                if msg.get("tool_calls"):
                    skip_llm = True
                    tool_results = []
                    for tc in msg["tool_calls"]:
                        func_name = tc["function"]["name"]
                        args = tc["function"]["arguments"]
                        result = self.registry.execute(func_name, **args)
                        self.messages.append({
                            "role": "tool",
                            "name": func_name,
                            "content": result,
                        })
                        console.print(f"[dim]  → {func_name}(...): {result[:120]}[/dim]")
                        tool_results.append((func_name, result))
                        if len(result) > 200 or any(w in result.lower() for w in ["error", "fail", "exception", "traceback"]):
                            skip_llm = False

                    parts.clear()
                    if skip_llm:
                        combined = "\n\n".join(
                            f"**{name}** result:\n{res}" for name, res in tool_results
                        )
                        msg = {"role": "assistant", "content": combined}
                        self.messages.append(msg)
                    else:
                        tool_spinner_text = "[cyan]Generating...[/cyan]"
                        with Live(Panel(Spinner("dots", text=tool_spinner_text), border_style="cyan"),
                                  console=console, refresh_per_second=4, vertical_overflow="visible") as live:
                            final = self.llm.chat(
                                messages=[{"role": "system", "content": system_prompt}, *self.messages],
                                enable_thinking=thinking_mode,
                                temperature=self.config.model.temperature,
                                max_tokens=self.config.model.max_tokens,
                                on_token=lambda tok: (
                                    parts.append(tok),
                                    _update_display(live, parts),
                                ),
                                keep_alive="0",
                            )

                        msg = final["message"]
                        self.messages.append(msg)

                content = msg.get("content", "")
                if not parts and content:
                    console.print()
                    console.print(Panel(Markdown(content), border_style="cyan"))

            # ── 定期的な自己反省 ────────────────────────────────
            msg_count_since_reflect += 1
            if msg_count_since_reflect >= 5:
                msg_count_since_reflect = 0
                try:
                    slice_for_reflect = self.messages[-8:] if len(self.messages) >= 8 else self.messages
                    result = self.reflexion.quick_reflect(slice_for_reflect)
                    if result.get("speech_style") or result.get("expressed_traits"):
                        self.persona_profile.update_from_reflection(result)
                except Exception:
                    pass

    def _cleanup(self):
        """終了時の後処理。"""
        _run_reflexion_and_save(
            self.reflexion, self.messages,
            self.episodic, self.semantic, self.persona_profile,
        )