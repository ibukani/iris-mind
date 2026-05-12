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
from memory.persona_profile import PersonaProfile
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
    persona_profile: PersonaProfile | None = None
    config_path: str = ""


def _run_reflexion_and_save(
    reflexion: Reflexion, messages: list, episodic: EpisodicStore, semantic: SemanticStore,
    persona_profile: PersonaProfile | None = None,
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
        semantic.add({
            "type": "lesson",
            "content": lesson,
            "tags": result.get("missing_capability", "").split() if result.get("missing_capability") else [],
            "timestamp": "",
            "context": "session_end",
        })
        console.print(f"[dim]Lesson saved: {lesson[:80]}[/dim]")
    if preference:
        semantic.add({
            "type": "preference",
            "content": preference,
            "tags": ["user_preference"],
            "timestamp": "",
            "context": "session_end",
        })
        console.print(f"[dim]Preference saved: {preference[:80]}[/dim]")

    if persona_profile:
        persona_profile.update_from_reflection(result)
        console.print("[dim]Persona profile updated[/dim]")


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
                "/persona - show/manage my personality\n"
                "/persona set speech_style|traits <text> - override speech style or traits\n"
                "/persona reset - reset personality to defaults\n"
                "/memory - show memory stats\n"
                "/memory-clear - clear all memory (episodic, semantic, vector store)\n"
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
            ctx.config.model.smart_model = name
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
        case ["/memory-clear"]:
            if ctx.episodic and ctx.semantic:
                ctx.episodic.clear()
                ctx.semantic.clear()
                console.print("[yellow]All memory cleared (episodic, semantic, vector store)[/yellow]")
            else:
                console.print("[yellow]Memory stores not initialized[/yellow]")
            return CommandResult(handled=True, thinking_mode=thinking_mode, plan_mode=plan_mode)
        case ["/clear"]:
            messages.clear()
            console.print("[yellow]Conversation cleared[/yellow]")
            return CommandResult(handled=True, thinking_mode=thinking_mode, plan_mode=plan_mode)
        case ["/exit"] | ["/quit"]:
            console.print("[yellow]Goodbye![/yellow]")
            if ctx.reflexion and ctx.episodic and ctx.semantic:
                _run_reflexion_and_save(ctx.reflexion, messages, ctx.episodic, ctx.semantic, ctx.persona_profile)
            sys.exit(0)
        case ["/persona"]:
            if not ctx.persona_profile:
                console.print("[yellow]Persona profile not initialized[/yellow]")
                return CommandResult(handled=True, thinking_mode=thinking_mode, plan_mode=plan_mode)
            style = ctx.persona_profile.get_speech_style() or "(未設定)"
            traits = ctx.persona_profile.get_traits() or "(未設定)"
            prefs = ctx.persona_profile.get_preferences_summary() or "(未収集)"
            table = Table(title="Iris's Personality")
            table.add_column("Aspect", style="cyan")
            table.add_column("Current State")
            table.add_row("Speech Style", style[:200])
            table.add_row("Personality Traits", traits[:200])
            table.add_row("Known Preferences", prefs[:200])
            console.print(table)
            return CommandResult(handled=True, thinking_mode=thinking_mode, plan_mode=plan_mode)
        case ["/persona", "set", target, *rest]:
            if not ctx.persona_profile:
                console.print("[yellow]Persona profile not initialized[/yellow]")
                return CommandResult(handled=True, thinking_mode=thinking_mode, plan_mode=plan_mode)
            text = " ".join(rest)
            if target == "speech_style":
                ctx.persona_profile.set_speech_style(text)
                console.print("[green]Speech style updated[/green]")
            elif target == "traits":
                ctx.persona_profile.set_traits(text)
                console.print("[green]Personality traits updated[/green]")
            else:
                console.print(f"[yellow]Unknown target: {target}. Use speech_style or traits.[/yellow]")
            return CommandResult(handled=True, thinking_mode=thinking_mode, plan_mode=plan_mode)
        case ["/persona", "reset"]:
            if ctx.persona_profile:
                ctx.persona_profile.reset()
                console.print("[green]Persona reset to defaults[/green]")
            return CommandResult(handled=True, thinking_mode=thinking_mode, plan_mode=plan_mode)
    return CommandResult(handled=False, thinking_mode=thinking_mode, plan_mode=plan_mode)
