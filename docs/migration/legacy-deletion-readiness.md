# Phase 9 Legacy Deletion Readiness

Phase 9 is not a bulk deletion phase.  Its purpose is to make every later
feature migration and deletion reviewable, testable, and reversible before old
Plugin/EventBus-centered code is removed.

The target architecture is `docs/architecture/cognitive-runtime-v1.2.1.md`.
Existing Plugin/EventBus modules are migration sources only; they are not the
shape to reproduce in the new runtime.

## Phase 9+ status

Phase 9 (Legacy Migration Control) is **complete**.

Phase 10 (Runtime Cutover Preparation) is **complete**.  The following controls are now in place:

- **Test isolation**: `tests/conftest.py` is target-safe at import time.
  Legacy fixtures live in `tests/legacy/conftest.py` and are imported lazily
  inside fixture bodies.
- **Marker discipline**: All legacy test files carry `pytestmark = pytest.mark.legacy`.
  Legacy architecture tests carry `pytestmark = pytest.mark.legacy_architecture`.
  Migration control tests carry `pytestmark = pytest.mark.migration`.
- **Architecture guards**: `tests/architecture/test_phase9_migration_control.py`
  enforces target-package isolation, legacy marker coverage, collection helper
  safety, and deletion-readiness documentation presence.
- **Audit helpers**: `tests/architecture/test_legacy_audit.py` provides a
  lightweight scan for forbidden legacy imports in target packages.
- **Documentation**: This document tracks every legacy package with status,
  blockers, and next actions.

Phase 9 does **not**:

- delete any legacy packages
- replace `main.py` or the runtime entrypoint
- implement Phase 10+ runtime cutover
- migrate LangMem, Discord, gRPC, tool execution, or full memory systems
- change public behavior of the existing legacy runtime

## Deletion policy

Delete a legacy file only after all of the following are true.

1. The behavior that should survive has a target owner in `iris/contracts`,
   `iris/cognitive`, `iris/features`, `iris/adapters`, `iris/presentation`,
   `iris/safety`, or `iris/runtime`.
2. Target tests cover that behavior without using legacy fixtures from
   `tests/legacy/conftest.py`.
3. `main.py` or the active runtime entrypoint no longer reaches the file.
4. No target module imports the legacy package.
5. Legacy architecture tests that only protected the old design are removed or
   marked as legacy.
6. Documentation and README no longer present the removed design as current.
7. Dependencies that existed only for the removed implementation are moved to an
   optional extra or removed.

## Status categories

| Code | Meaning | Action |
|---|---|---|
| A | Migrated and unused | Delete after import/test/doc check |
| B | Needed behavior, not yet migrated | Port behavior first |
| C | Still needed by old entrypoint/tests | Quarantine and cut over entrypoint/tests |
| D | Not part of target architecture | Delete after proving no runtime dependency |

## Legacy package readiness table

| Legacy package | Status | Target owner | Current blocker | Next action |
|---|---:|---|---|---|
| `iris/account` | B/C | `contracts/identity.py`, future `adapters/account/` | Legacy room/account handlers and tests still use EventBus fixtures | Introduce target account/identity ports before deletion |
| `iris/agency` | B/C | `cognitive/policy/`, `cognitive/action/`, `features/proactive_talk/` | Planning/execution/modulation behavior not fully target-owned | Split by planning, inhibition, execution, modulation, proactive |
| `iris/event` | C/D | No direct target equivalent; `runtime/telemetry.py` only if needed | Old entrypoint and legacy fixtures still use EventBus | Remove only after runtime cutover and handler tests are retired |
| `iris/heartbeat` | B/C | future `runtime/tasks/heartbeat.py` or `features/heartbeat/` | TimerTick/EventBus-based old runtime remains | Rebuild as runtime task, not EventBus plugin |
| `iris/io` | B/C | `adapters/app_gateway/`, future `adapters/io/`, `contracts/transport.py` | gRPC/session path is still Plugin/EventBus-based | Convert inbound/outbound flow to Observation/PresentedOutput gateway |
| `iris/kernel` | C/D | `runtime/`, `runtime/wiring/`, `runtime/cli.py`, future `runtime/config.py` | `main.py` still starts Supervisor/KernelProcess/PluginManager; target CLI exists but is not the default entrypoint | Build new runtime entrypoint is done (Phase 10). Replace `main.py` in a later phase. |
| `iris/limbic` | B/C | `cognitive/affect/`, future `adapters/affect/` | Stores/classifier/persistence not fully moved | Port stores/classifier only; do not port orchestrator/plugin |
| `iris/llm` | B/C | `adapters/llm/`, `cognitive/action/response.py` | Provider discovery/context utilities remain legacy | Port provider adapters and token/context utilities, then delete bridge/registry |
| `iris/memory` | B/C | `contracts/memory.py`, `cognitive/memory/`, `adapters/memory/`, future `features/memory_consolidation/` | Short-term/sensory/long-term/procedural/LangMem not fully moved | Migrate in slices: short-term, sensory, long-term, procedural, LangMem |
| `iris/room` | B/C | future `contracts/session.py`, `adapters/room/` | Room lifecycle still tied to account/io/event handlers | Model RoomId/Session context in target contracts before deletion |
| `iris/tools` | B/C | future `contracts/tools.py`, `adapters/tools/`, `safety/tool_gate.py` | Tool execution still tied to legacy execution path | Move tool execution behind ActionSafetyGate/ToolExecutor |

## Per-package deletion gates

Before deleting any legacy package, verify these gates are satisfied:

| Gate | Description |
|---|---|
| **Import gate** | `tests/architecture/test_phase9_migration_control.py` passes (no target package imports legacy) |
| **Test gate** | All legacy tests in the package are either migrated to target tests or explicitly marked `legacy`/`legacy_architecture` |
| **Runtime gate** | `main.py` or the active entrypoint no longer imports or starts the package |
| **Docs gate** | README, architecture docs, and this document no longer reference the package as current |

## Phase 10+ recommended deletion order

Start with small slices that do not require preserving Plugin/EventBus shape.

1. **LLM utilities**: repetition/token/context helpers → `adapters/llm/`
2. **Limbic classifier/store**: retain behavior, drop plugin/orchestrator → `cognitive/affect/`
3. **Memory short-term/sensory**: rebuild as perception/memory steps → `cognitive/memory/`
4. **Runtime entrypoint**: `runtime` owns startup before kernel deletion → `runtime/wiring/` (Phase 10: target CLI exists; legacy `main.py` still active)
5. **IO/session gateway**: convert gRPC/session events → `adapters/app_gateway/`
6. **Account/Room**: model identity/session in target contracts → `contracts/identity.py`
7. **Agency/Planning**: split by planning, inhibition, execution → `cognitive/policy/`
8. **Tools**: move behind ActionSafetyGate → `safety/tool_gate.py`
9. **Event/Heartbeat**: remove only after runtime cutover
10. **Kernel**: delete Supervisor/PluginManager after new entrypoint is active

## Phase 9 controls implemented in code

- `tests/conftest.py` is target-safe at import time.  Legacy fixtures live in
  `tests/legacy/conftest.py` with lazy imports.
- `tests/fakes/session.py` no longer eagerly imports from `iris.io.models`.
- Legacy test files are marked with `pytest.mark.legacy` for filtering.
- Legacy architecture tests are marked with `pytest.mark.legacy_architecture`.
- `tests/architecture/test_phase9_migration_control.py` guards:
  - target packages have no legacy imports
  - collection helpers have no eager legacy imports
  - legacy test files have the `legacy` marker
  - legacy architecture tests have the `legacy_architecture` marker
  - `tests/fakes/session.py` has no eager legacy imports
  - `tests/legacy/conftest.py` exists
  - root conftest has no legacy imports under `TYPE_CHECKING`
  - deletion-readiness document tracks all legacy packages
- `tests/architecture/test_legacy_audit.py` provides a lightweight audit scan.
- `pyproject.toml` defines `target`, `legacy`, `legacy_architecture`, and
  `migration` markers under strict marker validation.

## Phase 10 controls implemented in code

Phase 10 (Runtime Cutover Preparation) adds the following:

- **Target runtime CLI**: `iris/runtime/cli.py` provides a one-turn text
  interaction entrypoint without importing legacy Kernel/EventBus modules.
- **Wiring helper**: `iris/runtime/wiring/app.py` wires `IrisApp` with
  deterministic FakeLLM or OpenAI backend.
- **CLI tests**: `tests/runtime/test_cli.py` verifies one-turn execution,
  deterministic output, observation structure, and request recording.
- **Architecture guard expansion**: `tests/architecture/test_phase10_runtime_cutover.py`
  enforces:
  - `iris/runtime/cli.py`, `iris/runtime/app.py`, and all `iris/runtime/wiring/`
    files do not import legacy modules
  - `iris/runtime` package has no eager legacy imports
  - `main.py`, `iris/kernel`, and `iris/event` remain intact (Phase 10 is
    non-destructive)
  - CLI structure requirements (`main()`, `run_one_turn()`)
- **README**: New target runtime usage documented alongside legacy runtime.
- **Runtime command**:
  ```bash
  python -m iris.runtime.cli --text "hello"
  python -m iris.runtime.cli --text "hello" --llm fake
  ```

## Phase 10 remaining blockers

The new target runtime CLI works for one-turn FakeLLM execution, but the
following remain before deleting `iris/kernel` and `iris/event`:

- The target CLI does not yet manage long-running sessions, multi-turn
  conversation, or streaming IO.
- `main.py` still starts the legacy Supervisor; no process-supervision
  equivalent exists in the target runtime.
- gRPC, Discord, heartbeat, proactive, and LangMem features are not
  wired into the target runtime yet.
- Full memory, tool execution, account, room, and agency subsystems
  are not migrated.

These are tasks for Phase 11 and beyond.

## Recommended validation lanes

Use target validation for v1.2.1 work:

```bash
uv run pytest \
  tests/architecture/test_cognitive_runtime_*.py \
  tests/architecture/test_phase9_migration_control.py \
  tests/architecture/test_phase10_runtime_cutover.py \
  tests/contracts tests/adapters tests/cognitive tests/features tests/runtime \
  -q -m "not legacy and not legacy_architecture"
```

Use legacy validation only when touching old Plugin/EventBus behavior:

```bash
uv run pytest -m "legacy or legacy_architecture" -q
```

Use full validation before deleting any package:

```bash
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy iris/core iris/contracts iris/cognitive iris/presentation iris/safety iris/features iris/adapters iris/runtime tests/architecture
```

## Warning

Large legacy deletion must not happen until all four gates (import, test,
runtime, docs) are satisfied for the specific package.  Each package must be
migrated feature-by-feature, validated independently, and deleted only when
the target implementation fully replaces its behavior.
