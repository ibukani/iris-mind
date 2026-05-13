"""
Step 4 検証スクリプト — AgentKernel + AnomalyDetector
"""
from __future__ import annotations

import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from iris.kernel.agent_kernel import AgentKernel, AnomalyDetector
from iris.kernel.agent_state import AgentStateManager, State
from iris.kernel.config import ProactiveConfig
from iris.kernel.event_bus import (
    AgentResponseEvent,
    AgentStateChangeEvent,
    EventBus,
    ProactiveSpeechEvent,
    TimerTick,
    UserInputEvent,
)
from iris.kernel.memory_manager import MemoryManager
from iris.kernel.proactive import ProactiveEngine
from iris.memory.stores import EpisodicStore, SemanticStore

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

_tmpdir = Path(tempfile.mkdtemp(prefix="iris_step4_"))

event_bus = EventBus()
config = ProactiveConfig(enabled=True, check_interval_sec=0.1)
state = AgentStateManager(event_bus=event_bus)

episodic = EpisodicStore(
    path=str(_tmpdir / "episodes.jsonl"), max_entries=10
)
semantic = SemanticStore(
    path=str(_tmpdir / "semantic.jsonl"),
    max_entries=10,
    vector_db_path=str(_tmpdir / "chroma"),
)
memory = MemoryManager(episodic=episodic, semantic=semantic)

proactive = ProactiveEngine(
    config=config,
    event_bus=event_bus,
    state_manager=state,
    memory=memory,
)

kernel = AgentKernel(
    event_bus=event_bus,
    state_manager=state,
    proactive=proactive,
    memory=memory,
    config=config,
)

captured_speech: list[ProactiveSpeechEvent] = []


def on_speech(event: ProactiveSpeechEvent) -> None:
    captured_speech.append(event)


event_bus.subscribe("ProactiveSpeechEvent", on_speech)


# ── Test 1: AnomalyDetector ──────────────────────────────
print("\n=== Test 1: AnomalyDetector ===")
ad = AnomalyDetector()
check("detector created", ad is not None)

flags = ad.record_speech()
check("single speech no flags", len(flags) == 0, f"got {flags}")

for _ in range(10):
    ad.record_speech()
    time.sleep(0.01)
flags = ad.record_speech()
check("excess speech detected", "frequency_exceeded" in flags, f"got {flags}")

# Health check
healthy = ad.check_suppression_health({"suppression": {}})
check("healthy returns empty", len(healthy) == 0)

with_ignores = ad.check_suppression_health(
    {"suppression": {"consecutive_ignores": 3, "confirmation_mode": True}}
)
check("ignores detected", any(i["type"] == "high_ignore_rate" for i in with_ignores))
check("confirmation detected", any(i["type"] == "confirmation_mode" for i in with_ignores))


# ── Test 2: AgentKernel lifecycle ───────────────────────
print("\n=== Test 2: AgentKernel lifecycle ===")
check("not running initially", not kernel._running)

kernel.startup()
check("running after startup", kernel._running)
check("state is IDLE", state.is_idle())

# Stop timer early for stability in subsequent tests
kernel.shutdown()
check("not running after shutdown", not kernel._running)
check("timer thread stopped", kernel._timer_thread is None)


# ── Test 3: UserInputEvent handling ─────────────────────
print("\n=== Test 3: UserInputEvent handling ===")
kernel.startup()
time.sleep(0.2)

# Clear any pre-existing state by resetting proactive
proactive.reset()

event_bus.publish(
    UserInputEvent(
        timestamp=datetime.now(),
        source="user_input",
        content="test user input",
    )
)
time.sleep(0.05)

recent = memory.get_recent(3)
check("input recorded to episodic", any("test user input" in r.get("summary", "") for r in recent))

# Input while processing should be rejected (AgentKernel waits for AgentResponseEvent)
state.transition(State.PROCESSING)
event_bus.publish(
    UserInputEvent(
        timestamp=datetime.now(),
        source="user_input",
        content="during processing",
    )
)
time.sleep(0.05)
entries = memory._episodic._load_all()
check(
    "processing state rejects input",
    not any(e["summary"] == "during processing" for e in entries),
)
state.transition(State.IDLE)

kernel.shutdown()


# ── Test 4: ProactiveSpeechEvent handling ────────────────
print("\n=== Test 4: ProactiveSpeechEvent handling ===")
kernel.startup()
time.sleep(0.2)

speech_count_before = len(captured_speech)

event_bus.publish(
    ProactiveSpeechEvent(
        timestamp=datetime.now(),
        source="proactive",
        content="test proactive speech",
        trigger_type="time",
        confidence=0.8,
    )
)
time.sleep(0.05)

recent = memory.get_recent(3)
check(
    "proactive speech recorded to episodic",
    any("test proactive speech" in r.get("summary", "") for r in recent),
)
check(
    "speech event captured by subscriber",
    len(captured_speech) == speech_count_before + 1,
)

kernel.shutdown()


# ── Test 5: State change logging ─────────────────────────
print("\n=== Test 5: State change logging ===")
state_change_events: list[AgentStateChangeEvent] = []


def on_state_change(event: AgentStateChangeEvent) -> None:
    state_change_events.append(event)


event_bus.subscribe("AgentStateChangeEvent", on_state_change)

kernel.startup()
time.sleep(0.1)

# Trigger a state change: UserInputEvent → PROCESSING, then AgentResponseEvent → IDLE
event_bus.publish(
    UserInputEvent(
        timestamp=datetime.now(),
        source="user_input",
        content="trigger state change",
    )
)
# Send response to trigger IDLE transition
event_bus.publish(
    AgentResponseEvent(
        timestamp=datetime.now(),
        source="assistant",
        content="response",
    )
)
time.sleep(0.05)

kernel.shutdown()

check(
    "state transitions: IDLE→PROCESSING→IDLE",
    len(state_change_events) >= 2,
    f"got {len(state_change_events)}",
)


# ── Test 6: TimerTick scheduling ─────────────────────────
print("\n=== Test 6: TimerTick scheduling ===")
timer_events: list[TimerTick] = []


def on_timer(event: TimerTick) -> None:
    timer_events.append(event)


event_bus.subscribe("TimerTick", on_timer)

config.check_interval_sec = 0.05
kernel.startup()
time.sleep(0.12)
kernel.shutdown()

check("timer ticks generated", len(timer_events) >= 2, f"got {len(timer_events)}")
config.check_interval_sec = 0.1  # restore


# ── Summary ─────────────────────────────────────────────
print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
if failed:
    sys.exit(1)
else:
    print("All tests passed!")
