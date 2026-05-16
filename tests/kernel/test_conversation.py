from __future__ import annotations

from collections.abc import Callable

import pytest

from iris.kernel.agent_state import AgentStateManager, State
from iris.event import EventBus
from iris.io.session.manager import SessionManager
from iris.kernel.services.conversation import ConversationService
from iris.kernel.services.llm_pipeline import InterruptToken, LLMPipeline
from iris.kernel.services.response_readiness import ResponseReadinessConfig, ResponseReadinessEvaluator
from tests.conftest import FakeContextManager, FakeReflexion, FakeSessionInfo, FakeSessionManager


class FakeLLMPipeline:
    def __init__(self, response: str = "Hello from fake LLM") -> None:
        self.call_count = 0
        self._response = response
        self._interrupt_token: InterruptToken | None = None

    def iterate_with_tools(
        self,
        messages: list[dict],
        on_token: Callable[[str], None] | None = None,
        interrupt_token: InterruptToken | None = None,
        **kwargs: dict,
    ) -> str:
        self.call_count += 1
        self._interrupt_token = interrupt_token
        if on_token:
            on_token(self._response)
        return self._response

    def set_session_roles_summary(self, summary: str) -> None:
        pass


@pytest.fixture
def session_mgr() -> FakeSessionManager:
    mgr = FakeSessionManager()
    mgr.set_session_info(FakeSessionInfo(session_id="s1", roles=[]))
    return mgr


@pytest.fixture
def llm_pipeline() -> FakeLLMPipeline:
    return FakeLLMPipeline()


@pytest.fixture
def state_manager() -> AgentStateManager:
    return AgentStateManager(event_bus=EventBus())


@pytest.fixture
def conversation(session_mgr: FakeSessionManager, llm_pipeline: FakeLLMPipeline, state_manager: AgentStateManager) -> ConversationService:
    return ConversationService(
        session_manager=session_mgr,
        llm_pipeline=llm_pipeline,
        state_manager=state_manager,
        reflexion_manager=None,
        context_manager=None,
        quasi_timeout_ms=100,
        quasi_max_fragments=3,
    )


class TestProcessInput:
    def test_basic_input_flow(self, conversation: ConversationService, session_mgr: FakeSessionManager, llm_pipeline: FakeLLMPipeline) -> None:
        conversation.process_input("s1", "hello")
        assert llm_pipeline.call_count == 1
        assert any("hello" in m["content"] for m in conversation._messages)

    def test_sends_stream_and_response(self, conversation: ConversationService, session_mgr: FakeSessionManager, llm_pipeline: FakeLLMPipeline) -> None:
        conversation.process_input("s1", "hello")
        assert len(session_mgr.sent) >= 2
        assert any(m.msg_type == "stream" for m in session_mgr.sent)
        assert any(m.msg_type == "response" for m in session_mgr.sent)

    def test_on_complete_callback(self, conversation: ConversationService, llm_pipeline: FakeLLMPipeline) -> None:
        results: list[str] = []
        conversation.process_input("s1", "hello", on_complete=lambda text: results.append(text))
        assert results == ["Hello from fake LLM"]

    def test_slash_command_skipped(self, conversation: ConversationService, llm_pipeline: FakeLLMPipeline) -> None:
        conversation.process_input("s1", "/help")
        assert llm_pipeline.call_count == 0

    def test_messages_accumulate(self, conversation: ConversationService, llm_pipeline: FakeLLMPipeline) -> None:
        conversation.process_input("s1", "first")
        conversation.process_input("s1", "second")
        assert len(conversation._messages) == 4
        assert "first" in conversation._messages[0]["content"]
        assert "second" in conversation._messages[2]["content"]


class TestProcessQuasiInput:
    def test_single_final_fragment_flushes_immediately(self, conversation: ConversationService, session_mgr: FakeSessionManager, llm_pipeline: FakeLLMPipeline) -> None:
        conversation.process_quasi_input("s1", "hello world", is_final=True)
        assert llm_pipeline.call_count == 1

    def test_fragments_accumulate_until_final(self, conversation: ConversationService, llm_pipeline: FakeLLMPipeline) -> None:
        conversation.process_quasi_input("s1", "hello ", is_final=False)
        assert llm_pipeline.call_count == 0
        conversation.process_quasi_input("s1", "world", is_final=True)
        assert llm_pipeline.call_count == 1

    def test_max_fragments_flushes(self, conversation: ConversationService, llm_pipeline: FakeLLMPipeline) -> None:
        conversation.process_quasi_input("s1", "a", is_final=False)
        conversation.process_quasi_input("s1", "b", is_final=False)
        conversation.process_quasi_input("s1", "c", is_final=False)
        assert llm_pipeline.call_count == 1

    def test_new_input_interrupts_processing(self, conversation: ConversationService, session_mgr: FakeSessionManager, llm_pipeline: FakeLLMPipeline) -> None:
        conversation.process_quasi_input("s1", "first message", is_final=True)
        assert llm_pipeline.call_count == 1
        old_token = conversation._interrupt_token
        conversation.process_quasi_input("s1", "interrupt!", is_final=True)
        assert old_token is None or old_token.is_cancelled

    def test_stream_has_state_passthrough(self, conversation: ConversationService, session_mgr: FakeSessionManager, llm_pipeline: FakeLLMPipeline) -> None:
        conversation.process_quasi_input("s1", "hello", is_final=True)
        stream_msgs = [m for m in session_mgr.sent if m.msg_type == "stream"]
        assert any(m.state == "thinking" for m in stream_msgs)
        assert any(m.state == "speaking" for m in stream_msgs)
        assert any(m.state == "done" for m in stream_msgs)

    def test_empty_fragment_does_not_flush(self, conversation: ConversationService, llm_pipeline: FakeLLMPipeline) -> None:
        conversation.process_quasi_input("s1", "", is_final=True)
        assert llm_pipeline.call_count == 0


class TestStateIntegration:
    def test_idle_to_listening_on_first_fragment(self, conversation: ConversationService, state_manager: AgentStateManager) -> None:
        assert state_manager.is_idle()
        conversation.process_quasi_input("s1", "hello", is_final=False)
        assert state_manager.is_listening()

    def test_listening_to_processing_on_flush(self, conversation: ConversationService, state_manager: AgentStateManager) -> None:
        conversation.process_quasi_input("s1", "hello", is_final=False)
        assert state_manager.is_listening()
        conversation.process_quasi_input("s1", " world", is_final=True)
        assert state_manager.is_processing()

    def test_processing_to_idle_on_complete(self, conversation: ConversationService, state_manager: AgentStateManager, llm_pipeline: FakeLLMPipeline) -> None:
        conversation.process_quasi_input("s1", "hello", is_final=True)
        assert state_manager.is_processing() or state_manager.is_idle()

    def test_interrupt_during_processing(self, conversation: ConversationService, state_manager: AgentStateManager) -> None:
        conversation.process_quasi_input("s1", "hello", is_final=True)
        conversation.interrupt("s1")
        assert state_manager.is_idle()

    def test_listening_timeout_returns_to_idle(self, conversation: ConversationService, state_manager: AgentStateManager, llm_pipeline: FakeLLMPipeline) -> None:
        conversation.process_quasi_input("s1", "hello", is_final=False)
        assert state_manager.is_listening()
        conversation._on_quasi_flush("s1", "")
        assert state_manager.is_idle()


class TestInterrupt:
    def test_interrupt_cancels_token(self, conversation: ConversationService, llm_pipeline: FakeLLMPipeline) -> None:
        conversation.process_quasi_input("s1", "hello", is_final=True)
        token = conversation._interrupt_token
        assert token is not None
        conversation.interrupt("s1")
        assert token.is_cancelled

    def test_interrupt_sends_interrupted_state(self, conversation: ConversationService, session_mgr: FakeSessionManager) -> None:
        conversation.process_quasi_input("s1", "hello", is_final=True)
        conversation.interrupt("s1")
        stream_msgs = [m for m in session_mgr.sent if m.msg_type == "stream"]
        assert any(m.state == "interrupted" for m in stream_msgs)

    def test_interrupt_cancels_buffer(self, conversation: ConversationService) -> None:
        conversation.process_quasi_input("s1", "hello", is_final=False)
        conversation.interrupt("s1")
        assert conversation._quasi.fragment_count == 0
