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

from core.config import EscalationConfig, ModelEntry
from core.constants import (
    COMPLEX_TRIGGERS,
    COMPLEXITY_HIGH_THRESHOLD,
    COMPLEXITY_LOW_THRESHOLD,
    ENDING_WORDS,
    GREETING_WORDS,
    SHORT_GREET_TOKENS,
    TOOL_HINTS,
    Complexity,
)
from core.tool_executor import ToolExecutionEngine


@dataclass
class ProcessResult:
    response_message: dict
    thinking_mode: bool = False
    plan_mode: bool = False
    active_model: str = ""
    active_role: str = ""
    msg_count_since_reflect: int = 0
    escalated: bool = False


# ── 複雑性判定 ────────────────────────────────────────────


def _compute_complexity_score(
    user_input: str,
    last_role: str | None = None,
) -> int:
    lower = user_input.lower().strip()
    score = 0

    # Greeting / short ending → minimum score
    if len(lower) <= 15:
        if any(e in lower for e in ENDING_WORDS):
            return 0
        words = set(lower.split())
        if words & GREETING_WORDS:
            return 0

    # Length-based
    if len(user_input) > 150:
        score += 1
    if len(user_input) > 500:
        score += 2

    # Multiple sentences
    sentences = user_input.count(".") + user_input.count("!") + user_input.count("？")
    if sentences >= 2:
        score += 1
    if sentences >= 5:
        score += 1

    # Code blocks
    if "```" in user_input:
        score += 2
    elif "`" in user_input:
        score += 1

    # Tool hints
    if any(h in lower for h in TOOL_HINTS):
        score += 1

    # Multi-step triggers
    if any(t in lower for t in COMPLEX_TRIGGERS):
        score += 1

    # Multiple questions
    if user_input.count("?") > 2:
        score += 1

    # Context: previous turn used smart → stay conservative
    if last_role == "smart":
        score += 1

    return score


def _assess_complexity(user_input: str, last_role: str | None = None) -> Complexity:
    """ヒューリスティックスコアリングで複雑性を判定する。"""
    score = _compute_complexity_score(user_input, last_role)
    if score >= COMPLEXITY_HIGH_THRESHOLD:
        return Complexity.HIGH
    if score < COMPLEXITY_LOW_THRESHOLD:
        return Complexity.LOW
    return Complexity.MEDIUM


# ── ConversationService ────────────────────────────────────


class ConversationService:
    """会話オーケストレーション。

    複雑性判定・モデル選択・RAG・コンテキスト構築・応答生成・
    Tool Call実行・エスカレーション・Reflection を統括する。
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
        models: list[ModelEntry],
        escalation_config: EscalationConfig,
        temperature: float,
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
        self.models = models
        self.escalation_config = escalation_config
        self.temperature = temperature
        self.context_window = context_window
        self.compaction_threshold = compaction_threshold
        self.rag_max_results = rag_max_results

        self.models_by_role: dict[str, ModelEntry] = {m.role: m for m in models}

    # ── モデル選択 ──────────────────────────────────────────

    def _select_model_and_tools(
        self,
        complexity: Complexity,
        thinking_mode: bool,
        plan_mode: bool,
    ) -> tuple[str, str, int, list[dict] | None]:
        """(model_name, role, max_tokens, tools_list) を返す。副作用なし。"""
        force_smart = thinking_mode or plan_mode

        if force_smart or complexity == Complexity.HIGH:
            entry = self.models_by_role["smart"]
            return entry.name, entry.role, entry.max_tokens, self.registry.list_tools()

        entry = self.models_by_role["base"]
        tools = self.registry.list_tools_for_role(entry.role) if complexity != Complexity.LOW else None
        return entry.name, entry.role, entry.max_tokens, tools

    # ── システムプロンプト構築 ──────────────────────────────

    def _build_system_prompt(
        self,
        conversation_summary: str,
        rag_results: list[dict],
        user_input: str,
    ) -> str:
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

    # ── RAG ─────────────────────────────────────────────────

    def _retrieve_rag(self, user_input: str) -> list[dict]:
        try:
            return self.semantic.search(user_input, max_results=self.rag_max_results)
        except Exception:
            return []

    # ── Plan ────────────────────────────────────────────────

    def _handle_plan(
        self,
        plan_result: dict,
        user_input: str,
    ) -> dict:
        final_content = self.executor.execute_plan(
            plan_result,
            user_input,
            self.personality.name,
        )
        return {"role": "assistant", "content": final_content}

    # ── 直接応答（+ Tool Call + エスカレーション） ─────────

    def _execute_tool_calls(
        self,
        msg: dict,
        system_prompt: str,
        messages: list[dict],
        thinking_mode: bool,
        on_token: Callable[[str], None] | None,
        active_model: str,
    ) -> dict:
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
            max_tokens=self.max_tokens_for_model(active_model),
            on_token=on_token,
        )
        return dict(final["message"])

    def max_tokens_for_model(self, model_name: str) -> int:
        for m in self.models:
            if m.name == model_name:
                return m.max_tokens
        return 512

    def _needs_escalation(self, msg: dict, active_role: str) -> bool:
        if active_role != "base":
            return False
        if not self.escalation_config.enabled:
            return False
        content = msg.get("content", "")
        if not content:
            return True
        return content.startswith("Error:") or content.startswith("エラー:")

    def _escalate(
        self,
        system_prompt: str,
        messages: list[dict],
        thinking_mode: bool,
        on_token: Callable[[str], None] | None,
    ) -> dict:
        if self.escalation_config.swap_on_escalate:
            base_entry = self.models_by_role["base"]
            self.llm.unload_model(base_entry.name)

        smart_entry = self.models_by_role["smart"]
        smart_tools = self.registry.list_tools()

        response = self.llm.chat(
            messages=[{"role": "system", "content": system_prompt}, *messages],
            model=smart_entry.name,
            enable_thinking=thinking_mode,
            temperature=self.temperature,
            max_tokens=smart_entry.max_tokens,
            tools=smart_tools,
            on_token=on_token,
        )
        return dict(response["message"])

    def _handle_direct_response(
        self,
        system_prompt: str,
        messages: list[dict],
        thinking_mode: bool,
        tools_list: list[dict] | None,
        max_tokens: int,
        on_token: Callable[[str], None] | None,
        active_model: str,
        active_role: str,
    ) -> tuple[dict, bool]:
        escalated = False

        response = self.llm.chat(
            messages=[{"role": "system", "content": system_prompt}, *messages],
            model=active_model,
            enable_thinking=thinking_mode,
            temperature=self.temperature,
            max_tokens=max_tokens,
            tools=tools_list,
            on_token=on_token,
        )

        msg = dict(response["message"])
        messages.append(msg)

        if msg.get("tool_calls"):
            msg = self._execute_tool_calls(msg, system_prompt, messages, thinking_mode, on_token, active_model)

        if self._needs_escalation(msg, active_role):
            msg = self._escalate(system_prompt, messages, thinking_mode, on_token)
            escalated = True

        return msg, escalated

    # ── Quick Reflection ───────────────────────────────────

    def _run_quick_reflection(self, messages: list[dict], count: int) -> int:
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
        last_role: str,
        msg_count_since_reflect: int,
        on_token: Callable[[str], None] | None = None,
    ) -> ProcessResult:
        # Phase 1: 複雑性判定
        complexity = _assess_complexity(user_input, last_role)

        # Phase 2: モデル選択（ツール権限フィルタ込み）
        active_model, active_role, max_tokens, tools_list = self._select_model_and_tools(
            complexity,
            thinking_mode,
            plan_mode,
        )

        # Phase 3: コンテキスト圧縮判定
        conversation_summary = self.context_manager.check_and_summarize(
            messages,
            context_window=self.context_window,
            threshold=self.compaction_threshold,
        )

        # Phase 4: RAG取得
        rag_results = self._retrieve_rag(user_input)

        # Phase 5: システムプロンプト構築
        system_prompt = self._build_system_prompt(
            conversation_summary,
            rag_results,
            user_input,
        )

        # Phase 6: Plan判定
        should_plan = False
        plan_result = None
        has_complex_trigger = any(t in user_input.lower() for t in COMPLEX_TRIGGERS)
        if active_role == "smart" and (plan_mode or (thinking_mode and has_complex_trigger)):
            plan_result = self.planner.analyze(user_input, system_prompt[:300])
            should_plan = self.planner.is_complex(plan_result) if not plan_mode else True

        # Phase 7: 思考モードでユーザー入力をラップ
        if thinking_mode:
            messages[-1] = messages[-1].copy()
            messages[-1]["content"] = self.personality.build_thinking_prompt(user_input)

        # Phase 8: 簡易グリーティング抑制
        if (
            active_role != "smart"
            and not thinking_mode
            and user_input.strip().lower() in ("hello", "hi", "bye", "thanks", "ありがとう")
        ):
            max_tokens = SHORT_GREET_TOKENS

        # Phase 9: 応答生成
        if should_plan:
            assert plan_result is not None
            msg = self._handle_plan(plan_result, user_input)
            escalated = False
            messages.append(msg)
        else:
            msg, escalated = self._handle_direct_response(
                system_prompt,
                messages,
                thinking_mode,
                tools_list,
                max_tokens,
                on_token,
                active_model,
                active_role,
            )

        # Phase 10: Quick Reflection
        msg_count_since_reflect = self._run_quick_reflection(messages, msg_count_since_reflect)

        return ProcessResult(
            response_message=msg,
            thinking_mode=thinking_mode,
            plan_mode=plan_mode,
            active_model=active_model,
            active_role=active_role,
            msg_count_since_reflect=msg_count_since_reflect,
            escalated=escalated,
        )
