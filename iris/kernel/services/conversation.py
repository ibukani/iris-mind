from __future__ import annotations

import logging
from collections.abc import Callable

from iris.kernel.io.models import OutputMessage
from iris.kernel.io.session_manager import SessionManager

from .context import ContextManager
from .llm_pipeline import LLMPipeline
from .reflexion_manager import ReflexionManager

logger = logging.getLogger(__name__)


class ConversationService:
    def __init__(
        self,
        session_manager: SessionManager,
        llm_pipeline: LLMPipeline,
        reflexion_manager: ReflexionManager | None = None,
        context_manager: ContextManager | None = None,
        context_window: int = 0,
    ) -> None:
        self._session_mgr = session_manager
        self._llm_pipeline = llm_pipeline
        self._reflexion_manager = reflexion_manager
        self._context_manager = context_manager
        self._context_window = context_window
        self._messages: list[dict] = []
        self._msg_count_since_reflect: int = 0

    def process_input(self, session_id: str, content: str, on_complete: Callable[[str], None] | None = None) -> None:
        if content.startswith("/"):
            return
        self._messages.append({"role": "user", "content": content})

        self._session_mgr.route_output(
            session_id,
            OutputMessage(msg_type="stream", content=""),
        )

        self._llm_pipeline.set_session_roles_summary(
            self._session_mgr.get_roles_summary(),
        )

        try:
            response_text = self._llm_pipeline.iterate_with_tools(
                self._messages,
                on_token=lambda delta: self._session_mgr.route_output(
                    session_id,
                    OutputMessage(msg_type="stream", content=delta),
                ),
            )
        except Exception as e:
            response_text = f"[Error: {e}]"
            logger.exception("LLM call failed")

        self._messages.append({"role": "assistant", "content": response_text})

        self._session_mgr.route_output(session_id, OutputMessage(msg_type="stream", content="", metadata={"done": True}))
        self._session_mgr.route_output(session_id, OutputMessage(msg_type="response", content=response_text))

        if on_complete is not None:
            on_complete(response_text)

        self._msg_count_since_reflect += 1
        self._maybe_quick_reflect()
        self._maybe_compact()

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
