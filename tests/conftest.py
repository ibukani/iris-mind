from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest

from iris.event import EventBus
from iris.io.models import CommandOutput, Message
from iris.kernel.config import Config, ModelConfig, ProactiveConfig

# ── Fake LLM Provider ─────────────────────────────────────────


class FakeLLMProvider:
    def __init__(self, responses: list[dict] | None = None) -> None:
        self.call_count = 0
        self._responses = responses or [{"message": {"content": "Hello from FakeLLM", "role": "assistant"}}]
        self._messages_log: list[list[dict]] = []
        self._model_log: list[str | None] = []

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        enable_thinking: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        on_token: Callable[[str], None] | None = None,
        **kwargs: Any,
    ) -> dict:
        self._messages_log.append(messages)
        self._model_log.append(model)
        resp = self._responses[self.call_count % len(self._responses)]
        self.call_count += 1
        return resp

    def is_available(self) -> bool:
        return True

    def unload_model(self, model_name: str) -> None:
        pass


# ── Fake Memory Stores ────────────────────────────────────────


class FakeEpisodicStore:
    def __init__(self) -> None:
        self._entries: list[dict] = []

    def add(self, summary: str) -> None:
        self._entries.append({"summary": summary})

    def get_recent(self, n: int = 5) -> list[str]:
        return [e["summary"] for e in self._entries[-n:]]

    def clear(self) -> None:
        self._entries.clear()

    @property
    def count(self) -> int:
        return len(self._entries)


class FakeSemanticStore:
    def __init__(self) -> None:
        self._entries: list[dict] = []

    def add(self, entry: dict) -> None:
        if self._is_duplicate(entry.get("content", "")):
            return
        entry.setdefault("id", f"e{len(self._entries) + 1:03d}")
        entry.setdefault("tags", [])
        self._entries.append(entry)

    def search(self, query: str, max_results: int = 3) -> list[dict]:
        results = []
        for e in self._entries:
            if any(t in e.get("tags", []) for t in query.lower().split()):
                results.append({**e, "score": 0.8})
            elif query.lower() in e.get("content", "").lower():
                results.append({**e, "score": 0.6})
        return sorted(results, key=lambda x: x["score"], reverse=True)[:max_results]

    def clear(self) -> None:
        self._entries.clear()

    def _is_duplicate(self, content: str) -> bool:
        return any(e.get("content") == content for e in self._entries)

    @property
    def count(self) -> int:
        return len(self._entries)


class FakeVectorStore:
    def __init__(self) -> None:
        self._entries: list[dict] = []

    def add(self, entry: dict) -> None:
        self._entries.append(entry)

    def update(self, entry: dict) -> None:
        for i, e in enumerate(self._entries):
            if e.get("id") == entry.get("id"):
                self._entries[i] = entry
                return

    def delete(self, eid: str) -> None:
        self._entries = [e for e in self._entries if e.get("id") != eid]

    def clear(self) -> None:
        self._entries.clear()

    def search(self, query: str, max_results: int = 3, min_score: float = 0.0) -> list[dict]:
        results = []
        for e in self._entries:
            content = e.get("content", "")
            score = 0.7 + len(query) / max(len(content), 1) * 0.3 if query.lower() in content.lower() else 0.1
            if score >= min_score:
                results.append({**e, "score": min(score, 1.0)})
        return sorted(results, key=lambda x: x["score"], reverse=True)[:max_results]

    def count(self) -> int:
        return len(self._entries)


@dataclass
class FakeMemoryManager:
    episodic: FakeEpisodicStore = field(default_factory=FakeEpisodicStore)
    semantic: FakeSemanticStore = field(default_factory=FakeSemanticStore)
    vector_store: FakeVectorStore = field(default_factory=FakeVectorStore)
    _preferences: list[dict] = field(default_factory=list)

    def search_semantic(self, query: str, max_results: int = 3) -> list[dict]:
        return self.semantic.search(query, max_results=max_results)

    def get_user_preferences(self) -> list[dict]:
        return self._preferences

    def add_episodic(self, content: str, kind: str = "user_input", metadata: dict | None = None) -> None:
        self.episodic.add(content)

    def add_semantic(self, content: str, tags: list[str] | None = None) -> None:
        self.semantic.add({"content": content, "tags": tags or []})

    def add_semantic_by_type(self, entry_type: str, content: str, tags: list[str] | None = None) -> None:
        self.semantic.add({"content": content, "tags": tags or [], "type": entry_type})

    def get_recent(self, n: int = 3) -> list[dict]:
        entries = self.episodic.get_recent(n)
        return [{"summary": e} for e in entries]


# ── Fake Persona ──────────────────────────────────────────────


class FakePersonaData:
    def __init__(self) -> None:
        self._entries: list[dict] = []

    def add_entry(self, category: str, text: str, source: str = "reflection") -> None:
        self._entries.append({"category": category, "text": text, "source": source})

    def get_top(self, category: str, n: int = 5) -> list[dict]:
        return [e for e in self._entries if e["category"] == category][:n]

    def get_all(self, category: str) -> list[dict]:
        return [e for e in self._entries if e["category"] == category]

    def clear(self) -> None:
        self._entries.clear()


class FakePersonaProfile:
    def __init__(self, persona_data: FakePersonaData | None = None) -> None:
        self._data = persona_data or FakePersonaData()
        self._speech_style = ""
        self._traits = ""

    def get_speech_style(self) -> str:
        return self._speech_style

    def get_traits(self) -> str:
        return self._traits

    def update_from_reflection(self, reflection: dict[str, str]) -> None:
        if reflection.get("speech_style"):
            self._speech_style = reflection["speech_style"]
        if reflection.get("expressed_traits"):
            self._traits = reflection["expressed_traits"]

    def set_speech_style(self, text: str) -> None:
        self._speech_style = text

    def set_traits(self, text: str) -> None:
        self._traits = text

    def reset(self) -> None:
        self._speech_style = ""
        self._traits = ""


# ── Fake AgentsMdStore ────────────────────────────────────────


@dataclass
class FakeSessionInfo:
    session_id: str = ""
    role: str = ""
    permissions: list = field(default_factory=list)
    identity: str = ""


class FakeSessionManager:
    def __init__(self) -> None:
        self.sent: list[Message | CommandOutput] = []
        self._session_info: FakeSessionInfo | None = None

    def set_session_info(self, info: FakeSessionInfo) -> None:
        self._session_info = info

    def route_message(self, msg: Message) -> None:
        self.sent.append(msg)

    def route_command_output(self, session_id: str, msg: CommandOutput) -> None:
        self.sent.append(msg)

    def is_session_active(self, session_id: str) -> bool:
        return bool(session_id)

    def get_session_info(self, session_id: str) -> FakeSessionInfo | None:
        return self._session_info

    def get_sessions_summary(self) -> str:
        info = self._session_info
        if info and info.permissions:
            r = ", ".join(p.value if hasattr(p, "value") else str(p) for p in info.permissions)
            return f"Connected clients:\n{info.role}: {r}"
        return ""


class FakeAgentsMdStore:
    def __init__(self, content: str = "") -> None:
        self._content = content
        self.update_called_with: str | None = None

    def load(self) -> str:
        return self._content

    def update(self, new_content: str) -> None:
        self._content = new_content
        self.update_called_with = new_content


# ── Fake ContextManager ───────────────────────────────────────


class FakeContextManager:
    def __init__(self) -> None:
        self.has_summary = False
        self._summary = ""
        self._compact_messages: list[dict] = []

    def check_and_summarize(
        self, messages: list[dict], context_window: int, threshold: float = 0.7, preserve_last: int = 4
    ) -> str:
        return self._summary

    def force_summarize(self, messages: list[dict], instructions: str = "", preserve_last: int = 2) -> str:
        self.has_summary = True
        self._summary = "Fake summary"
        return self._summary

    def build_compact_messages(self, messages: list[dict], preserve_last: int = 4) -> list[dict]:
        return self._compact_messages or [
            {"role": "system", "content": f"[Compact summary of {len(messages)} messages]"}
        ]

    def clear(self) -> None:
        self.has_summary = False
        self._summary = ""
        self._compact_messages.clear()


# ── Fake ToolExecutionEngine ──────────────────────────────────


class FakeCapabilityRegistry:
    def __init__(self) -> None:
        self._tools: list[dict] = []
        self._side_effects: set[str] = set()

    def list_tools(self) -> list[dict]:
        return self._tools

    def register_func(
        self, name: str, description: str = "", parameters: dict | None = None, **kwargs: Any
    ) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._tools.append(
                {
                    "type": "function",
                    "function": {"name": name, "description": description, "parameters": parameters or {}},
                }
            )
            return func

        return decorator

    def execute(self, name: str, **kwargs: Any) -> str:
        return f"Executed {name} with {kwargs}"

    def register_decorated(self, fn: Any) -> None:
        pass

    def is_side_effect(self, name: str) -> bool:
        return name in self._side_effects


class FakeToolExecutionEngine:
    def __init__(self) -> None:
        self.registry = FakeCapabilityRegistry()
        self._executed_results: list[tuple[str, str, bool]] = []

    def execute_all(self, ctx: list[dict]) -> list[tuple[str, str, bool]]:
        results: list[tuple[str, str, bool]] = []
        for msg in ctx:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    name = tc["function"]["name"]
                    is_side = self.registry.is_side_effect(name)
                    triple = (name, "ok", is_side)
                    results.append(triple)
                    self._executed_results.append(triple)
                    if not is_side:
                        ctx.append({"role": "tool", "content": "Result: ok", "tool_call_id": tc.get("id", "")})
        return results

    @staticmethod
    def all_side_effects(results: list[tuple[str, str, bool]]) -> bool:
        return bool(results) and all(r[2] for r in results)


# ── Fake Reflexion ────────────────────────────────────────────


class FakeReflexion:
    def __init__(self, reflect_result: dict[str, str] | None = None) -> None:
        self._reflect_result = reflect_result or {
            "summary": "Test summary",
            "lesson": "Test lesson",
            "preference": "Test preference",
            "improvement": "Test improvement",
            "speech_style": "friendly",
            "expressed_traits": "helpful",
            "user_reaction": "positive",
        }
        self.reflect_calls: list[list[dict]] = []
        self.quick_reflect_calls: list[list[dict]] = []

    def reflect(self, conversation_history: list[dict]) -> dict[str, str]:
        self.reflect_calls.append(conversation_history)
        return dict(self._reflect_result)

    def quick_reflect(self, conversation_slice: list[dict]) -> dict[str, str]:
        self.quick_reflect_calls.append(conversation_slice)
        result = {
            "speech_style": self._reflect_result.get("speech_style", ""),
            "expressed_traits": self._reflect_result.get("expressed_traits", ""),
            "user_reaction": self._reflect_result.get("user_reaction", ""),
        }
        return {k: v for k, v in result.items() if v}

    def should_add_capability(self, reflection: dict[str, str]) -> bool:
        return bool(reflection.get("missing_capability"))


# ── Fake Personality ──────────────────────────────────────────


class FakePersonality:
    def __init__(self, name: str = "Iris") -> None:
        self.name = name
        self._system_prompt = ""
        self._thinking_prompt = ""

    def build_system_prompt(
        self,
        agents_md_content: str = "",
        speech_style: str = "",
        personality_traits: str = "",
        user_preferences: str = "",
        governance_principles: str = "",
        session_roles: str = "",
    ) -> str:
        parts = [
            f"## Iris Profile\n{agents_md_content}" if agents_md_content else "",
            f"## Personality\n{personality_traits}" if personality_traits else "",
            f"## Speech Style\n{speech_style}" if speech_style else "",
            f"## User Preferences\n{user_preferences}" if user_preferences else "",
            f"## Governance\n{governance_principles}" if governance_principles else "",
            f"## Sessions\n{session_roles}" if session_roles else "",
        ]
        self._system_prompt = "\n\n".join(p for p in parts if p) or "Default system prompt"
        return self._system_prompt

    def build_thinking_prompt(self, user_input: str) -> str:
        self._thinking_prompt = f"Think about: {user_input}"
        return self._thinking_prompt


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def fake_llm() -> FakeLLMProvider:
    return FakeLLMProvider()


@pytest.fixture
def fake_episodic() -> FakeEpisodicStore:
    return FakeEpisodicStore()


@pytest.fixture
def fake_semantic() -> FakeSemanticStore:
    return FakeSemanticStore()


@pytest.fixture
def fake_vector() -> FakeVectorStore:
    return FakeVectorStore()


@pytest.fixture
def fake_memory() -> FakeMemoryManager:
    return FakeMemoryManager()


@pytest.fixture
def fake_persona_data() -> FakePersonaData:
    return FakePersonaData()


@pytest.fixture
def fake_persona_profile() -> FakePersonaProfile:
    return FakePersonaProfile()


@pytest.fixture
def fake_agents_md() -> FakeAgentsMdStore:
    return FakeAgentsMdStore()


@pytest.fixture
def fake_context_mgr() -> FakeContextManager:
    return FakeContextManager()


@pytest.fixture
def fake_tool_exec() -> FakeToolExecutionEngine:
    return FakeToolExecutionEngine()


@pytest.fixture
def fake_reflexion() -> FakeReflexion:
    return FakeReflexion()


@pytest.fixture
def fake_personality() -> FakePersonality:
    return FakePersonality()


@pytest.fixture
def minimal_config() -> Config:
    return Config(
        model=ModelConfig(
            models=[{"name": "test-model", "roles": ["default"]}],  # pyright: ignore[reportArgumentType]
            provider="ollama",
            base_url="http://localhost:11434",
        ),
    )


@pytest.fixture
def proactive_config() -> ProactiveConfig:
    return ProactiveConfig(
        check_interval_sec=5.0,
        min_interval_sec=60.0,
        max_interval_sec=600.0,
        speak_threshold=0.3,
    )


@pytest.fixture
def mock_time_provider() -> Callable[[], float]:
    """Returns a time provider that starts at 1000.0 and increments by 1 each call."""
    t: float = 1000.0

    def _time() -> float:
        nonlocal t
        current = t
        t += 1.0
        return current

    return _time
