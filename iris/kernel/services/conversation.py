from __future__ import annotations

import logging
from collections.abc import Callable

from iris.kernel.agent_state import AgentStateManager, State
from iris.kernel.io.input_buffer import InputBuffer
from iris.kernel.io.models import OutputMessage
from iris.kernel.io.session_manager import SessionManager

from .context import ContextManager
from .llm_pipeline import InterruptToken, LLMPipeline
from .reflexion_manager import ReflexionManager
from .response_readiness import ResponseReadinessEvaluator, ResponseReadinessConfig

logger = logging.getLogger(__name__)


class ConversationService:
    def __init__(
        self,
        session_manager: SessionManager,
        llm_pipeline: LLMPipeline,
        state_manager: AgentStateManager | None = None,
        reflexion_manager: ReflexionManager | None = None,
        context_manager: ContextManager | None = None,
        context_window: int = 0,
        quasi_timeout_ms: int = 800,
        quasi_max_fragments: int = 10,
        readiness_config: ResponseReadinessConfig | None = None,
        readiness_evaluator: ResponseReadinessEvaluator | None = None,
    ) -> None:
        self._session_mgr = session_manager
        self._llm_pipeline = llm_pipeline
        self._state_mgr = state_manager
        self._reflexion_manager = reflexion_manager
        self._context_manager = context_manager
        self._context_window = context_window
        self._messages: list[dict] = []
        self._msg_count_since_reflect: int = 0

        self._interrupt_token: InterruptToken | None = None
        self._quasi = InputBuffer(
            session_id="",
            timeout_ms=quasi_timeout_ms,
            max_fragments=quasi_max_fragments,
        )
        self._quasi.set_flush_callback(self._on_quasi_flush)
        self._readiness = readiness_evaluator
    def process_input(self, session_id: str, content: str, on_complete: Callable[[str], None] | None = None) -> None:
        if content.startswith("/"):
            return

        info = self._session_mgr.get_session_info(session_id)
        if info:
            roles_str = ", ".join(r.value for r in info.roles)
            tagged = f"[session: {session_id}, roles: {roles_str}] {content}"
        else:
            tagged = content
        self._messages.append({"role": "user", "content": tagged})

        self._send_stream(session_id, "")

        self._llm_pipeline.set_session_roles_summary(
            self._session_mgr.get_roles_summary(),
        )

        try:
            token = InterruptToken()
            self._interrupt_token = token
            response_text = self._llm_pipeline.iterate_with_tools(
                self._messages,
                on_token=lambda delta: self._send_stream(session_id, delta),
                interrupt_token=token,
            )
        except Exception as e:
            response_text = f"[Error: {e}]"
            logger.exception("LLM call failed")
        finally:
            self._interrupt_token = None

        self._messages.append({"role": "assistant", "content": response_text})

        self._send_stream(session_id, "", done=True)
        self._send_response(session_id, response_text)

        if on_complete is not None:
            on_complete(response_text)

        self._msg_count_since_reflect += 1
        self._maybe_quick_reflect()
        self._maybe_compact()

    def process_quasi_input(self, session_id: str, content: str, is_final: bool = True) -> None:
        self._interrupt_if_processing(session_id)
        if self._state_mgr and self._state_mgr.is_idle():
            self._state_mgr.transition(State.LISTENING)
        self._quasi.session_id = session_id
        self._quasi.add_fragment(content, is_final)

    def interrupt(self, session_id: str) -> None:
        self._interrupt_if_processing(session_id)
        self._quasi.cancel()
        if self._state_mgr and (self._state_mgr.is_listening() or self._state_mgr.is_processing()):
            self._state_mgr.transition(State.INTERRUPTED)
            self._state_mgr.transition(State.IDLE)

    def _interrupt_if_processing(self, session_id: str) -> None:
        token = self._interrupt_token
        if token is not None:
            token.cancel()
            self._interrupt_token = None
            self._send_stream(session_id, "", state="interrupted")

    def _on_quasi_flush(self, session_id: str, content: str) -> None:
        if not content:
            if self._state_mgr and self._state_mgr.is_listening():
                self._state_mgr.transition(State.IDLE)
            return

        if self._state_mgr:
            self._state_mgr.transition(State.PROCESSING)

        info = self._session_mgr.get_session_info(session_id)
        if info:
            roles_str = ", ".join(r.value for r in info.roles)
            tagged = f"[session: {session_id}, roles: {roles_str}] {content}"
        else:
            tagged = content
        self._messages.append({"role": "user", "content": tagged})

        self._send_stream(session_id, "", state="thinking")

        self._llm_pipeline.set_session_roles_summary(
            self._session_mgr.get_roles_summary(),
        )

        try:
            token = InterruptToken()
            self._interrupt_token = token
            response_text = self._llm_pipeline.iterate_with_tools(
                self._messages,
                on_token=lambda delta: self._send_stream(session_id, delta, state="speaking"),
                interrupt_token=token,
            )
        except Exception as e:
            response_text = f"[Error: {e}]"
            logger.exception("LLM call failed")
        finally:
            self._interrupt_token = None

        self._messages.append({"role": "assistant", "content": response_text})

        self._send_stream(session_id, "", state="done")
        self._send_response(session_id, response_text)

        if self._state_mgr and self._state_mgr.is_processing():
            self._state_mgr.transition(State.IDLE)

        self._msg_count_since_reflect += 1
        self._maybe_quick_reflect()
        self._maybe_compact()

    def _send_stream(
        self,
        session_id: str,
        content: str,
        state: str | None = None,
        done: bool = False,
    ) -> None:
        meta: dict = {}
        if done:
            meta["done"] = True
        self._session_mgr.route_output(
            session_id,
            OutputMessage(msg_type="stream", content=content, state=state, metadata=meta),
        )

    def _send_response(self, session_id: str, content: str) -> None:
        self._session_mgr.route_output(
            session_id,
            OutputMessage(msg_type="response", content=content),
        )

    def _maybe_quick_reflect(self) -> None:
        if self._reflexion_manager is None:
            return
        self._msg_count_since_reflect = self._reflexion_manager.maybe_run(
            self._messages,
            self._msg_count_since_reflect,
        )

    def session_reflect(self) -> None:
        if self._reflexion_manager is None:
            return
        self._reflexion_manager.run_session(self._messages)

    def _maybe_compact(self) -> None:
        if self._context_manager is None or self._context_window <= 0:
            return
        self._context_manager.check_and_summarize(
            self._messages,
            context_window=self._context_window,
        )

    def force_compact(self) -> None:
        if self._context_manager is None or len(self._messages) < 2:
            return
        self._context_manager.force_summarize(self._messages)
        logger.info("Conversation force compacted")

    def clear_history(self) -> None:
        self._messages.clear()
        self._msg_count_since_reflect = 0
        if self._context_manager is not None:
            self._context_manager.clear()
        logger.info("Conversation history cleared")
