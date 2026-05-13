from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.config import Config
from core.llm_bridge import LLMBridge
from core.reflexion import Reflexion
from memory.persona_profile import PersonaProfile
from memory.stores import EpisodicStore, SemanticStore

if TYPE_CHECKING:
    from capabilities.registry import CapabilityRegistry
    from core.context import ContextManager
    from core.executor import Executor
    from core.planner import Planner


console = Console(safe_box=True, legacy_windows=False)


@dataclass
class CommandResult:
    handled: bool
    mode: str


@dataclass
class CommandContext:
    """コマンド実行に必要な最小限の依存を集約。"""

    llm: LLMBridge
    config: Config
    config_path: str = ""
    registry: CapabilityRegistry | None = field(default=None, repr=False)
    reflexion: Reflexion | None = None
    episodic: EpisodicStore | None = None
    semantic: SemanticStore | None = None
    planner: Planner | None = field(default=None, repr=False)
    executor: Executor | None = field(default=None, repr=False)
    persona_profile: PersonaProfile | None = None
    context_manager: ContextManager | None = field(default=None, repr=False)


def _run_reflexion_and_save(
    reflexion: Reflexion,
    messages: list,
    episodic: EpisodicStore,
    semantic: SemanticStore,
    persona_profile=None,
):
    if len(messages) < 2:
        return
    console.print("[yellow]Reflecting on session...[/yellow]")
    result = reflexion.reflect(messages)
    summary = result.get("summary", "").strip()
    lesson = result.get("lesson", "").strip()
    preference = result.get("preference", "").strip()

    if summary:
        episodic.add(summary)
        console.print(f"[dim]Episode saved: {summary[:80]}[/dim]")
    if lesson:
        semantic.add(
            {
                "type": "lesson",
                "content": lesson,
                "tags": result.get("missing_capability", "").split() if result.get("missing_capability") else [],
                "timestamp": "",
                "context": "session_end",
            }
        )
        console.print(f"[dim]Lesson saved: {lesson[:80]}[/dim]")
    if preference:
        semantic.add(
            {
                "type": "preference",
                "content": preference,
                "tags": ["user_preference"],
                "timestamp": "",
                "context": "session_end",
            }
        )
        console.print(f"[dim]Preference saved: {preference[:80]}[/dim]")

    if persona_profile:
        persona_profile.update_from_reflection(result)
        console.print("[dim]Persona profile updated[/dim]")


_MODE_LABELS = {"auto": "AUTO", "deep": "DEEP", "stepwise": "STEPWISE"}


def handle_command(cmd: str, ctx: CommandContext, messages: list, mode: str = "auto") -> CommandResult:
    match cmd.lower().split():
        case ["/help"]:
            console.print(
                Panel(
                    "[bold]/mode[/bold] - show current mode\n"
                    "[bold]/mode auto[/bold] - auto mode (default, automatic model switching)\n"
                    "[bold]/mode deep[/bold] - deep mode (force smart model + CoT)\n"
                    "[bold]/mode stepwise[/bold] - stepwise mode (smart model + planning + execute)\n"
                    "/compact - compact conversation history (preserves summary)\n"
                    "/compact <instructions> - compact with custom instructions\n"
                    "/capabilities - list registered capabilities\n"
                    "/persona - show/manage my personality\n"
                    "/persona set speech_style|traits <text> - override speech style or traits\n"
                    "/persona reset - reset personality to defaults\n"
                    "/memory - show memory stats\n"
                    "/memory-clear - clear all memory (episodic, semantic, vector store)\n"
                    "/clear - clear conversation history\n"
                    "/exit - exit Iris",
                    title="Commands",
                    border_style="yellow",
                )
            )
            return CommandResult(handled=True, mode=mode)

        case ["/mode"]:
            default = ctx.config.personality.mode_default
            dflt = _MODE_LABELS.get(default, default)
            console.print(f"[yellow]Mode: {_MODE_LABELS.get(mode, mode)} (default: {dflt})[/yellow]")
            return CommandResult(handled=True, mode=mode)

        case ["/mode", new_mode] if new_mode in ("auto", "deep", "stepwise"):
            mode = new_mode
            if mode != "stepwise":
                ctx.config.personality.mode_default = mode
                if ctx.config_path:
                    ctx.config.save(ctx.config_path)
            console.print(f"[yellow]Mode: {_MODE_LABELS.get(mode, mode)}[/yellow]")
            return CommandResult(handled=True, mode=mode)

        case ["/mode", *_]:
            console.print("[yellow]Usage: /mode [auto|deep|stepwise][/yellow]")
            return CommandResult(handled=True, mode=mode)

        case ["/capabilities"]:
            _handle_capabilities(ctx)
            return CommandResult(handled=True, mode=mode)

        case ["/memory"]:
            _handle_memory_status(ctx)
            return CommandResult(handled=True, mode=mode)

        case ["/memory-clear"]:
            _handle_memory_clear(ctx)
            return CommandResult(handled=True, mode=mode)

        case ["/compact", *rest]:
            _handle_compact(ctx, messages, rest)
            return CommandResult(handled=True, mode=mode)

        case ["/clear"]:
            if ctx.context_manager:
                ctx.context_manager.clear()
            messages.clear()
            console.print("[yellow]Conversation cleared[/yellow]")
            return CommandResult(handled=True, mode=mode)

        case ["/exit"] | ["/quit"]:
            console.print("[yellow]Goodbye![/yellow]")
            if ctx.reflexion and ctx.episodic and ctx.semantic:
                _run_reflexion_and_save(
                    ctx.reflexion,
                    messages,
                    ctx.episodic,
                    ctx.semantic,
                    ctx.persona_profile,
                )
            sys.exit(0)

        case ["/persona"]:
            _handle_persona_list(ctx)
            return CommandResult(handled=True, mode=mode)

        case ["/persona", "set", target, *rest]:
            _handle_persona_set(ctx, target, rest)
            return CommandResult(handled=True, mode=mode)

        case ["/persona", "reset"]:
            if ctx.persona_profile:
                ctx.persona_profile.reset()
                console.print("[green]Persona reset to defaults[/green]")
            return CommandResult(handled=True, mode=mode)

    return CommandResult(handled=False, mode=mode)


def _handle_capabilities(ctx: CommandContext):
    if not ctx.registry:
        return
    table = Table(title="Registered Capabilities")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    for cap in ctx.registry._capabilities.values():
        table.add_row(cap.name, cap.description)
    console.print(table)


def _handle_memory_status(ctx: CommandContext):
    if not ctx.episodic or not ctx.semantic:
        console.print("[yellow]Memory stores not initialized[/yellow]")
        return
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


def _handle_memory_clear(ctx: CommandContext):
    if ctx.episodic and ctx.semantic:
        ctx.episodic.clear()
        ctx.semantic.clear()
        console.print("[yellow]All memory cleared (episodic, semantic, vector store)[/yellow]")
    else:
        console.print("[yellow]Memory stores not initialized[/yellow]")


def _handle_persona_list(ctx: CommandContext):
    if not ctx.persona_profile:
        console.print("[yellow]Persona profile not initialized[/yellow]")
        return
    styles = ctx.persona_profile.get_all_speech_styles()
    traits = ctx.persona_profile.get_all_traits()

    table = Table(title="Iris's Personality - accumulated data")
    table.add_column("Aspect", style="cyan")
    table.add_column("Entries")

    style_lines = "\n".join(f"  [{s.get('count', 1)}x] {s['text'][:60]}" for s in styles) if styles else "(未収集)"
    trait_lines = "\n".join(f"  [{t.get('count', 1)}x] {t['text'][:60]}" for t in traits) if traits else "(未収集)"

    table.add_row("Speech Style", style_lines)
    table.add_row("Personality Traits", trait_lines)

    profile_path = Path(ctx.config.memory.agents_md_path)
    profile_size = len(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else 0
    table.add_row("Profile Size", f"{profile_size} bytes")
    console.print(table)


def _handle_compact(ctx: CommandContext, messages: list, args: list[str]):
    cm = ctx.context_manager
    if not cm:
        console.print("[yellow]Context manager not initialized[/yellow]")
        return

    instructions = " ".join(args) if args else ""
    preserve = 6

    try:
        summary = cm.force_summarize(messages, instructions=instructions, preserve_last=preserve)
    except Exception as e:
        console.print(f"[red]Compaction failed: {e}[/red]")
        return

    if not summary:
        console.print("[yellow]Compaction produced no summary[/yellow]")
        return

    compacted = cm.build_compact_messages(messages, preserve_last=preserve)
    messages[:] = compacted

    old_count = len(messages)
    console.print(f"[yellow]Conversation compacted: {old_count} messages retained[/yellow]")


def _handle_persona_set(ctx: CommandContext, target: str, rest: list[str]):
    if not ctx.persona_profile:
        console.print("[yellow]Persona profile not initialized[/yellow]")
        return
    text = " ".join(rest)
    if target == "speech_style":
        ctx.persona_profile.set_speech_style(text)
        console.print("[green]Speech style updated[/green]")
    elif target == "traits":
        ctx.persona_profile.set_traits(text)
        console.print("[green]Personality traits updated[/green]")
    else:
        console.print(f"[yellow]Unknown target: {target}. Use speech_style or traits.[/yellow]")
