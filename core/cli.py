from __future__ import annotations
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live
from rich.spinner import Spinner

from core.config import Config
from core.llm_bridge import LLMBridge
from core.personality import Personality
from core.reflexion import Reflexion
from core.planner import Planner
from core.executor import Executor
from core.commands import IrisContext, handle_command, _run_reflexion_and_save
from memory.stores import AgentsMdStore, EpisodicStore, SemanticStore
from capabilities.registry import CapabilityRegistry

console = Console()
PROJECT_ROOT = Path(__file__).parent.parent


def _ensure_ollama(config: Config) -> LLMBridge | None:
    llm = LLMBridge(
        model_name=config.model.name,
        base_url=config.model.base_url,
    )
    if not llm.is_available():
        console.print(
            "[red]Ollama is not running![/red]\n"
            f"Please start Ollama and pull the model:\n"
            f"  ollama pull {config.model.name}\n"
            f"  ollama serve"
        )
        return None
    console.print(f"[green]Connected to Ollama ({config.model.name})[/green]")
    return llm


def _detect_complex(user_input: str) -> bool:
    triggers = [
        "調査", "調べて", "比較", "分析", "設計", "構築", "作成して",
        "research", "compare", "analyze", "design", "build", "create",
        "まず", "最初に", "その後", "step", "steps",
    ]
    return any(t in user_input.lower() for t in triggers)


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

    reflexion = Reflexion(llm=llm)
    planner = Planner(llm=llm)
    executor = Executor(llm=llm, registry=registry)
    ctx = IrisContext(llm=llm, config=config, registry=registry,
                      reflexion=reflexion, episodic=episodic,
                      semantic=semantic, planner=planner, executor=executor)

    console.print(Panel.fit(
        f"[bold cyan]Iris[/bold cyan] - v0.1.0\n"
        f"Model: {config.model.name} | Thinking mode: OFF\n"
        f"Type /help for commands, /think to toggle thinking mode",
        border_style="cyan",
    ))

    messages: list[dict] = []
    thinking_mode = config.personality.thinking_mode_default
    plan_mode = False

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]You[/bold cyan]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Goodbye![/yellow]")
            _run_reflexion_and_save(reflexion, messages, episodic, semantic)
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

        system_prompt = personality.build_system_prompt(agents_md.load())
        recent_episodes = episodic.get_recent(3)
        if recent_episodes:
            system_prompt += "\n\n## Recent Sessions\n" + "\n".join(f"- {e}" for e in recent_episodes)

        if thinking_mode:
            messages[-1] = messages[-1].copy()
            messages[-1]["content"] = personality.build_thinking_prompt(user_input)

        should_plan = plan_mode or (thinking_mode and _detect_complex(user_input))
        plan_result = None
        if should_plan:
            console.print("[dim]Analyzing task...[/dim]")
            _rag_results = semantic.search(user_input, max_results=config.memory.rag_max_results)
            if _rag_results:
                system_prompt += "\n\n## Related Lessons\n" + "\n".join(f"- {e['content']}" for e in _rag_results)
            plan_result = planner.analyze(user_input, system_prompt[:300])
            if not plan_mode:
                should_plan = planner.is_complex(plan_result)

        if should_plan:
            console.print(f"[yellow]Planning mode: {len(plan_result.get('subtasks', []))} subtasks[/yellow]")
            for st in plan_result.get("subtasks", []):
                console.print(f"  [dim]→ {st['name']}: {st['description'][:60]}[/dim]")

            def _on_step(i: int, name: str):
                console.print(f"  [dim]Step {i+1}: {name}...[/dim]")

            with console.status("[cyan]Executing plan...[/cyan]", spinner="dots"):
                step_results = executor.execute_plan(
                    plan_result, user_input, config.personality.name, on_subtask=_on_step,
                )

            with console.status("[cyan]Synthesizing results...[/cyan]", spinner="dots"):
                final_content = executor.synthesize(plan_result, step_results, user_input, config.personality.name)

            messages.append({"role": "assistant", "content": final_content})
            if final_content:
                console.print(Panel(Markdown(final_content), border_style="cyan"))
        else:
            parts: list[str] = []

            with Live(Panel(Spinner("dots", text="[dim]Memory search...[/dim]"), border_style="cyan"), refresh_per_second=15) as live:
                _rag_results = semantic.search(user_input, max_results=config.memory.rag_max_results)
                if _rag_results:
                    system_prompt += "\n\n## Related Lessons\n" + "\n".join(f"- {e['content']}" for e in _rag_results)

                live.update(Panel(Spinner("dots", text="[dim]Generating...[/dim]"), border_style="cyan"))
                response = llm.chat(
                    messages=[{"role": "system", "content": system_prompt}, *messages],
                    enable_thinking=thinking_mode,
                    temperature=config.model.temperature,
                    max_tokens=config.model.max_tokens,
                    tools=registry.list_tools(),
                    on_token=lambda tok: (
                        parts.append(tok),
                        live.update(Panel(Markdown("".join(parts)), border_style="cyan")),
                    ),
                )

            msg = response["message"]
            messages.append(msg)

            if msg.get("tool_calls"):
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

                parts.clear()
                with Live(Panel(Spinner("dots", text="[dim]Generating...[/dim]"), border_style="cyan"), refresh_per_second=15) as live:
                    final = llm.chat(
                        messages=[{"role": "system", "content": system_prompt}, *messages],
                        enable_thinking=thinking_mode,
                        temperature=config.model.temperature,
                        max_tokens=config.model.max_tokens,
                        on_token=lambda tok: (
                            parts.append(tok),
                            live.update(Panel(Markdown("".join(parts)), border_style="cyan")),
                        ),
                    )

                msg = final["message"]
                messages.append(msg)

            content = msg.get("content", "")
            if not parts and content:
                console.print()
                console.print(Panel(Markdown(content), border_style="cyan"))
