from __future__ import annotations
import sys
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.config import Config
from core.llm_bridge import LLMBridge
from core.reflexion import Reflexion
from core.planner import Planner
from core.executor import Executor
from memory.stores import EpisodicStore, SemanticStore
from capabilities.registry import CapabilityRegistry

console = Console(safe_box=True, legacy_windows=False)


@dataclass
class CommandResult:
    handled: bool
    thinking_mode: bool
    plan_mode: bool


@dataclass
class IrisContext:
    llm: LLMBridge
    config: Config
    registry: CapabilityRegistry
    reflexion: Reflexion
    episodic: EpisodicStore
    semantic: SemanticStore
    planner: Planner
    executor: Executor
    config_path: str = ""


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


def handle_command(cmd: str, ctx: IrisContext,
                   messages: list, thinking_mode: bool,
                   plan_mode: bool = False) -> CommandResult:
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
            return CommandResult(handled=True, thinking_mode=thinking_mode, plan_mode=plan_mode)
        case ["/think"]:
            thinking_mode = not thinking_mode
            state = "ON" if thinking_mode else "OFF"
            ctx.config.personality.thinking_mode_default = thinking_mode
            if ctx.config_path:
                ctx.config.save(ctx.config_path)
            console.print(f"[yellow]Thinking mode: {state}[/yellow]")
            return CommandResult(handled=True, thinking_mode=thinking_mode, plan_mode=plan_mode)
        case ["/plan"]:
            plan_mode = not plan_mode
            state = "ON" if plan_mode else "OFF"
            console.print(f"[yellow]Plan mode: {state}[/yellow]")
            return CommandResult(handled=True, thinking_mode=thinking_mode, plan_mode=plan_mode)
        case ["/model", name]:
            ctx.llm.set_model(name)
            ctx.config.model.name = name
            if ctx.config_path:
                ctx.config.save(ctx.config_path)
            console.print(f"[green]Switched to model: {name}[/green]")
            return CommandResult(handled=True, thinking_mode=thinking_mode, plan_mode=plan_mode)
        case ["/capabilities"]:
            table = Table(title="Registered Capabilities")
            table.add_column("Name", style="cyan")
            table.add_column("Description")
            for cap in ctx.registry._capabilities.values():
                table.add_row(cap.name, cap.description)
            console.print(table)
            return CommandResult(handled=True, thinking_mode=thinking_mode, plan_mode=plan_mode)
        case ["/memory"]:
            if not ctx.episodic or not ctx.semantic:
                console.print("[yellow]Memory stores not initialized[/yellow]")
                return CommandResult(handled=True, thinking_mode=thinking_mode, plan_mode=plan_mode)
            recent_eps = ctx.episodic.get_recent(3)
            all_sem = ctx.semantic._load_all()
            profile_path = Path(ctx.config.memory.agents_md_path)
            profile_size = len(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else 0
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
            return CommandResult(handled=True, thinking_mode=thinking_mode, plan_mode=plan_mode)
        case ["/clear"]:
            messages.clear()
            console.print("[yellow]Conversation cleared[/yellow]")
            return CommandResult(handled=True, thinking_mode=thinking_mode, plan_mode=plan_mode)
        case ["/exit"] | ["/quit"]:
            console.print("[yellow]Goodbye![/yellow]")
            if ctx.reflexion and ctx.episodic and ctx.semantic:
                _run_reflexion_and_save(ctx.reflexion, messages, ctx.episodic, ctx.semantic)
            sys.exit(0)
    return CommandResult(handled=False, thinking_mode=thinking_mode, plan_mode=plan_mode)
