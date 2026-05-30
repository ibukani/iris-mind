from __future__ import annotations

from dataclasses import dataclass


class HookPriority:
    SYSTEM = range(100)
    CORE = range(100, 1000)
    FEATURE = range(1000, 5000)
    USER = range(5000, 10000)


@dataclass(frozen=True)
class HookPoint:
    name: str
    description: str


HOOK_POINTS: dict[str, HookPoint] = {
    "llm.before_chat": HookPoint("llm.before_chat", "LLM呼出前"),
    "llm.after_chat": HookPoint("llm.after_chat", "LLM応答後"),
    "llm.before_stream": HookPoint("llm.before_stream", "ストリーム開始時"),
    "memory.before_store": HookPoint("memory.before_store", "記憶保存前"),
    "memory.after_search": HookPoint("memory.after_search", "記憶検索後"),
    "agency.plan_decided": HookPoint("agency.plan_decided", "計画決定時"),
    "agency.before_exec": HookPoint("agency.before_exec", "実行前"),
    "io.before_send": HookPoint("io.before_send", "送信前"),
    "io.after_receive": HookPoint("io.after_receive", "受信後"),
    "io.dispatch": HookPoint("io.dispatch", "IO受信メッセージのディスパッチ"),
}
