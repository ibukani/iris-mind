"""
Step 6 検証スクリプト — ConversationService + AgentResponseEvent
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from iris.kernel.agent_kernel import AgentKernel
from iris.kernel.agent_state import AgentStateManager
from iris.kernel.config import Config, ProactiveConfig
from iris.kernel.conversation import ConversationService
from iris.kernel.event_bus import (
    AgentResponseEvent,
    EventBus,
    UserInputEvent,
)
from iris.kernel.memory_manager import MemoryManager
from iris.kernel.proactive import ProactiveEngine
from memory.stores import EpisodicStore, SemanticStore

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        msg = f"  FAIL: {name}"
        if detail:
            msg += f" - {detail}"
        print(msg)


# ── Mock LLM ────────────────────────────────────────────


class MockLLM:
    def __init__(self) -> None:
        self.last_messages: list[dict] = []

    def chat(
        self,
        messages: list[dict],
        **_kwargs: object,
    ) -> dict:
        self.last_messages = messages
        return {
            "message": {
                "role": "assistant",
                "content": "Mock response: Hello!",
            }
        }


class MockPersonality:
    def build_system_prompt(self, **_kwargs: object) -> str:
        return "You are a test AI."


# ── Setup ────────────────────────────────────────────────

_tmpdir = Path(tempfile.mkdtemp(prefix="iris_step6_"))

event_bus = EventBus()
config = Config()
config.proactive.enabled = False  # disable proactive for testing
state = AgentStateManager(event_bus=event_bus)

episodic = EpisodicStore(
    path=str(_tmpdir / "episodes.jsonl"), max_entries=10
)
semantic = SemanticStore(
    path=str(_tmpdir / "semantic.jsonl"),
    max_entries=10,
    vector_db_path=str(_tmpdir / "chroma"),
)
memory = MemoryManager(episodic=episodic, semantic=semantic)

proactive = ProactiveEngine(
    config=config.proactive,
    event_bus=event_bus,
    state_manager=state,
    memory=memory,
)

mock_llm = MockLLM()
mock_personality = MockPersonality()

captured_responses: list[AgentResponseEvent] = []


def on_response(event: AgentResponseEvent) -> None:
    captured_responses.append(event)


# ── Test 1: ConversationService construction ────────────
print("\n=== Test 1: ConversationService construction ===")
cs = ConversationService(
    event_bus=event_bus,
    memory=memory,
    llm=mock_llm,
    personality=mock_personality,
    config=config,
)
check("conversation service created", cs is not None)
check("messages empty initially", len(cs._messages) == 0)


# ── Test 2: AgentResponseEvent event type ───────────────
print("\n=== Test 2: AgentResponseEvent event type ===")
ev = AgentResponseEvent(
    timestamp=datetime.now(),
    source="assistant",
    content="test",
)
check("event type name correct", type(ev).__name__ == "AgentResponseEvent")


# ── Test 3: ConversationService processes UserInputEvent ─
print("\n=== Test 3: ConversationService processes UserInputEvent ===")
event_bus.subscribe("AgentResponseEvent", on_response)

event_bus.publish(
    UserInputEvent(
        timestamp=datetime.now(),
        source="user_input",
        content="Hello",
    )
)

check("response event published", len(captured_responses) == 1, f"got {len(captured_responses)}")
if captured_responses:
    resp = captured_responses[0]
    check("response has content", "Mock response" in resp.content, f"got {resp.content}")
    check("response source is assistant", resp.source == "assistant")

check("user message recorded", len(cs._messages) == 2)  # user + assistant
check("assistant message content", cs._messages[1]["content"] == "Mock response: Hello!")


# ── Test 4: LLM receives system prompt + messages ──────
print("\n=== Test 4: LLM receives correct messages ===")
check("LLM got messages", len(mock_llm.last_messages) >= 1)
if mock_llm.last_messages:
    first = mock_llm.last_messages[0]
    check("first message is system", first["role"] == "system", f"got {first.get('role')}")
    check("system prompt content", "test AI" in first["content"])


# ── Test 5: AgentKernel + ConversationService integration ─
print("\n=== Test 5: AgentKernel + ConversationService integration ===")
# Create fresh EventBus/state for clean test
bus2 = EventBus()
state2 = AgentStateManager(event_bus=bus2)

kernel = AgentKernel(
    event_bus=bus2,
    state_manager=state2,
    proactive=ProactiveEngine(
        config=ProactiveConfig(enabled=False),
        event_bus=bus2,
        state_manager=state2,
        memory=memory,
    ),
    memory=memory,
    config=ProactiveConfig(),
)

episodic2 = EpisodicStore(
    path=str(_tmpdir / "episodes2.jsonl"), max_entries=10
)
semantic2 = SemanticStore(
    path=str(_tmpdir / "semantic2.jsonl"),
    max_entries=10,
    vector_db_path=str(_tmpdir / "chroma2"),
)
memory2 = MemoryManager(episodic=episodic2, semantic=semantic2)
mock_llm2 = MockLLM()

# Start kernel first, then create ConversationService
kernel.startup()

cs2 = ConversationService(
    event_bus=bus2,
    memory=memory2,
    llm=mock_llm2,
    personality=mock_personality,
    config=config,
)

response2_events: list[AgentResponseEvent] = []


def on_response2(event: AgentResponseEvent) -> None:
    response2_events.append(event)


bus2.subscribe("AgentResponseEvent", on_response2)

check("state is IDLE before input", state2.is_idle())

bus2.publish(
    UserInputEvent(
        timestamp=datetime.now(),
        source="user_input",
        content="Test integration",
    )
)

check("response received in integration test", len(response2_events) == 1, f"got {len(response2_events)}")
if response2_events:
    check("response content", "Mock response" in response2_events[0].content)

kernel.shutdown()


# ── Test 6: Reflexion integration ───────────────────────
print("\n=== Test 6: Reflexion integration ===")

class MockReflexion:
    def quick_reflect(self, _messages: list[dict]) -> dict[str, str]:
        return {
            "speech_style": "丁寧で親しみやすい",
            "expressed_traits": "好奇心旺盛",
            "user_reaction": "簡潔な回答を好む",
        }
    def reflect(self, _messages: list[dict]) -> dict[str, str]:
        return {
            "summary": "テストセッション",
            "lesson": "テストの教訓",
            "preference": "ユーザーは簡潔な回答を好む",
            "improvement": "",
            "missing_capability": "",
            "speech_style": "丁寧",
            "expressed_traits": "好奇心旺盛",
            "user_reaction": "ポジティブ",
        }

_tmp3 = Path(tempfile.mkdtemp(prefix="iris_step6_reflect_"))
episodic3 = EpisodicStore(str(_tmp3 / "episodes.jsonl"), max_entries=10)
semantic3 = SemanticStore(str(_tmp3 / "semantic.jsonl"), max_entries=10, vector_db_path=str(_tmp3 / "chroma"))
memory3 = MemoryManager(episodic=episodic3, semantic=semantic3)
bus3 = EventBus()

cs3 = ConversationService(
    event_bus=bus3,
    memory=memory3,
    llm=MockLLM(),
    personality=MockPersonality(),
    config=config,
    reflexion=MockReflexion(),
    reflect_interval=1,  # every turn
)

bus3.publish(UserInputEvent(timestamp=datetime.now(), source="user_input", content="hello"))
bus3.publish(UserInputEvent(timestamp=datetime.now(), source="user_input", content="how are you?"))

semantic_results = memory3.search_semantic("話し方", max_results=5)
check("semantic has speech_style from quick_reflect",
      any("丁寧" in r.get("content", "") for r in semantic_results))

semantic_results2 = memory3.search_semantic("性格", max_results=5)
check("semantic has traits from quick_reflect",
      any("好奇心旺盛" in r.get("content", "") for r in semantic_results2))

# Session reflect
cs3.session_reflect()
recent2 = memory3.get_recent(5)
check("session reflect stored to episodic",
      any("summary]" in r.get("summary", "") for r in recent2))


# ── Summary ─────────────────────────────────────────────
print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
if failed:
    sys.exit(1)
else:
    print("All tests passed!")
