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
        path=str(PROJECT_ROOT / config.memory.vector_db_path / ".." / "episodes.jsonl"),
        max_entries=config.memory.episodic_max_entries,
    )
    semantic = SemanticStore(
        path=str(PROJECT_ROOT / config.memory.vector_db_path / ".." / "semantic.jsonl"),
        max_entries=config.memory.semantic_max_entries,
    )

    registry = CapabilityRegistry()
    registry.discover_modules(str(PROJECT_ROOT / "capabilities"))
    console.print(f"[green]Loaded {len(registry._capabilities)} capabilities[/green]")

    console.print(Panel.fit(
        f"[bold cyan]Iris[/bold cyan] - v0.1.0\n"
        f"Model: {config.model.name} | Thinking mode: OFF\n"
        f"Type /help for commands, /think to toggle thinking mode",
        border_style="cyan",
    ))

    messages: list[dict] = []
    thinking_mode = config.personality.thinking_mode_default

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]You[/bold cyan]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Goodbye![/yellow]")
            break

        if not user_input.strip():
            continue

        if user_input.startswith("/"):
            handled, thinking_mode = _handle_command(
                user_input, llm, config, messages, thinking_mode, registry
            )
            if handled:
                continue

        messages.append({"role": "user", "content": user_input})

        system_prompt = personality.build_system_prompt(agents_md.load())

        if thinking_mode:
            _inject_thinking_context(messages, personality, user_input)

        relevant_lessons = semantic.search(user_input, max_results=config.memory.rag_max_results)
        if relevant_lessons:
            lesson_text = "\n".join(f"- {e['content']}" for e in relevant_lessons)
            system_prompt += f"\n\n## Related Lessons\n{lesson_text}"

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


def _inject_thinking_context(messages: list[dict], personality: Personality, user_input: str):
    messages[-1]["content"] = personality.build_thinking_prompt(user_input)


def _handle_command(cmd: str, llm: LLMBridge, config: Config,
                    messages: list, thinking_mode: bool,
                    registry: CapabilityRegistry) -> tuple[bool, bool]:
    from rich.table import Table

    match cmd.lower().split():
        case ["/help"]:
            console.print(Panel(
                "[bold]/think[/bold] - toggle thinking mode\n"
                "/model <name> - switch model\n"
                "/capabilities - list registered capabilities\n"
                "/memory - show memory stats\n"
                "/clear - clear conversation history\n"
                "/exit - exit Iris",
                title="Commands",
                border_style="yellow",
            ))
        case ["/think"]:
            thinking_mode = not thinking_mode
            state = "ON" if thinking_mode else "OFF"
            console.print(f"[yellow]Thinking mode: {state}[/yellow]")
            return True, thinking_mode
        case ["/model", name]:
            llm.set_model(name)
            config.model.name = name
            console.print(f"[green]Switched to model: {name}[/green]")
            return True, thinking_mode
        case ["/capabilities"]:
            table = Table(title="Registered Capabilities")
            table.add_column("Name", style="cyan")
            table.add_column("Description")
            for cap in registry._capabilities.values():
                table.add_row(cap.name, cap.description)
            console.print(table)
            return True, thinking_mode
        case ["/clear"]:
            messages.clear()
            console.print("[yellow]Conversation cleared[/yellow]")
            return True, thinking_mode
        case ["/exit"] | ["/quit"]:
            console.print("[yellow]Goodbye![/yellow]")
            sys.exit(0)
    return False, thinking_mode


if __name__ == "__main__":
    run_cli()
