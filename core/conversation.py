from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from capabilities.registry import CapabilityRegistry
    from core.context import ContextManager
    from core.executor import Executor
    from core.llm_bridge import LLMBridge
    from core.personality import Personality
    from core.planner import Planner
    from core.reflexion import Reflexion
    from memory.persona_profile import PersonaProfile
    from memory.stores import AgentsMdStore, EpisodicStore, SemanticStore

from core.constants import (
    CLASSIFY_PROMPT,
    COMPLEX_TRIGGERS,
    ENDING_WORDS,
    GREETING_WORDS,
    SCENARIOS,
    TOOL_HINTS,
)
from core.tool_executor import ToolExecutionEngine

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
            messages=[{"role": "user", "content": CLASSIFY_PROMPT.format(input=user_input)}],
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

    # ── 内部メソッド（責務ごとに分割） ──────────────────────

    def _classify_scenario(self, user_input: str) -> str:
        """2段階分類: キーワード → LLM fallback"""
        category = _quick_classify(user_input)
        if category is None and self.fast_model is not None:
            category = _classify_input(self.llm, user_input, self.fast_model)
        return category or "simple"

    def _resolve_model_params(
        self,
        scenario: str,
        thinking_mode: bool,
        plan_mode: bool,
    ) -> tuple[str, int, list[dict] | None]:
        """使用モデル・トークン上限・ツールリストを決定する（副作用なし）。"""
        has_fast = self.fast_model is not None
        use_fast, scenario_max_tokens = SCENARIOS.get(scenario, (True, 256))
        force_smart = plan_mode or thinking_mode

        if force_smart or not use_fast or not has_fast:
            return self.smart_model, self.max_tokens, self.registry.list_tools()
        assert self.fast_model is not None  # has_fast=True で保証
        return self.fast_model, min(self.max_tokens_fast, scenario_max_tokens), None

    def _build_system_prompt(
        self,
        conversation_summary: str,
        rag_results: list[dict],
        user_input: str,
    ) -> str:
        """システムプロンプトを構築（ペルソナ・記憶・RAGを統合）。"""
        pref_results = self.semantic.search("ユーザーの好み user preference", max_results=3)
        pref_text = "\n".join(f"- {p['content'][:120]}" for p in pref_results) if pref_results else ""

        system_prompt = self.personality.build_system_prompt(
            agents_md_content=self.agents_md.load(),
            speech_style=self.persona_profile.get_speech_style(),
            personality_traits=self.persona_profile.get_traits(),
            user_preferences=pref_text,
            conversation_summary=conversation_summary,
        )

        recent_episodes = self.episodic.get_recent(3)
        if recent_episodes:
            system_prompt += "\n\n## Recent Sessions\n" + "\n".join(f"- {e}" for e in recent_episodes)

        if rag_results:
            system_prompt += "\n\n## Related Lessons\n" + "\n".join(f"- {e['content']}" for e in rag_results)

        return system_prompt

    def _retrieve_rag(self, user_input: str) -> list[dict]:
        """意味記憶から関連エントリを検索して返す。"""
        try:
            return self.semantic.search(user_input, max_results=self.rag_max_results)
        except Exception:
            return []

    def _handle_plan(
        self,
        plan_result: dict,
        user_input: str,
    ) -> dict:
        """Plan-and-Execute でサブタスクを実行し、最終メッセージを返す。"""
        final_content = self.executor.execute_plan(
            plan_result,
            user_input,
            self.personality.name,
        )
        return {"role": "assistant", "content": final_content}

    def _handle_direct_response(
        self,
        system_prompt: str,
        messages: list[dict],
        thinking_mode: bool,
        tools_list: list[dict] | None,
        max_tokens: int,
        on_token: Callable[[str], None] | None,
        active_model: str,
    ) -> dict:
        """LLM呼び出し→Tool Call実行→フォローアップまでを一貫処理して最終メッセージを返す。"""
        response = self.llm.chat(
            messages=[{"role": "system", "content": system_prompt}, *messages],
            model=active_model,
            enable_thinking=thinking_mode,
            temperature=self.temperature,
            max_tokens=max_tokens,
            tools=tools_list,
            on_token=on_token,
        )

        msg = response["message"]
        messages.append(msg)

        if msg.get("tool_calls"):
            msg = self._execute_tool_calls(msg, system_prompt, messages, thinking_mode, on_token, active_model)

        return msg

    def _execute_tool_calls(
        self,
        msg: dict,
        system_prompt: str,
        messages: list[dict],
        thinking_mode: bool,
        on_token: Callable[[str], None] | None,
        active_model: str,
    ) -> dict:
        """Tool Callを実行し、必要に応じてフォローアップLLM呼び出しを行う。"""
        tool_engine = ToolExecutionEngine(self.llm, self.registry)
        ctx = messages[:]
        tool_results = tool_engine.execute_all(ctx)

        if not tool_engine.should_follow_up(tool_results):
            combined = "\n\n".join(f"**{name}** result:\n{res}" for name, res in tool_results)
            messages.extend(ctx[len(messages) :])
            return {"role": "assistant", "content": combined}

        messages.extend(ctx[len(messages) :])
        final = self.llm.chat(
            messages=[{"role": "system", "content": system_prompt}, *messages],
            model=active_model,
            enable_thinking=thinking_mode,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            on_token=on_token,
        )
        return final["message"]

    def _run_quick_reflection(self, messages: list[dict], count: int) -> int:
        """5メッセージごとに quick_reflect を実行。"""
        count += 1
        if count < 5:
            return count
        try:
            slice_for_reflect = messages[-8:] if len(messages) >= 8 else messages
            result = self.reflexion.quick_reflect(slice_for_reflect)
            if result.get("speech_style") or result.get("expressed_traits"):
                self.persona_profile.update_from_reflection(result)
        except Exception:
            pass
        return 0

    # ── 公開API ────────────────────────────────────────────

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
        # Phase 1: 入力分類
        scenario = self._classify_scenario(user_input)

        # Phase 2: モデル選択（set_model副作用なし、model名を直接返す）
        active_model, max_tokens, tools_list = self._resolve_model_params(
            scenario,
            thinking_mode,
            plan_mode,
        )
        use_fast = active_model == self.fast_model

        # Phase 3: コンテキスト圧縮判定
        conversation_summary = self.context_manager.check_and_summarize(
            messages,
            context_window=self.context_window,
            threshold=self.compaction_threshold,
        )

        # Phase 4: RAG取得（Plan/非Plan共通、1度だけ）
        rag_results = self._retrieve_rag(user_input) if not use_fast else []

        # Phase 5: システムプロンプト構築
        system_prompt = self._build_system_prompt(
            conversation_summary,
            rag_results,
            user_input,
        )

        # Phase 6: Plan判定
        should_plan = False
        plan_result = None
        if not use_fast and (plan_mode or (thinking_mode and _detect_complex(user_input))):
            plan_result = self.planner.analyze(user_input, system_prompt[:300])
            should_plan = self.planner.is_complex(plan_result) if not plan_mode else True

        # Phase 7: 思考モードでユーザー入力をラップ
        if thinking_mode:
            messages[-1] = messages[-1].copy()
            messages[-1]["content"] = self.personality.build_thinking_prompt(user_input)

        # Phase 8: 簡易グリーティング抑制
        if (
            not use_fast
            and not plan_mode
            and not thinking_mode
            and user_input.strip().lower() in ("hello", "hi", "bye", "thanks", "ありがとう")
        ):
            max_tokens = _SHORT_GREET_TOKENS

        # Phase 9: 応答生成
        if should_plan:
            assert plan_result is not None
            msg = self._handle_plan(plan_result, user_input)
        else:
            msg = self._handle_direct_response(
                system_prompt,
                messages,
                thinking_mode,
                tools_list,
                max_tokens,
                on_token,
                active_model,
            )

        messages.append(msg)

        # Phase 10: Quick Reflection
        msg_count_since_reflect = self._run_quick_reflection(messages, msg_count_since_reflect)

        return ProcessResult(
            response_message=msg,
            thinking_mode=thinking_mode,
            plan_mode=plan_mode,
            active_model=active_model,
            msg_count_since_reflect=msg_count_since_reflect,
        )
