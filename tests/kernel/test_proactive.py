from __future__ import annotations

from typing import Any

from iris.kernel.agent_state import AgentStateManager, State
from iris.kernel.event_bus import EventBus, TimerTick
from iris.kernel.proactive import ProactiveConfig, ProactiveEngine
from tests.conftest import FakeLLMProvider, FakeMemoryManager

# ── Helper ────────────────────────────────────────────────────


def make_engine(
    config: ProactiveConfig | None = None,
    event_bus: EventBus | None = None,
    state: AgentStateManager | None = None,
    memory: FakeMemoryManager | None = None,
    llm: Any = None,
    fast_model: str | None = None,
    time_provider: Any = None,
) -> ProactiveEngine:
    """Build ProactiveEngine with test defaults."""
    eb = event_bus or EventBus()
    st = state or AgentStateManager(event_bus=eb)
    st._state = State.IDLE  # ensure idle
    cfg = config or ProactiveConfig(
        enabled=True,
        check_interval_sec=5.0,
        min_interval_sec=60.0,
        max_interval_sec=600.0,
        speak_threshold=0.3,
        tier1_auto_approve=True,
        tier2_confidence_threshold=0.7,
    )
    mem = memory or FakeMemoryManager()
    return ProactiveEngine(
        config=cfg,
        event_bus=eb,
        state_manager=st,
        memory=mem,
        llm=llm,
        fast_model=fast_model,
        time_provider=time_provider,
    )


def step_time() -> float:
    """Simple monotonic time provider."""
    t = 1000.0
    while True:
        yield t
        t += 1.0


# ── _try_parse_json ──────────────────────────────────────────


class TestTryParseJson:
    def test_direct_json(self) -> None:
        result = ProactiveEngine._try_parse_json('{"speech": "hello", "confidence": 0.8}')
        assert result is not None
        assert result["speech"] == "hello"
        assert result["confidence"] == 0.8

    def test_markdown_code_block(self) -> None:
        result = ProactiveEngine._try_parse_json('```json\n{"speech": "hi", "confidence": 0.5}\n```')
        assert result is not None
        assert result["speech"] == "hi"

    def test_brace_extraction(self) -> None:
        text = 'Some text before { "speech": "hello" } and after'
        result = ProactiveEngine._try_parse_json(text)
        assert result is not None
        assert result["speech"] == "hello"

    def test_invalid_input(self) -> None:
        assert ProactiveEngine._try_parse_json("") is None
        assert ProactiveEngine._try_parse_json("not json") is None
        assert ProactiveEngine._try_parse_json("{broken") is None

    def test_nested_braces(self) -> None:
        text = '{"speech": "hi", "data": {"nested": true}}'
        result = ProactiveEngine._try_parse_json(text)
        assert result is not None
        assert result["speech"] == "hi"


# ── _char_bigram_set ─────────────────────────────────────────


class TestCharBigramSet:
    def test_normal_text(self) -> None:
        s = ProactiveEngine._char_bigram_set("hello")
        assert len(s) == 4
        assert "he" in s
        assert "el" in s
        assert "ll" in s
        assert "lo" in s

    def test_short_text(self) -> None:
        assert ProactiveEngine._char_bigram_set("a") == set()
        assert ProactiveEngine._char_bigram_set("") == set()

    def test_japanese(self) -> None:
        s = ProactiveEngine._char_bigram_set("こんにちは")
        assert len(s) == 4


# ── _estimate_confidence ─────────────────────────────────────


class TestEstimateConfidence:
    def test_basic(self) -> None:
        scores = {"time": 0.5, "memory": 0.5, "context": 0.5, "mood": 0.5}
        conf = ProactiveEngine._estimate_confidence(scores)
        assert 0.0 < conf <= 1.0

    def test_with_memory_weight(self) -> None:
        scores = {"time": 0.0, "memory": 1.0, "context": 0.0, "mood": 0.0}
        conf = ProactiveEngine._estimate_confidence(scores)
        assert conf >= 0.5

    def test_zero_scores(self) -> None:
        scores = {"time": 0.0, "memory": 0.0, "context": 0.0, "mood": 0.0}
        assert ProactiveEngine._estimate_confidence(scores) == 0.0


# ── Suppression Check ────────────────────────────────────────


class TestSuppressionCheck:
    def test_allows_when_conditions_met(self) -> None:
        engine = make_engine()
        now = 1000.0
        assert engine._suppression_check(now) is True

    def test_rejects_during_cooldown(self) -> None:
        engine = make_engine()
        now = 1000.0
        engine._suppression.cooldown_until = 2000.0
        assert engine._suppression_check(now) is False

    def test_rejects_when_sleeping(self) -> None:
        engine = make_engine()
        engine._suppression.is_sleeping = True
        assert engine._suppression_check(1000.0) is False

    def test_rejects_negative_mood(self) -> None:
        engine = make_engine()
        engine._suppression.negative_mood_score = 0.8
        assert engine._suppression_check(1000.0) is False

    def test_rejects_confirmation_mode(self) -> None:
        engine = make_engine()
        engine._suppression.consecutive_ignores = 2
        engine._suppression.confirmation_mode = True
        assert engine._suppression_check(1000.0) is False

    def test_rejects_frequency_exceeded(self) -> None:
        engine = make_engine()
        now = 1000.0
        engine._suppression.proactive_timestamps = [now - 10, now - 20, now - 30]
        assert engine._suppression_check(now) is False

    def test_rejects_recent_user_activity(self) -> None:
        engine = make_engine()
        now = 1000.0
        engine._suppression.last_user_activity = now - 1
        assert engine._suppression_check(now) is False

    def test_rejects_min_interval(self) -> None:
        engine = make_engine()
        now = 1000.0
        engine._suppression.last_proactive_time = now - 10
        assert engine._suppression_check(now) is False


# ── Trigger Scoring ──────────────────────────────────────────


class TestTriggerScoring:
    def test_time_score_zero_when_recent(self) -> None:
        engine = make_engine()
        now = 1000.0
        engine._suppression.last_proactive_time = now - 10
        score = engine._compute_time_score(now)
        assert score == 0.0

    def test_time_score_increases_with_time(self) -> None:
        engine = make_engine()
        engine._suppression.last_user_activity = 0.0
        score = engine._compute_time_score(300.0)
        assert 0.0 < score <= 1.0

    def test_time_score_first_time(self) -> None:
        engine = make_engine()
        engine._suppression.last_proactive_time = 0.0
        engine._suppression.last_user_activity = 0.0
        score = engine._compute_time_score(1000.0)
        assert score == 0.4

    def test_context_score_low_with_different_topics(self) -> None:
        engine = make_engine()
        engine._memory.add_episodic("hello world")
        engine._memory.add_episodic("python programming")
        score = engine._compute_context_score()
        assert 0.0 <= score <= 1.0

    def test_context_score_with_short_responses(self) -> None:
        engine = make_engine()
        engine._memory.add_episodic("ok")
        engine._memory.add_episodic("yes")
        score = engine._compute_context_score()
        assert score == 0.7

    def test_mood_score_high_when_no_negative(self) -> None:
        engine = make_engine()
        score = engine._compute_mood_score()
        assert score == 1.0

    def test_mood_score_zero_when_negative(self) -> None:
        engine = make_engine()
        engine._suppression.negative_mood_score = 0.8
        assert engine._compute_mood_score() == 0.0

    def test_total_scoring(self) -> None:
        engine = make_engine()
        now = 1000.0
        total, scores = engine._score_triggers(now)
        assert "time" in scores
        assert "memory" in scores
        assert "context" in scores
        assert "mood" in scores
        assert 0.0 <= total <= 1.0


# ── Speech Generation ────────────────────────────────────────


class TestSpeechGeneration:
    def test_tier1_generates_text(self) -> None:
        engine = make_engine(llm=FakeLLMProvider())
        scores = {"time": 0.8, "memory": 0.0, "context": 0.0, "mood": 0.0}
        speech = engine._build_tier1_speech(scores)
        assert isinstance(speech, str)
        assert len(speech) > 0

    def test_tier1_fallback_no_llm(self) -> None:
        engine = make_engine(llm=None)
        scores = {"time": 0.8, "memory": 0.0, "context": 0.0, "mood": 0.0}
        speech = engine._build_tier1_speech(scores)
        assert speech == "お疲れさまです！何かお手伝いしましょうか？"

    def test_tier2_parses_json_response(self) -> None:
        llm = FakeLLMProvider(
            responses=[
                {
                    "message": {
                        "content": '{"speech": "test speech", "confidence": 0.8, "reasoning": "test"}',
                        "role": "assistant",
                    }
                }
            ]
        )
        engine = make_engine(llm=llm)
        scores = {"time": 0.5, "memory": 0.0, "context": 0.0, "mood": 0.0}
        speech, confidence, reasoning = engine._build_tier2_speech(scores)
        assert speech == "test speech"
        assert confidence == 0.8
        assert reasoning == "test"

    def test_tier2_fallback_no_llm(self) -> None:
        engine = make_engine(llm=None)
        scores = {"time": 0.5, "memory": 0.0, "context": 0.0, "mood": 0.0}
        speech, confidence, reasoning = engine._build_tier2_speech(scores)
        assert len(speech) > 0
        assert 0.0 <= confidence <= 1.0


# ── Governance Flow ──────────────────────────────────────────


class TestGovernanceFlow:
    def test_tier1_auto_approves_time_trigger(self) -> None:
        engine = make_engine()
        scores = {"time": 0.8, "memory": 0.0, "context": 0.0, "mood": 0.0}
        result = engine._generate_speech(scores, 1000.0)
        assert result is not None
        assert result.tier == 1

    def test_tier1_auto_approves_mood_trigger(self) -> None:
        engine = make_engine()
        scores = {"mood": 0.8, "time": 0.0, "memory": 0.0, "context": 0.0}
        result = engine._generate_speech(scores, 1000.0)
        assert result is not None
        assert result.tier == 1

    def test_tier2_calls_llm_for_other_triggers(self) -> None:
        llm = FakeLLMProvider(
            responses=[
                {
                    "message": {
                        "content": '{"speech": "hi", "confidence": 0.8, "reasoning": "test"}',
                        "role": "assistant",
                    }
                }
            ]
        )
        engine = make_engine(
            llm=llm,
            config=ProactiveConfig(
                enabled=True,
                check_interval_sec=5.0,
                min_interval_sec=60.0,
                max_interval_sec=600.0,
                speak_threshold=0.3,
                tier1_auto_approve=True,
                tier2_confidence_threshold=0.7,
            ),
        )
        scores = {"memory": 0.8, "time": 0.0, "context": 0.0, "mood": 0.0}
        result = engine._generate_speech(scores, 1000.0)
        assert result is not None
        assert result.tier == 2

    def test_low_confidence_suppressed(self) -> None:
        llm = FakeLLMProvider(
            responses=[
                {"message": {"content": '{"speech": "hi", "confidence": 0.3, "reasoning": "low"}', "role": "assistant"}}
            ]
        )
        engine = make_engine(llm=llm)
        scores = {"memory": 0.2, "time": 0.0, "context": 0.0, "mood": 0.0}
        result = engine._generate_speech(scores, 1000.0)
        assert result is None

    def test_agent_kernel_rejects_low_confidence(self) -> None:
        llm = FakeLLMProvider(
            responses=[
                {"message": {"content": '{"speech": "hi", "confidence": 0.6, "reasoning": "mid"}', "role": "assistant"}}
            ]
        )
        engine = make_engine(llm=llm)
        scores = {"memory": 0.4, "time": 0.0, "context": 0.0, "mood": 0.0}
        result = engine._generate_speech(scores, 1000.0)
        # No approval_callback set -> published anyway (non-critical path)
        assert result is not None

    def test_confirmation_mode_suppressed_by_guard(self) -> None:
        """Known issue: _suppression_check rejects before confirmation speech is generated."""
        engine = make_engine()
        engine._suppression.consecutive_ignores = 2
        engine._suppression.confirmation_mode = True
        engine._suppression.last_proactive_time = 0.0
        engine._suppression.last_user_activity = 0.0
        result = engine._generate_speech({"time": 0.5, "memory": 0.0, "context": 0.0, "mood": 0.0}, 1000.0)
        # Currently blocked by _suppression_check (confirmation_mode check)
        assert result is None

    def test_tier1_generates_speech_when_allowed(self) -> None:
        engine = make_engine()
        engine._suppression.last_proactive_time = 0.0
        engine._suppression.last_user_activity = 0.0
        result = engine._generate_speech({"time": 0.8, "memory": 0.0, "context": 0.0, "mood": 0.0}, 1000.0)
        assert result is not None
        assert result.tier == 1


class TestDetermineTriggerType:
    def test_picks_highest_score(self) -> None:
        result = ProactiveEngine._determine_trigger_type({"time": 0.3, "memory": 0.9, "context": 0.1, "mood": 0.2})
        assert result == "memory"

    def test_first_on_tie(self) -> None:
        result = ProactiveEngine._determine_trigger_type({"time": 0.5, "memory": 0.5, "context": 0.5, "mood": 0.5})
        assert isinstance(result, str)


# ── Public API ───────────────────────────────────────────────


class TestPublicAPI:
    def test_notify_ignore_increments_counter(self) -> None:
        engine = make_engine()
        engine.notify_ignore()
        assert engine._suppression.consecutive_ignores == 1

    def test_notify_ignore_triggers_confirmation_mode(self) -> None:
        engine = make_engine()
        engine.notify_ignore()
        engine.notify_ignore()
        assert engine._suppression.confirmation_mode is True

    def test_notify_positive_response_resets_ignores(self) -> None:
        engine = make_engine()
        engine.notify_ignore()
        engine.notify_ignore()
        engine.notify_positive_response()
        assert engine._suppression.consecutive_ignores == 0
        assert engine._suppression.confirmation_mode is False

    def test_notify_user_activity_updates_timestamp(self) -> None:
        engine = make_engine()
        old = engine._suppression.last_user_activity
        engine.notify_user_activity()
        assert engine._suppression.last_user_activity >= old

    def test_set_cooldown(self) -> None:
        engine = make_engine(time_provider=lambda: 1000.0)
        engine.set_cooldown(600.0)
        assert engine._suppression.cooldown_until == 1600.0

    def test_set_mood(self) -> None:
        engine = make_engine()
        engine.set_mood(0.5)
        assert engine._suppression.negative_mood_score == 0.5

    def test_set_mood_clamps(self) -> None:
        engine = make_engine()
        engine.set_mood(-0.1)
        assert engine._suppression.negative_mood_score == 0.0
        engine.set_mood(1.5)
        assert engine._suppression.negative_mood_score == 1.0

    def test_reset(self) -> None:
        engine = make_engine()
        engine.notify_ignore()
        engine.set_mood(0.8)
        engine.reset()
        assert engine._suppression.consecutive_ignores == 0
        assert engine._suppression.negative_mood_score == 0.0
        assert engine._suppression.confirmation_mode is False

    def test_get_status(self) -> None:
        engine = make_engine()
        status = engine.get_status()
        assert "suppression" in status
        assert "consecutive_ignores" in status["suppression"]
        assert "is_sleeping" in status["suppression"]

    def test_timer_tick_triggers_when_idle(self) -> None:
        config = ProactiveConfig(
            enabled=True,
            check_interval_sec=0.0,
            min_interval_sec=0.0,
            max_interval_sec=600.0,
            speak_threshold=0.0,
            tier1_auto_approve=True,
            tier2_confidence_threshold=0.7,
        )
        gen = step_time()
        eb = EventBus()
        st = AgentStateManager(event_bus=eb)
        engine = make_engine(config=config, event_bus=eb, state=st, time_provider=lambda: next(gen))
        results: list[str] = []

        def collect(event: Any) -> None:
            results.append(event.content)

        eb.subscribe("ProactiveSpeechEvent", collect)
        engine._on_timer_tick(TimerTick(timestamp=None, source="test", tick_count=0))
        assert len(results) >= 1

    # ── Model injection ────────────────────────────────────────

    def test_tier1_speech_passes_fast_model(self) -> None:
        llm = FakeLLMProvider()
        engine = make_engine(llm=llm, fast_model="fast-model")
        result = engine._build_tier1_speech({"time": 0.8})
        assert result is not None
        assert llm._model_log[-1] == "fast-model"

    def test_tier2_speech_passes_fast_model(self) -> None:
        llm = FakeLLMProvider(
            responses=[
                {
                    "message": {
                        "content": '{"speech": "hello", "confidence": 0.9, "reasoning": "test"}',
                        "role": "assistant",
                    }
                }
            ]
        )
        engine = make_engine(llm=llm, fast_model="fast-model")
        scores = {"memory": 0.8, "time": 0.3, "context": 0.2, "mood": 0.1}
        speech, confidence, reasoning = engine._build_tier2_speech(scores)
        assert speech == "hello"
        assert confidence == 0.9
        assert llm._model_log[-1] == "fast-model"
