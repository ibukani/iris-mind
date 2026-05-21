from __future__ import annotations

from collections.abc import Callable
import logging
from typing import TYPE_CHECKING

from iris.kernel.config import Config

if TYPE_CHECKING:
    from iris.io.session.manager import SessionManager
    from iris.kernel.debug_capture import DebugCapture
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
        debug_capture: DebugCapture | None = None,
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
        self._debug_capture = debug_capture

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

    def set_debug_capture(self, debug_capture: DebugCapture) -> None:
        self._debug_capture = debug_capture

    def handle(self, name: str, args: str = "") -> str:
        logger.info("CommandHandler: /%s %s", name, args[:100] if args else "")
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
        if name == "debug":
            return self._debug(args)
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
            "  /tools               List registered tools\n"
            "  /llm                Show LLM config\n"
            "  /personality        Show Big Five personality scores\n"
            "  /debug [on|off|...] Debug prompt/response capture"
        )

    def _status(self) -> str:
        cfg = self._config
        if cfg is None:
            return "Kernel running (no config)"
        lines = [
            f"Models: {[m.name for m in cfg.model.models]}",
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
        if self._memory.long_term.episodic:
            entries = self._memory.long_term.episodic.load_all()
            lines.append(f"  Episodic: {len(entries)} entries")
        if self._memory.long_term.semantic:
            entries = self._memory.long_term.semantic.load_all()
            lines.append(f"  Semantic: {len(entries)} entries")
        return "\n".join(lines)

    def _debug(self, args: str) -> str:
        dc = self._debug_capture
        if dc is None:
            return "DebugCapture not available"
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else ""

        if sub == "on":
            dc.set_enabled(True)
            return "Debug capture enabled"
        if sub == "off":
            dc.set_enabled(False)
            return "Debug capture disabled"

        if not dc.enabled:
            return "Debug capture is disabled (use /debug on first)"

        if sub == "list":
            return dc.list_captures()
        if sub == "last":
            entries = dc.last()
            if not entries:
                return "No captures"
            return "\n---\n".join(e.format_as_markdown() for e in entries)
        if sub in ("show", "get"):
            n_str = parts[1] if len(parts) > 1 else ""
            try:
                entry_id = int(n_str)
            except (ValueError, TypeError):
                return "Usage: /debug show <id>"
            return dc.show(entry_id)
        if sub == "dump":
            written = dc.dump_all()
            if written:
                return f"Wrote {len(written)} file(s):\n" + "\n".join(str(p) for p in written)
            return "No captures to dump"

        return (
            "Usage:\n"
            "  /debug on              Enable capture\n"
            "  /debug off             Disable capture\n"
            "  /debug list            List captured entries\n"
            "  /debug last            Show most recent capture(s)\n"
            "  /debug show <id>       Show specific capture\n"
            "  /debug dump            Write all captures to logs/debug/"
        )

    def _emotion(self) -> str:
        if not self._limbic:
            return "Limbic system not available"
        report = self._limbic.get_emotion_report()
        e = report.get("emotion", {})
        mood = report.get("mood_text", "")
        tags = report.get("recent_tags", [])
        lines = [
            f"Emotion: valence={e.get('valence', 0):.2f} arousal={e.get('arousal', 0):.2f} dominance={e.get('dominance', 0):.2f}",
            f"Mood: {mood or 'neutral'}",
        ]
        if tags:
            lines.append(f"Recent emotional tags ({len(tags)}):")
            lines.extend(f"  - {str(t)[:80]}" for t in tags[:3])
        return "\n".join(lines)

    def _sessions(self) -> str:
        if not self._session_mgr:
            return "Session manager not available"
        summary = self._session_mgr.get_sessions_summary()
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
        lines = [f"Default model: {cfg.model.get_model('default')}"]
        for m in cfg.model.models:
            conn = cfg.model.providers.get(m.provider)
            base_url = conn.base_url if conn else ""
            if not base_url:
                if m.provider == "ollama":
                    base_url = "http://localhost:11434"
                elif m.provider == "openrouter":
                    base_url = "https://openrouter.ai/api/v1"
                elif m.provider == "google":
                    base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
            info = f"  {m.name} [{m.provider}:{base_url}] ctx={m.num_ctx or cfg.model.default_num_ctx}"
            if m.num_gpu is not None:
                info += f" gpu={m.num_gpu}"
            if m.main_gpu is not None:
                info += f" main_gpu={m.main_gpu}"
            info += f" max_tokens={m.max_tokens}"
            lines.append(info)
        if self._llm:
            ok = self._llm.is_available()
            lines.append(f"Status: {'available' if ok else 'unreachable'}")
        return "\n".join(lines)

    def _personality(self) -> str:
        if not self._big_five:
            return "Big Five profile not available"
        return self._big_five.format_summary()
