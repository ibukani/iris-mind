from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.io.session.manager import SessionManager
    from iris.kernel.config import Config
    from iris.limbic.prefrontal.personality import BigFiveProfile
    from iris.limbic.manager import LimbicManager
    from iris.llm.bridge import LLMBridge
    from iris.tools.registry import ToolRegistry


class InfoCommands:
    def __init__(
        self,
        config: Config | None = None,
        limbic: LimbicManager | None = None,
        session_mgr: SessionManager | None = None,
        llm: LLMBridge | None = None,
        registry: ToolRegistry | None = None,
        big_five: BigFiveProfile | None = None,
    ) -> None:
        self._config = config
        self._limbic = limbic
        self._session_mgr = session_mgr
        self._llm = llm
        self._registry = registry
        self._big_five = big_five

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

    def emotion(self) -> str:
        if not self._limbic:
            return "Limbic system not available"
        report = self._limbic.get_report()
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

    def sessions(self) -> str:
        if not self._session_mgr:
            return "Session manager not available"
        summary = self._session_mgr.get_sessions_summary()
        if not summary:
            return "No active sessions"
        return summary

    def ping(self) -> str:
        if not self._llm:
            return "LLM not available"
        ok = self._llm.is_available()
        return f"LLM: {'OK' if ok else 'UNREACHABLE'}"

    def tools(self) -> str:
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

    def llm_info(self) -> str:
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

    def personality(self) -> str:
        if not self._big_five:
            return "Big Five profile not available"
        return self._big_five.format_summary()
