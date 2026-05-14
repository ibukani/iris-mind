import pytest

from iris.kernel.agent_state import AgentStateManager, State
from iris.kernel.event_bus import AgentStateChangeEvent, EventBus


def make_manager() -> tuple[AgentStateManager, EventBus]:
    eb = EventBus()
    m = AgentStateManager(event_bus=eb, timeout_seconds=99999)
    m._current = State.IDLE
    return m, eb


# Actual transition rules from agent_state.py _ALLOWED_TRANSITIONS
# + same-state is always True (line 96)
TRANSITION_TABLE: list[tuple[State, State, bool]] = [
    (State.IDLE, State.PROCESSING, True),
    (State.IDLE, State.PROACTIVE, True),
    (State.IDLE, State.SLEEPING, True),
    (State.IDLE, State.THINKING, True),
    (State.IDLE, State.REFLECTING, False),
    (State.IDLE, State.IDLE, True),
    (State.PROCESSING, State.IDLE, True),
    (State.PROCESSING, State.REFLECTING, True),
    (State.PROCESSING, State.SLEEPING, True),
    (State.PROCESSING, State.PROCESSING, True),
    (State.PROCESSING, State.PROACTIVE, False),
    (State.PROCESSING, State.THINKING, False),
    (State.PROACTIVE, State.IDLE, True),
    (State.PROACTIVE, State.SLEEPING, True),
    (State.PROACTIVE, State.PROCESSING, False),
    (State.PROACTIVE, State.REFLECTING, False),
    (State.PROACTIVE, State.THINKING, False),
    (State.PROACTIVE, State.PROACTIVE, True),
    (State.REFLECTING, State.IDLE, True),
    (State.REFLECTING, State.PROCESSING, True),
    (State.REFLECTING, State.SLEEPING, False),
    (State.REFLECTING, State.THINKING, False),
    (State.REFLECTING, State.REFLECTING, True),
    (State.THINKING, State.IDLE, True),
    (State.THINKING, State.PROCESSING, True),
    (State.THINKING, State.SLEEPING, False),
    (State.THINKING, State.REFLECTING, False),
    (State.THINKING, State.THINKING, True),
    (State.SLEEPING, State.IDLE, True),
    (State.SLEEPING, State.PROCESSING, False),
    (State.SLEEPING, State.REFLECTING, False),
    (State.SLEEPING, State.THINKING, False),
    (State.SLEEPING, State.PROACTIVE, False),
    (State.SLEEPING, State.SLEEPING, True),
]


@pytest.mark.parametrize("from_state,to_state,expected", TRANSITION_TABLE)
def test_state_transitions(from_state: State, to_state: State, expected: bool) -> None:
    manager, _ = make_manager()
    manager._current = from_state
    result = manager.transition(to_state)
    assert result == expected
    if expected:
        assert manager.current == to_state
    else:
        assert manager.current == from_state


def test_transition_publishes_event() -> None:
    eb = EventBus()
    manager = AgentStateManager(event_bus=eb)
    received: list[AgentStateChangeEvent] = []

    def handler(event: AgentStateChangeEvent) -> None:
        received.append(event)

    eb.subscribe("AgentStateChangeEvent", handler)
    manager.transition(State.PROCESSING)

    assert len(received) == 1
    assert received[0].previous_state == State.IDLE
    assert received[0].new_state == State.PROCESSING


def test_transition_to_sleeping_and_back() -> None:
    manager, _ = make_manager()
    assert manager.transition(State.SLEEPING) is True
    assert manager.is_sleeping() is True
    assert manager.transition(State.PROCESSING) is False
    assert manager.transition(State.IDLE) is True
    assert manager.is_idle() is True


def test_state_query_methods() -> None:
    manager, _ = make_manager()
    assert manager.is_idle() is True
    manager.transition(State.PROCESSING)
    assert manager.is_processing() is True
    manager.transition(State.IDLE)
    manager.transition(State.PROACTIVE)
    assert manager.is_proactive() is True
    manager.transition(State.IDLE)
    manager.transition(State.PROCESSING)
    manager.transition(State.REFLECTING)
    assert manager.is_reflecting() is True
    manager.transition(State.IDLE)
    manager.transition(State.THINKING)
    assert manager.is_thinking() is True
    manager.transition(State.IDLE)
    manager.transition(State.SLEEPING)
    assert manager.is_sleeping() is True


def test_timeout_from_processing() -> None:
    eb = EventBus()
    manager = AgentStateManager(event_bus=eb, timeout_seconds={State.PROCESSING: -1.0})
    manager.transition(State.PROCESSING)
    timed_out = manager.check_timeout()
    assert timed_out == State.IDLE
    assert manager.is_idle() is True


def test_no_timeout_when_idle() -> None:
    manager, _ = make_manager()
    assert manager.is_idle() is True
    timed_out = manager.check_timeout()
    assert timed_out is None
    assert manager.is_idle() is True


def test_current_property() -> None:
    manager, _ = make_manager()
    assert manager.current == State.IDLE
    manager.transition(State.PROCESSING)
    assert manager.current == State.PROCESSING
