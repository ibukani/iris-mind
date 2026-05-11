#!/usr/bin/env python3
"""Iris - 自律的に行動し進化できるAI"""

import sys
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.markdown import Markdown

from core.config import Config
from core.llm_bridge import LLMBridge
from core.personality import Personality
from core.reflexion import Reflexion
from core.planner import Planner
from core.executor import Executor
from memory.stores import AgentsMdStore, EpisodicStore, SemanticStore
from capabilities.registry import CapabilityRegistry

console = Console()
PROJECT_ROOT = Path(__file__).parent


def run_cli():
    config = Config.load(str(PROJECT_ROOT / "config.yaml"))

    if not (llm := _ensure_ollama(config)):
        return

    personality = Personality(name=config.personality.name)
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

    recent_episodes = episodic.get_recent(3)
    if recent_episodes:
        console.print(f"[dim]Loaded {len(recent_episodes)} recent episodes from memory[/dim]")

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
            handled, thinking_mode, plan_mode = _handle_command(
                user_input, llm, config, messages, thinking_mode, registry,
                reflexion, episodic, semantic, planner, executor, plan_mode,
            )
            if handled:
                continue

        messages.append({"role": "user", "content": user_input})

        system_prompt = personality.build_system_prompt(agents_md.load())
        if recent_episodes:
            system_prompt += "\n\n## Recent Sessions\n" + "\n".join(f"- {e}" for e in recent_episodes)

        if thinking_mode:
            _inject_thinking_context(messages, personality, user_input)

        relevant_lessons = semantic.search(user_input, max_results=config.memory.rag_max_results)
        if relevant_lessons:
            lesson_text = "\n".join(f"- {e['content']}" for e in relevant_lessons)
            system_prompt += f"\n\n## Related Lessons\n{lesson_text}"

        should_plan = plan_mode or (thinking_mode and _detect_complex(user_input, llm))
        if should_plan and not plan_mode:
            plan_result = planner.analyze(user_input, system_prompt[:300])
            should_plan = planner.is_complex(plan_result)

        if should_plan:
            if not plan_mode:
                plan_result = planner.analyze(user_input, system_prompt[:300])
            console.print(f"[yellow]Planning mode: {len(plan_result.get('subtasks', []))} subtasks[/yellow]")
            for st in plan_result.get("subtasks", []):
                console.print(f"  [dim]→ {st['name']}: {st['description'][:60]}[/dim]")

            with console.status("[cyan]Executing plan...[/cyan]", spinner="dots"):
                step_results = executor.execute_plan(plan_result, system_prompt)

            with console.status("[cyan]Synthesizing results...[/cyan]", spinner="dots"):
                final_content = executor.synthesize(plan_result, step_results, system_prompt)

            messages.append({"role": "assistant", "content": final_content})
            if final_content:
                console.print(Panel(Markdown(final_content), border_style="cyan"))
        else:
            with console.status("[cyan]Thinking...[/cyan]", spinner="dots"):
                response = llm.chat(
                    messages=[{"role": "system", "content": system_prompt}, *messages],
                    enable_thinking=thinking_mode,
                    temperature=config.model.temperature,
                    max_tokens=config.model.max_tokens,
                    tools=registry.list_tools(),
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

                with console.status("[cyan]Processing results...[/cyan]", spinner="dots"):
                    final = llm.chat(
                        messages=[{"role": "system", "content": system_prompt}, *messages],
                        enable_thinking=thinking_mode,
                        temperature=config.model.temperature,
                        max_tokens=config.model.max_tokens,
                    )
                    msg = final["message"]
                    messages.append(msg)

            content = msg.get("content", "")
            if content:
                console.print(Panel(Markdown(content), border_style="cyan"))


def _run_reflexion_and_save(
    reflexion: Reflexion, messages: list, episodic: EpisodicStore, semantic: SemanticStore
):
    if len(messages) < 2:
        return
    console.print("[yellow]Reflecting on session...[/yellow]")
    result = reflexion.reflect(messages)
    summary = result.get("summary", "").strip()
    lesson = result.get("lesson", "").strip()
    if summary:
        episodic.add(summary)
        console.print(f"[dim]Episode saved: {summary[:80]}[/dim]")
    if lesson:
        semantic.add({
            "type": "lesson",
            "content": lesson,
            "tags": result.get("missing_capability", "").split() if result.get("missing_capability") else [],
            "timestamp": "",
            "context": "session_end",
        })
        console.print(f"[dim]Lesson saved: {lesson[:80]}[/dim]")


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


def _detect_complex(user_input: str, llm: LLMBridge) -> bool:
    """クイック判定：複数ツール・複数ステップが必要そうか"""
    triggers = [
        "調査", "調べて", "比較", "分析", "設計", "構築", "作成して",
        "research", "compare", "analyze", "design", "build", "create",
        "まず", "最初に", "その後", "step", "steps",
    ]
    return any(t in user_input.lower() for t in triggers)


def _inject_thinking_context(messages: list[dict], personality: Personality, user_input: str):
    messages[-1]["content"] = personality.build_thinking_prompt(user_input)


def _handle_command(cmd: str, llm: LLMBridge, config: Config,
                    messages: list, thinking_mode: bool,
                    registry: CapabilityRegistry,
                    reflexion: Reflexion | None = None,
                    episodic: EpisodicStore | None = None,
                    semantic: SemanticStore | None = None,
                    planner: Planner | None = None,
                    executor: Executor | None = None,
                    plan_mode: bool = False) -> tuple[bool, bool, bool]:
    from rich.table import Table

    match cmd.lower().split():
        case ["/help"]:
            console.print(Panel(
                "[bold]/think[/bold] - toggle thinking mode\n"
                "[bold]/plan[/bold] - toggle plan-and-execute mode\n"
                "/model <name> - switch model\n"
                "/capabilities - list registered capabilities\n"
                "/memory - show memory stats\n"
                "/clear - clear conversation history\n"
                "/exit - exit Iris",
                title="Commands",
                border_style="yellow",
            ))
            return True, thinking_mode, plan_mode
        case ["/think"]:
            thinking_mode = not thinking_mode
            state = "ON" if thinking_mode else "OFF"
            console.print(f"[yellow]Thinking mode: {state}[/yellow]")
            return True, thinking_mode, plan_mode
        case ["/plan"]:
            plan_mode = not plan_mode
            state = "ON" if plan_mode else "OFF"
            console.print(f"[yellow]Plan mode: {state}[/yellow]")
            return True, thinking_mode, plan_mode
        case ["/model", name]:
            llm.set_model(name)
            config.model.name = name
            console.print(f"[green]Switched to model: {name}[/green]")
            return True, thinking_mode, plan_mode
        case ["/capabilities"]:
            table = Table(title="Registered Capabilities")
            table.add_column("Name", style="cyan")
            table.add_column("Description")
            for cap in registry._capabilities.values():
                table.add_row(cap.name, cap.description)
            console.print(table)
            return True, thinking_mode, plan_mode
        case ["/memory"]:
            if not episodic or not semantic:
                console.print("[yellow]Memory stores not initialized[/yellow]")
                return True, thinking_mode, plan_mode
            from pathlib import Path
            from rich.table import Table
            recent_eps = episodic.get_recent(3)
            all_sem = semantic._load_all()
            profile_path = Path(config.memory.agents_md_path)
            profile_size = profile_path.read_text(encoding="utf-8").__len__() if profile_path.exists() else 0
            table = Table(title="Memory Stats")
            table.add_column("Store", style="cyan")
            table.add_column("Entries")
            table.add_row("Episodic", str(len(recent_eps)) + " recent" if recent_eps else "0")
            table.add_row("Semantic", str(len(all_sem)))
            table.add_row("Profile", str(profile_size) + " bytes")
            console.print(table)
            if recent_eps:
                console.print("\n[bold]Recent Episodes:[/bold]")
                for e in recent_eps:
                    console.print(f"  [dim]• {e[:100]}[/dim]")
            return True, thinking_mode, plan_mode
        case ["/clear"]:
            messages.clear()
            console.print("[yellow]Conversation cleared[/yellow]")
            return True, thinking_mode, plan_mode
        case ["/exit"] | ["/quit"]:
            console.print("[yellow]Goodbye![/yellow]")
            if reflexion and episodic and semantic:
                _run_reflexion_and_save(reflexion, messages, episodic, semantic)
            sys.exit(0)
    return False, thinking_mode, plan_mode


if __name__ == "__main__":
    run_cli()
