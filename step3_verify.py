"""
Step 3 検証スクリプト — ProactiveEngine
"""
from __future__ import annotations

import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from iris.kernel.agent_state import AgentStateManager, State
from iris.kernel.config import ProactiveConfig
from iris.kernel.event_bus import EventBus, ProactiveSpeechEvent, TimerTick
from iris.kernel.memory_manager import MemoryManager
from iris.kernel.proactive import ProactiveEngine, ProactiveResult
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


# ── Setup ────────────────────────────────────────────────

_tmpdir = Path(tempfile.mkdtemp(prefix="iris_step3_"))

event_bus = EventBus()
config = ProactiveConfig(enabled=True, check_interval_sec=0.1)
state = AgentStateManager(event_bus=event_bus)

episodic = EpisodicStore(path=str(_tmpdir / "episodes.jsonl"), max_entries=10)
semantic = SemanticStore(path=str(_tmpdir / "semantic.jsonl"), max_entries=10, vector_db_path=str(_tmpdir / "chroma"))
memory = MemoryManager(episodic=episodic, semantic=semantic)

engine = ProactiveEngine(
    config=config,
    event_bus=event_bus,
    state_manager=state,
    memory=memory,
)

# ── Test 1: SuppressionState initialization ──────────────
print("\n=== Test 1: SuppressionState init ===")
check("engine created", engine is not None)
check("suppression exists", engine._suppression is not None)
check("cooldown default 0", engine._suppression.cooldown_until == 0.0)
check("ignores default 0", engine._suppression.consecutive_ignores == 0)

# ── Test 2: TimerTick ignored when disabled ──────────────
print("\n=== Test 2: Disabled engine ===")
config.enabled = False
captured_events: list[ProactiveSpeechEvent] = []

def on_speech(event: ProactiveSpeechEvent) -> None:
    captured_events.append(event)

event_bus.subscribe("ProactiveSpeechEvent", on_speech)
event_bus.publish(TimerTick(timestamp=datetime.now(), source="timer", tick_count=1))
check("no speech when disabled", len(captured_events) == 0)

# ── Test 3: TimerTick ignored when not IDLE ─────────────
print("\n=== Test 3: Non-IDLE state ===")
config.enabled = True
state.transition(State.PROCESSING)
event_bus.publish(TimerTick(timestamp=datetime.now(), source="timer", tick_count=2))
check("no speech when processing", len(captured_events) == 0)
state.transition(State.IDLE)

# ── Test 4: Trigger scoring ─────────────────────────────
print("\n=== Test 4: Trigger scoring ===")
total, scores = engine._score_triggers(now=time.time())
check("total is float 0-1", 0.0 <= total <= 1.0, f"got {total}")
for key in ("time", "memory", "context", "mood"):
    check(f"score {key} in range", 0.0 <= scores[key] <= 1.0, f"got {scores[key]}")
check("trigger type is valid", engine._determine_trigger_type(scores) in scores)

# ── Test 5: Suppression check ───────────────────────────
print("\n=== Test 5: Suppression check ===")
engine._suppression.cooldown_until = time.time() + 9999
check("cooldown suppresses", not engine._suppression_check(now=time.time()))
engine._suppression.cooldown_until = 0.0

engine._suppression.negative_mood_score = 0.8
check("negative mood suppresses", not engine._suppression_check(now=time.time()))
engine._suppression.negative_mood_score = 0.0

engine._suppression.last_proactive_time = time.time()
check("recent speech suppresses", not engine._suppression_check(now=time.time()))
engine._suppression.last_proactive_time = 0.0

engine._suppression.consecutive_ignores = 2
engine._suppression.confirmation_mode = True
check("confirmation mode suppresses", not engine._suppression_check(now=time.time()))
engine._suppression.consecutive_ignores = 0
engine._suppression.confirmation_mode = False

# ── Test 6: Score computation ───────────────────────────
print("\n=== Test 6: Score computation ===")
now = time.time()
engine._suppression.last_proactive_time = now - 300  # 5min ago
time_score = engine._compute_time_score(now)
expected = (300 - config.min_interval_sec) / (config.max_interval_sec - config.min_interval_sec)
check("time score calculation", abs(time_score - min(expected, 1.0)) < 0.01, f"got {time_score}")

memory_score = engine._compute_memory_score()
check("memory score fallback 0", memory_score == 0.0, f"got {memory_score}")

mood_score = engine._compute_mood_score()
check("mood score default", mood_score > 0.0, f"got {mood_score}")

# ── Test 7: Tier generation ─────────────────────────────
print("\n=== Test 7: Tier generation ===")
result = engine._generate_speech(
    {"time": 0.9, "memory": 0.0, "context": 0.1, "mood": 0.5},
    now=time.time(),
)
check("tier1 generated", result is not None, "result was None")
if result:
    check("tier is 1 (temporal)", result.tier == 1, f"got {result.tier}")
    check("confidence is 1.0", result.confidence == 1.0, f"got {result.confidence}")
    check("trigger is temporal", result.trigger_type == "time", f"got {result.trigger_type}")
    check("reasoning mentions Tier1", "Tier1" in result.reasoning, f"got {result.reasoning}")

# Tier2 case (memory trigger)
result2 = engine._generate_speech(
    {"time": 0.1, "memory": 0.85, "context": 0.2, "mood": 0.3},
    now=time.time(),
)
check("tier2 generated", result2 is not None, "result was None")
if result2:
    check("tier is 2", result2.tier == 2, f"got {result2.tier}")
    check("confidence >= threshold", result2.confidence >= config.tier2_confidence_threshold, f"got {result2.confidence}")
    check("reasoning mentions Tier2", "Tier2" in result2.reasoning, f"got {result2.reasoning}")

# Low confidence → no speech (use non-Tier1 trigger to bypass auto-approve)
result3 = engine._generate_speech(
    {"time": 0.0, "memory": 0.1, "context": 0.0, "mood": 0.0},
    now=time.time(),
)
check("low confidence Tier2 suppressed", result3 is None, "result should be None")

# ── Test 8: Speech publishing ───────────────────────────
print("\n=== Test 8: Speech publishing ===")
before_count = len(captured_events)
r = ProactiveResult(
    content="テスト発話",
    tier=1,
    confidence=1.0,
    trigger_type="time",
    reasoning="test",
)
engine._publish_speech(r)
check("speech event published", len(captured_events) == before_count + 1, f"got {len(captured_events)}")
check("last_proactive_time updated", engine._suppression.last_proactive_time > 0)

# ── Test 9: Public API ──────────────────────────────────
print("\n=== Test 9: Public API ===")
engine.notify_user_activity()
check("user activity recorded", engine._suppression.last_user_activity > 0)

engine.notify_ignore()
check("ignore count incremented", engine._suppression.consecutive_ignores == 1)

engine.notify_ignore()
check("ignore triggers confirmation mode", engine._suppression.confirmation_mode)

engine.notify_positive_response()
check("positive resets ignores", engine._suppression.consecutive_ignores == 0)
check("positive resets confirmation", not engine._suppression.confirmation_mode)

engine.set_mood(0.9)
check("mood set high", engine._suppression.negative_mood_score == 0.9)
engine.set_mood(1.5)
check("mood clamped to 1.0", engine._suppression.negative_mood_score == 1.0)

engine.set_cooldown(30.0)
check("cooldown set", engine._suppression.cooldown_until > time.time())

engine.reset()
check("reset clears ignores", engine._suppression.consecutive_ignores == 0)
check("reset clears confirmation", not engine._suppression.confirmation_mode)
check("reset clears cooldown", engine._suppression.cooldown_until == 0.0)

# ── Test 10: Empty memory scoring ───────────────────────
print("\n=== Test 10: Empty memory handling ===")
check("memory score with empty store", engine._compute_memory_score() == 0.0)

# ── Summary ─────────────────────────────────────────────
print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
if failed:
    sys.exit(1)
else:
    print("All tests passed!")
