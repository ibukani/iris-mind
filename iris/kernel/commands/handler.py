from __future__ import annotations

from collections.abc import Callable
import logging
from typing import TYPE_CHECKING

from iris.kernel.config import Config

if TYPE_CHECKING:
    from iris.io.session.manager import SessionManager
    from iris.limbic.manager import LimbicManager
    from iris.llm.llm_bridge import LLMBridge
    from iris.memory.manager import MemoryManager
    from iris.memory.personality.big_five import BigFiveProfile
    from iris.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class CommandHandler:
    def __init__(
        self,
        config: Config | None = None,
        on_shutdown: Callable[[], None] | None = None,
        on_compact: Callable[[], str] | None = None,
        memory: MemoryManager | None = None,
        limbic: LimbicManager | None = None,
        session_mgr: SessionManager | None = None,
        llm: LLMBridge | None = None,
        registry: ToolRegistry | None = None,
        big_five: BigFiveProfile | None = None,
    ) -> None:
        self._config = config
        self._on_shutdown = on_shutdown
        self._on_compact = on_compact
        self._memory = memory
        self._limbic = limbic
        self._session_mgr = session_mgr
        self._llm = llm
        self._registry = registry
        self._big_five = big_five

    def set_shutdown_handler(self, handler: Callable[[], None]) -> None:
        self._on_shutdown = handler

    def set_compact_handler(self, handler: Callable[[], str]) -> None:
        self._on_compact = handler

    def set_memory(self, memory: MemoryManager) -> None:
        self._memory = memory

    def set_limbic(self, limbic: LimbicManager) -> None:
        self._limbic = limbic

    def set_session_mgr(self, session_mgr: SessionManager) -> None:
        self._session_mgr = session_mgr

    def set_llm(self, llm: LLMBridge) -> None:
        self._llm = llm

    def set_registry(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def set_big_five(self, big_five: BigFiveProfile) -> None:
        self._big_five = big_five

    def handle(self, name: str, args: str = "") -> str:
        if name == "help":
            return self._help()
        if name == "status":
            return self._status()
        if name == "shutdown":
            return self._shutdown()
        if name == "compact":
            return self._compact()
        if name == "memory":
            return self._memory_cmd(args)
        if name == "emotion":
            return self._emotion()
        if name == "sessions":
            return self._sessions()
        if name == "ping":
            return self._ping()
        if name == "tools":
            return self._tools()
        if name == "llm":
            return self._llm_info()
        if name == "personality":
            return self._personality()
        return f"Unknown command: /{name}"

    def _help(self) -> str:
        return (
            "Available commands:\n"
            "  /help               Show this help\n"
            "  /status             Show kernel status\n"
            "  /shutdown           Graceful shutdown\n"
            "  /compact            Compact context\n"
            "  /memory recent [n]  Show recent episodic memories\n"
            "  /memory search <q>  Search semantic memory\n"
            "  /memory clear [type] Clear episodic/semantic memory\n"
            "  /emotion            Show current emotion state\n"
            "  /sessions           Show active sessions\n"
            "  /ping               Check LLM health\n"
            "  /tools              List registered tools\n"
            "  /llm                Show LLM config\n"
            "  /personality        Show Big Five personality scores"
        )

    def _status(self) -> str:
        cfg = self._config
        if cfg is None:
            return "Kernel running (no config)"
        lines = [
            f"Model: {cfg.model.provider} ({cfg.model.get_model('default')})",
            f"Session: {cfg.session.host}:{cfg.session.port}",
            f"Memory: episodic={cfg.memory.episodic_max_entries}, semantic={cfg.memory.semantic_max_entries}",
        ]
        if self._limbic:
            e = self._limbic.current_emotion()
            mood = self._limbic.build_mood_description(style="short")
            lines.append(f"Emotion: v={e.valence:.2f} a={e.arousal:.2f} d={e.dominance:.2f} ({mood})")
        return "\n".join(lines)

    def _shutdown(self) -> str:
        if self._on_shutdown:
            self._on_shutdown()
        return "Shutting down..."

    def _compact(self) -> str:
        if self._on_compact:
            return self._on_compact()
        return "Compact handler not available"

    def _memory_cmd(self, args: str) -> str:
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else ""

        if sub == "recent":
            n_str = parts[1] if len(parts) > 1 else "5"
            try:
                n = max(1, int(n_str))
            except ValueError:
                n = 5
            return self._memory_recent(n)

        if sub == "search":
            query = parts[1] if len(parts) > 1 else ""
            if not query:
                return "Usage: /memory search <query>"
            return self._memory_search(query)

        if sub == "clear":
            stream = parts[1].lower() if len(parts) > 1 else ""
            return self._memory_clear(stream)

        return self._memory_stats()

    def _memory_recent(self, n: int) -> str:
        if not self._memory:
            return "Memory not available"
        entries = self._memory.retrieve("episodic", n=n)
        if not entries:
            return "No episodic memories"
        lines = [f"Recent {len(entries)} episodic memories:"]
        for i, e in enumerate(entries, 1):
            summary = e.get("summary", "")[:120]
            ts = e.get("timestamp", "")[:19]
            lines.append(f"  {i}. [{ts}] {summary}")
        return "\n".join(lines)

    def _memory_search(self, query: str) -> str:
        if not self._memory:
            return "Memory not available"
        results = self._memory.search(query, stream="semantic", max_results=5)
        if not results:
            return f"No results for: {query}"
        lines = [f"Search results for '{query}':"]
        for r in results:
            content = r.get("content", "")[:120]
            score = r.get("score", 0)
            lines.append(f"  [{score:.2f}] {content}")
        return "\n".join(lines)

    def _memory_clear(self, stream: str) -> str:
        if not self._memory:
            return "Memory not available"
        valid = {"", "episodic", "semantic"}
        if stream not in valid:
            return "Usage: /memory clear [episodic|semantic]"
        s = stream if stream else None
        self._memory.clear(s)
        return f"Cleared {stream or 'all'} memory"

    def _memory_stats(self) -> str:
        if not self._memory:
            return "Memory not available"
        lines = ["Memory stats:"]
        if self._memory._episodic:
            entries = self._memory._episodic._load_all()
            lines.append(f"  Episodic: {len(entries)} entries")
        if self._memory._semantic:
            entries = self._memory._semantic._load_all()
            lines.append(f"  Semantic: {len(entries)} entries")
        return "\n".join(lines)

    def _emotion(self) -> str:
        if not self._limbic:
            return "Limbic system not available"
        report = self._limbic.get_emotion_report()
        e = report.get("emotion", {})
        mood = report.get("mood_text", "")
        tags = report.get("recent_tags", [])
        lines = [
            f"Emotion: valence={e.get('valence',0):.2f} arousal={e.get('arousal',0):.2f} dominance={e.get('dominance',0):.2f}",
            f"Mood: {mood or 'neutral'}",
        ]
        if tags:
            lines.append(f"Recent emotional tags ({len(tags)}):")
            lines.extend(f"  - {str(t)[:80]}" for t in tags[:3])
        return "\n".join(lines)

    def _sessions(self) -> str:
        if not self._session_mgr:
            return "Session manager not available"
        summary = self._session_mgr.get_roles_summary()
        if not summary:
            return "No active sessions"
        return summary

    def _ping(self) -> str:
        if not self._llm:
            return "LLM not available"
        ok = self._llm.is_available()
        return f"LLM: {'OK' if ok else 'UNREACHABLE'}"

    def _tools(self) -> str:
        if not self._registry:
            return "Tool registry not available"
        tools = self._registry.list_tools()
        if not tools:
            return "No tools registered"
        lines = [f"Registered tools ({len(tools)}):"]
        for t in tools:
            name = t.get("function", {}).get("name", "?")
            desc = t.get("function", {}).get("description", "")[:80]
            lines.append(f"  - {name}: {desc}")
        return "\n".join(lines)

    def _llm_info(self) -> str:
        cfg = self._config
        if not cfg:
            return "Config not available"
        lines = [
            f"Provider: {cfg.model.provider}",
            f"Model: {cfg.model.get_model('default')}",
        ]
        if self._llm:
            ok = self._llm.is_available()
            lines.append(f"Status: {'available' if ok else 'unreachable'}")
        return "\n".join(lines)

    def _personality(self) -> str:
        if not self._big_five:
            return "Big Five profile not available"
        return self._big_five.format_summary()
