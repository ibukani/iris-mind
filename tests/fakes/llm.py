"""Fake LLM Provider。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class FakeLLMProvider:
    def __init__(self, responses: list[Any] | None = None) -> None:
        self.call_count = 0
        from langchain_core.messages import AIMessage

        self._responses: list[Any] = responses or [AIMessage(content="Hello from FakeLLM")]
        self._messages_log: list[list[dict]] = []
        self._model_log: list[str | None] = []

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        enable_thinking: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        on_token: Callable[[str], None] | None = None,
        **kwargs: Any,
    ) -> Any:
        self._messages_log.append(messages)
        self._model_log.append(model)
        resp = self._responses[self.call_count % len(self._responses)]
        self.call_count += 1
        return resp

    def is_available(self) -> bool:
        return True

    def unload_model(self, model_name: str) -> None:
        pass


class _FakeRunnable:
    """``langmem.create_thread_extractor`` が返す ``Runnable`` の最小スタブ。"""

    def __init__(self, schema: type, response_factory: Callable[[Any, type], Any]) -> None:
        self._schema = schema
        self._response_factory = response_factory

    def invoke(self, input: Any, config: Any = None) -> Any:
        return self._response_factory(input, self._schema)


class FakeChatModelForLangMem:
    """LangMem 抽出器をテストするための LangChain 互換 ChatModel スタブ。

    ``langmem.create_thread_extractor`` は ``BaseChatModel`` ではなく
    任意のオブジェクトを ``model`` 引数に受け取れる (内部で ``init_chat_model`` をスキップ)。
    したがってテストでは ``FakeChatModelForLangMem`` のようなシンプルなダミーを渡せばよい。
    """

    def __init__(self, name: str = "fake") -> None:
        self.name = name
        self.call_count = 0
        self.last_messages: list[Any] = []
        self.responses: list[Any] = []
        self.response_index = 0

    def set_responses(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.response_index = 0

    def get_next_response(self) -> Any:
        if not self.responses:
            return None
        resp = self.responses[self.response_index % len(self.responses)]
        self.response_index += 1
        return resp

    def record(self, messages: list[Any]) -> None:
        self.call_count += 1
        self.last_messages = list(messages)


def make_fake_thread_extractor(model: FakeChatModelForLangMem, schema: type, instructions: str) -> _FakeRunnable:
    """テスト用の ``thread_extractor_factory``。``schema`` インスタンスをそのまま返す。"""

    def _factory(input: Any, schema_cls: type) -> Any:
        from langchain_core.messages import BaseMessage

        msgs = input.get("messages", []) if isinstance(input, dict) else []
        model.record([m.content for m in msgs if isinstance(m, BaseMessage)])
        return schema_cls.model_validate(model.get_next_response())

    return _FakeRunnable(schema, _factory)


__all__ = ["FakeChatModelForLangMem", "FakeLLMProvider", "_FakeRunnable", "make_fake_thread_extractor"]
