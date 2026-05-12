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
from core.llm_bridge import LLMBridge
from core.personality import Personality
from core.reflexion import Reflexion
from core.planner import Planner
from core.executor import Executor
from core.commands import IrisContext, handle_command, _run_reflexion_and_save
from memory.persona_profile import PersonaProfile
from memory.stores import AgentsMdStore, EpisodicStore, SemanticStore
from capabilities.registry import CapabilityRegistry

console = Console(safe_box=True, legacy_windows=False)
PROJECT_ROOT = Path(__file__).parent.parent
_RAG_EXECUTOR = ThreadPoolExecutor(max_workers=1)

_GREETING_WORDS = {
    "hello", "hi", "bye", "hey", "thanks", "thank", "yes", "no",
    "good morning", "good evening", "good night",
    "おはよう", "こんにちは", "こんばんは", "おやすみ",
    "はい", "いいえ", "ありがとう", "おっす", "やあ",
}

_TOOL_HINTS = [
    "ファイル", "実行", "コード", "作成", "変更", "削除", "読み込み",
    "file", "write", "create", "run", "execute", "read", "delete",
    "list", "modify", "edit", "shell",
]

_SCENARIOS: dict[str, tuple[bool, int]] = {
    "greeting": (True, 128),
    "simple": (True, 512),
    "qa": (True, 1024),
    "tool": (False, 1024),
    "complex": (False, 1024),
}

_CLASSIFY_PROMPT = (
    "Classify the following user input into exactly ONE category. "
    "Reply with only the category word, nothing else.\n"
    "Categories:\n"
    "- greeting: simple hello, thanks, goodbye (no real request)\n"
    "- simple: short factual question, simple chat (fits in 1-2 sentences)\n"
    "- qa: requires explanation but no tool calls\n"
    "- tool: requires file operations, code execution, or shell commands\n"
    "- complex: multi-step task requiring planning and subtasks\n\n"
    "Input: {input}\n"
    "Category:"
)


def _quick_classify(user_input: str) -> str | None:
    lower = user_input.lower().strip()
    words = set(lower.split())
    is_short = len(lower) <= 15
    if is_short:
        if words & _GREETING_WORDS:
            return "greeting"
        if any(g in lower for g in _GREETING_WORDS):
            return "greeting"
    if any(h in lower for h in _TOOL_HINTS):
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
                       "content": _CLASSIFY_PROMPT.format(input=user_input)}],
            temperature=0,
            max_tokens=10,
        )
        raw = resp["message"].get("content", "").strip().lower()
        return raw if raw in _SCENARIOS else "simple"
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


def _quick_reflect_and_update(reflexion: Reflexion, messages: list, persona_profile: PersonaProfile):
    try:
        slice_for_reflect = messages[-8:] if len(messages) >= 8 else messages
        result = reflexion.quick_reflect(slice_for_reflect)
        if result.get("speech_style") or result.get("expressed_traits"):
            persona_profile.update_from_reflection(result)
    except Exception:
        pass


def _detect_complex(user_input: str) -> bool:
    triggers = [
        "調査", "調べて", "比較", "分析", "設計", "構築", "作成して",
        "research", "compare", "analyze", "design", "build", "create",
        "まず", "最初に", "その後", "step", "steps",
    ]
    return any(t in user_input.lower() for t in triggers)


_COMMANDS = [
    "/help", "/think", "/plan", "/model", "/clear", "/exit", "/quit",
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


def run_cli():
    config = Config.load(str(PROJECT_ROOT / "config.yaml"))

    if not (llm := _ensure_ollama(config)):
        return

    personality = Personality(
        name=config.personality.name,
        prompt_file=str(PROJECT_ROOT / config.personality.prompt_file),
    )
    agents_md = AgentsMdStore(
        path=str(PROJECT_ROOT / config.memory.agents_md_path),
        max_bytes=config.memory.agents_md_max_bytes,
    )
    episodic = EpisodicStore(
        path=str(PROJECT_ROOT / config.memory.episodic_path),
        max_entries=config.memory.episodic_max_entries,
    )
    semantic = SemanticStore(
        path=str(PROJECT_ROOT / config.memory.semantic_path),
        max_entries=config.memory.semantic_max_entries,
        vector_db_path=str(PROJECT_ROOT / config.memory.vector_db_path),
    )

    registry = CapabilityRegistry()
    registry.discover_modules(str(PROJECT_ROOT / "capabilities"))
    console.print(f"[green]Loaded {len(registry._capabilities)} capabilities[/green]")

    persona_profile = PersonaProfile(store=agents_md, semantic=semantic)
    speech_style = persona_profile.get_speech_style()
    if speech_style:
        console.print(f"[dim]Speech style: {speech_style[:60]}...[/dim]")
    console.print(f"[dim]Persona: {len(persona_profile._buf)} sections[/dim]")

    reflexion = Reflexion(llm=llm)
    planner = Planner(llm=llm)
    executor = Executor(llm=llm, registry=registry)
    ctx = IrisContext(llm=llm, config=config, config_path=str(PROJECT_ROOT / "config.yaml"),
                      registry=registry,
                      reflexion=reflexion, episodic=episodic,
                      semantic=semantic, planner=planner, executor=executor,
                      persona_profile=persona_profile)

    console.print(Panel.fit(
        f"[bold cyan]Iris[/bold cyan] - v0.1.0\n"
        f"Model: {config.model.smart_model} | Thinking mode: OFF\n"
        f"Type /help for commands, /think to toggle thinking mode",
        border_style="cyan",
    ))

    messages: list[dict] = []
    thinking_mode = config.personality.thinking_mode_default
    plan_mode = False
    active_model = config.model.fast_model or config.model.smart_model
    _msg_count_since_reflect = 0

    def _update_display(live: Live, p: list[str]):
        try:
            live.update(Panel(Markdown("".join(p)), border_style="cyan"))
        except Exception:
            pass

    session = PromptSession(
        history=FileHistory(str(PROJECT_ROOT / ".iris_history")),
        completer=WordCompleter(_COMMANDS, ignore_case=True),
    )

    while True:
        try:
            user_input = session.prompt(
                lambda: _make_prompt(thinking_mode, plan_mode, active_model, len(messages))
            )
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Goodbye![/yellow]")
            _run_reflexion_and_save(reflexion, messages, episodic, semantic, persona_profile)
            break

        if not user_input.strip():
            continue

        if user_input.startswith("/"):
            cmd_result = handle_command(user_input, ctx, messages, thinking_mode, plan_mode)
            if cmd_result.handled:
                thinking_mode = cmd_result.thinking_mode
                plan_mode = cmd_result.plan_mode
                continue

        messages.append({"role": "user", "content": user_input})

        system_prompt = personality.build_system_prompt(
            agents_md_content=agents_md.load(),
            speech_style=persona_profile.get_speech_style(),
            personality_traits=persona_profile.get_traits(),
            user_preferences=persona_profile.get_preferences_summary(),
        )
        recent_episodes = episodic.get_recent(3)
        if recent_episodes:
            system_prompt += "\n\n## Recent Sessions\n" + "\n".join(f"- {e}" for e in recent_episodes)

        has_fast = config.model.fast_model is not None

        category = _quick_classify(user_input)
        if category is None and has_fast:
            console.print("[dim]Classifying...[/dim]")
            category = _classify_input(llm, user_input, config.model.fast_model)
        scenario = category or "simple"
        use_fast, scenario_max_tokens = _SCENARIOS.get(scenario, (True, 256))

        force_smart = plan_mode or thinking_mode
        if force_smart or not use_fast or not has_fast:
            use_fast = False
            llm.set_model(config.model.smart_model)
            active_model = config.model.smart_model
            max_tokens = config.model.max_tokens
            tools_list = registry.list_tools()
            console.print(f"[blue]  Model:[/blue] {config.model.smart_model} [dim]({scenario})[/dim]")
        else:
            llm.set_model(config.model.fast_model)
            active_model = config.model.fast_model
            max_tokens = min(config.model.max_tokens_fast, scenario_max_tokens)
            tools_list = None
            console.print(f"[blue]  Model:[/blue] {config.model.fast_model} [dim]({scenario}, max_tokens={max_tokens})[/dim]")

        if thinking_mode:
            messages[-1] = messages[-1].copy()
            messages[-1]["content"] = personality.build_thinking_prompt(user_input)

        should_plan = False
        plan_result = None
        if not use_fast and (plan_mode or (thinking_mode and _detect_complex(user_input))):
            rag_future = _RAG_EXECUTOR.submit(semantic.search, user_input, max_results=config.memory.rag_max_results)
            console.print(f"[dim]Analyzing task ({config.model.smart_model})...[/dim]")
            plan_result = planner.analyze(user_input, system_prompt[:300])
            _rag_results = rag_future.result()
            if _rag_results:
                system_prompt += "\n\n## Related Lessons\n" + "\n".join(f"- {e['content']}" for e in _rag_results)
            if not plan_mode:
                should_plan = planner.is_complex(plan_result)

        if not use_fast and not plan_mode and not thinking_mode and user_input.strip().lower() in ("hello", "hi", "bye", "thanks", "ありがとう"):
            max_tokens = 64

        if should_plan:
            console.print(f"[yellow]Planning mode: {len(plan_result.get('subtasks', []))} subtasks[/yellow]")
            for st in plan_result.get("subtasks", []):
                console.print(f"  [dim]→ {st['name']}: {st['description'][:60]}[/dim]")

            def _on_step(i: int, name: str):
                console.print(f"  [dim]Step {i+1}: {name}...[/dim]")

            with console.status(f"[cyan]{active_model} executing {len(plan_result.get('subtasks', []))} subtasks...[/cyan]", spinner="dots"):
                final_content = executor.execute_plan(
                    plan_result, user_input, config.personality.name, on_subtask=_on_step,
                )

            messages.append({"role": "assistant", "content": final_content})
            if final_content:
                console.print(Panel(Markdown(final_content), border_style="cyan"))
        else:
            parts: list[str] = []
            trimmed = _trim_context(messages, config.model.context_window)

            rag_future = _RAG_EXECUTOR.submit(semantic.search, user_input, max_results=config.memory.rag_max_results)

            spinner_text = f"[dim]{active_model} ({scenario}, max_tokens={max_tokens})...[/dim]"
            with Live(Panel(Spinner("dots", text=spinner_text), border_style="cyan"), console=console, refresh_per_second=4, vertical_overflow="visible") as live:
                _rag_results = rag_future.result()
                if _rag_results:
                    system_prompt += "\n\n## Related Lessons\n" + "\n".join(f"- {e['content']}" for e in _rag_results)
                live.update(Panel(Spinner("dots", text=spinner_text), border_style="cyan"))
                response = llm.chat(
                    messages=[{"role": "system", "content": system_prompt}, *trimmed],
                    enable_thinking=thinking_mode,
                    temperature=config.model.temperature,
                    max_tokens=max_tokens,
                    tools=tools_list,
                    on_token=lambda tok: (
                        parts.append(tok),
                        _update_display(live, parts),
                    ),
                )

            msg = response["message"]
            messages.append(msg)

            if msg.get("tool_calls"):
                skip_llm = True
                tool_results = []
                for tc in msg["tool_calls"]:
                    func_name = tc["function"]["name"]
                    args = tc["function"]["arguments"]
                    result = registry.execute(func_name, **args)
                    messages.append({
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
                    messages.append(msg)
                else:
                    tool_spinner = f"[dim]{active_model} (tool result)...[/dim]"
                    with Live(Panel(Spinner("dots", text=tool_spinner), border_style="cyan"), console=console, refresh_per_second=4, vertical_overflow="visible") as live:
                        final = llm.chat(
                            messages=[{"role": "system", "content": system_prompt}, *messages],
                            enable_thinking=thinking_mode,
                            temperature=config.model.temperature,
                            max_tokens=config.model.max_tokens,
                            on_token=lambda tok: (
                                parts.append(tok),
                                _update_display(live, parts),
                            ),
                        )

                    msg = final["message"]
                    messages.append(msg)

            content = msg.get("content", "")
            if not parts and content:
                console.print()
                console.print(Panel(Markdown(content), border_style="cyan"))

        _msg_count_since_reflect += 1
        if _msg_count_since_reflect >= 5:
            _msg_count_since_reflect = 0
            _quick_reflect_and_update(reflexion, messages, persona_profile)
