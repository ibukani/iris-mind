from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from core.llm_bridge import LLMBridge
    from capabilities.registry import CapabilityRegistry
    from core.personality import Personality
    from core.reflexion import Reflexion
    from core.planner import Planner
    from core.executor import Executor
    from core.context import ContextManager
    from memory.stores import AgentsMdStore, EpisodicStore, SemanticStore
    from memory.persona_profile import PersonaProfile

from core.constants import (
    CLASSIFY_PROMPT, SCENARIOS,
    GREETING_WORDS, ENDING_WORDS, TOOL_HINTS, COMPLEX_TRIGGERS,
)
from core.tool_executor import ToolExecutionEngine

_RAG_EXECUTOR = ThreadPoolExecutor(max_workers=1)
_SHORT_GREET_TOKENS = 64


@dataclass
class ProcessResult:
    response_message: dict
    thinking_mode: bool = False
    plan_mode: bool = False
    active_model: str = ""
    msg_count_since_reflect: int = 0


def _detect_complex(user_input: str) -> bool:
    return any(t in user_input.lower() for t in COMPLEX_TRIGGERS)


def _quick_classify(user_input: str, messages: list[dict] | None = None) -> str | None:
    lower = user_input.lower().strip()
    words = set(lower.split())
    is_short = len(lower) <= 15

    if is_short and any(e in lower for e in ENDING_WORDS):
        return "ending"

    if is_short:
        if words & GREETING_WORDS:
            return "greeting"
        if any(g in lower for g in GREETING_WORDS):
            return "greeting"

    if messages and len(messages) >= 2:
        prev = messages[-2].get("content", "").lower()
        if any(e in prev for e in ENDING_WORDS):
            return "ending"

    if any(h in lower for h in TOOL_HINTS):
        return "tool"
    if _detect_complex(user_input):
        return "complex"
    return None


def _classify_input(llm: LLMBridge, user_input: str, fast_model: str) -> str:
    try:
        resp = llm.chat(
            messages=[{"role": "user",
                       "content": CLASSIFY_PROMPT.format(input=user_input)}],
            model=fast_model,
            temperature=0,
            max_tokens=10,
        )
        raw = resp["message"].get("content", "").strip().lower()
        return raw if raw in SCENARIOS else "simple"
    except Exception:
        return "simple"


class ConversationService:
    """会話オーケストレーション。

    入力分類・モデル選択・RAG・コンテキスト構築・応答生成・
    Tool Call実行・Reflection を統括する。
    CliSession はこの結果を受け取り表示のみを行う。
    """

    def __init__(
        self,
        llm: LLMBridge,
        registry: CapabilityRegistry,
        personality: Personality,
        agents_md: AgentsMdStore,
        episodic: EpisodicStore,
        semantic: SemanticStore,
        persona_profile: PersonaProfile,
        reflexion: Reflexion,
        planner: Planner,
        executor: Executor,
        context_manager: ContextManager,
        smart_model: str,
        fast_model: str | None,
        temperature: float,
        max_tokens: int,
        max_tokens_fast: int,
        context_window: int = 0,
        compaction_threshold: float = 0.85,
        rag_max_results: int = 3,
    ):
        self.llm = llm
        self.registry = registry
        self.personality = personality
        self.agents_md = agents_md
        self.episodic = episodic
        self.semantic = semantic
        self.persona_profile = persona_profile
        self.reflexion = reflexion
        self.planner = planner
        self.executor = executor
        self.context_manager = context_manager
        self.smart_model = smart_model
        self.fast_model = fast_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_tokens_fast = max_tokens_fast
        self.context_window = context_window
        self.compaction_threshold = compaction_threshold
        self.rag_max_results = rag_max_results

    def process_input(
        self,
        user_input: str,
        messages: list[dict],
        thinking_mode: bool,
        plan_mode: bool,
        active_model: str,
        msg_count_since_reflect: int,
        on_token: Callable[[str], None] | None = None,
    ) -> ProcessResult:
        has_fast = self.fast_model is not None
        category = _quick_classify(user_input)
        if category is None and has_fast:
            category = _classify_input(self.llm, user_input, self.fast_model)
        scenario = category or "simple"
        use_fast, scenario_max_tokens = SCENARIOS.get(scenario, (True, 256))

        force_smart = plan_mode or thinking_mode
        if force_smart or not use_fast or not has_fast:
            use_fast = False
            self.llm.set_model(self.smart_model)
            active_model = self.smart_model
            max_tokens = self.max_tokens
            tools_list = self.registry.list_tools()
        else:
            self.llm.set_model(self.fast_model)
            active_model = self.fast_model
            max_tokens = min(self.max_tokens_fast, scenario_max_tokens)
            tools_list = None

        _conversation_summary = self.context_manager.check_and_summarize(
            messages,
            context_window=self.context_window,
            threshold=self.compaction_threshold,
        )

        _pref_results = self.semantic.search("ユーザーの好み user preference", max_results=3)
        _pref_text = "\n".join(f"- {p['content'][:120]}" for p in _pref_results) if _pref_results else ""
        system_prompt = self.personality.build_system_prompt(
            agents_md_content=self.agents_md.load(),
            speech_style=self.persona_profile.get_speech_style(),
            personality_traits=self.persona_profile.get_traits(),
            user_preferences=_pref_text,
            conversation_summary=_conversation_summary,
        )

        recent_episodes = self.episodic.get_recent(3)
        if recent_episodes:
            system_prompt += "\n\n## Recent Sessions\n" + "\n".join(f"- {e}" for e in recent_episodes)

        if thinking_mode:
            messages[-1] = messages[-1].copy()
            messages[-1]["content"] = self.personality.build_thinking_prompt(user_input)

        should_plan = False
        plan_result = None
        if not use_fast and (plan_mode or (thinking_mode and _detect_complex(user_input))):
            rag_future = _RAG_EXECUTOR.submit(self.semantic.search, user_input, max_results=self.rag_max_results)
            plan_result = self.planner.analyze(user_input, system_prompt[:300])
            _rag_results = rag_future.result()
            if _rag_results:
                system_prompt += "\n\n## Related Lessons\n" + "\n".join(f"- {e['content']}" for e in _rag_results)
            if not plan_mode:
                should_plan = self.planner.is_complex(plan_result)

        if not use_fast and not plan_mode and not thinking_mode and user_input.strip().lower() in (
            "hello", "hi", "bye", "thanks", "ありがとう"):
            max_tokens = _SHORT_GREET_TOKENS

        if should_plan:
            subtasks = plan_result.get("subtasks", [])
            final_content = self.executor.execute_plan(
                plan_result, user_input, self.personality.name,
            )
            msg = {"role": "assistant", "content": final_content}
            messages.append(msg)
        else:
            if not use_fast:
                rag_future = _RAG_EXECUTOR.submit(self.semantic.search, user_input, max_results=self.rag_max_results)
                _rag_results = rag_future.result()
                if _rag_results:
                    system_prompt += "\n\n## Related Lessons\n" + "\n".join(f"- {e['content']}" for e in _rag_results)

            response = self.llm.chat(
                messages=[{"role": "system", "content": system_prompt}, *messages],
                enable_thinking=thinking_mode,
                temperature=self.temperature,
                max_tokens=max_tokens,
                tools=tools_list,
                on_token=on_token if not use_fast else None,
            )

            msg = response["message"]
            messages.append(msg)

            if msg.get("tool_calls"):
                tool_engine = ToolExecutionEngine(self.llm, self.registry)
                ctx = messages[:]
                tool_results = tool_engine.execute_all(ctx)

                if not tool_engine.should_follow_up(tool_results):
                    combined = "\n\n".join(
                        f"**{name}** result:\n{res}" for name, res in tool_results
                    )
                    msg = {"role": "assistant", "content": combined}
                    messages.extend(ctx[len(messages):])
                    messages.append(msg)
                else:
                    messages.extend(ctx[len(messages):])
                    final = self.llm.chat(
                        messages=[{"role": "system", "content": system_prompt}, *messages],
                        enable_thinking=thinking_mode,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        on_token=on_token,
                    )
                    msg = final["message"]
                    messages.append(msg)

        msg_count_since_reflect += 1
        if msg_count_since_reflect >= 5:
            msg_count_since_reflect = 0
            try:
                slice_for_reflect = messages[-8:] if len(messages) >= 8 else messages
                result = self.reflexion.quick_reflect(slice_for_reflect)
                if result.get("speech_style") or result.get("expressed_traits"):
                    self.persona_profile.update_from_reflection(result)
            except Exception:
                pass

        return ProcessResult(
            response_message=msg,
            thinking_mode=thinking_mode,
            plan_mode=plan_mode,
            active_model=active_model,
            msg_count_since_reflect=msg_count_since_reflect,
        )
