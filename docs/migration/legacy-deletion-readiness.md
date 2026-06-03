# Legacy Deletion Readiness

## Strategy change (Phase 11)

Full feature-by-feature legacy migration has been **abandoned**.

The project is now on an **early legacy deletion / MVP reconstruction route**:

- The target runtime (`main.py` → `iris.runtime.*`) is the **source of truth**.
- Legacy Plugin/EventBus code is **reference-only**, not runtime material.
- Removed features (gRPC, Discord, LangMem, proactive, heartbeat, tools,
  room/account, full memory) may be rebuilt later as target-native
  implementations.
- Do not preserve legacy runtime compatibility.

Phase 11 has cut over `main.py` to the target runtime.  The legacy
Supervisor/Kernel/PluginManager/EventBus path is no longer the default.

## Phase 11 status

Phase 11 (MVP Runtime Cutover) is **complete**.  Changes:

- `main.py` now delegates to `iris.runtime.cli` (target Cognitive Runtime).
  It no longer imports `iris.kernel` or `iris.event`.
- Architecture guards verify `main.py`, `iris/runtime/cli.py`, and
  `iris/runtime/wiring/` do not import legacy packages and do not
  reference PluginManager/EventBus.
- Architecture guards no longer require `iris/kernel` or `iris/event` to
  exist (deletion is now the intended direction).
- Tests added for the main.py entrypoint (`tests/runtime/test_main_entrypoint.py`).
- Documentation now states the early deletion / MVP reconstruction strategy.
- Legacy test suite remains quarantined behind markers and is not part of
  the default validation path.

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
| `iris/account` | A/D | `contracts/identity.py` | main.py no longer reaches iris/account; legacy-only | Safe to delete |
| `iris/agency` | A/D | `cognitive/policy/`, `cognitive/action/` | main.py no longer reaches iris/agency; target policy exists | Safe to delete |
| `iris/limbic` | A/D | `cognitive/affect/` | Target appraisal/relationship steps exist; legacy limbic is unused | Safe to delete |
| `iris/llm` | A/D | `adapters/llm/` | Target LLM adapters exist; legacy provider discovery is unused | Safe to delete |
| `iris/memory` | A/D | `contracts/memory.py`, `cognitive/memory/`, `adapters/memory/` | Target memory contracts/adapters exist; legacy memory is unused | Safe to delete |
| `iris/room` | A/D | future `contracts/session.py` | main.py no longer reaches iris/room; legacy-only | Safe to delete |
| `iris/tools` | A/D | future `contracts/tools.py` | main.py no longer reaches iris/tools; legacy-only | Safe to delete |

## Per-package deletion gates

Before deleting any legacy package, verify these gates are satisfied:

| Gate | Description |
|---|---|
| **Import gate** | `tests/architecture/test_phase9_migration_control.py` passes (no target package imports legacy) |
| **Test gate** | All legacy tests in the package are either migrated to target tests or explicitly marked `legacy`/`legacy_architecture` |
| **Runtime gate** | `main.py` or the active entrypoint no longer imports or starts the package |
| **Docs gate** | README, architecture docs, and this document no longer reference the package as current |

## Superseded: Phase 10+ recommended deletion order

The feature-by-feature migration plan below has been superseded by the
early deletion / MVP reconstruction strategy.  All legacy packages are
now rated A/D (safe to delete) because `main.py` no longer reaches them.

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

## Phase 11 remaining blockers before hard legacy deletion

The target runtime is now the default execution path.  Legacy packages
(`iris/kernel`, `iris/event`, etc.) are no longer reached via `main.py`.

Remaining before hard deletion:

- Add `iris/admin` to forbidden imports in architecture guards, or
  confirm it is no longer needed.
- Remove or archive legacy tests that reference deleted packages.
- Verify `config.yaml` / `iris/kernel/config.py` is not imported by
  any target path.
- Run full test suite with markers to confirm legacy tests are
  quarantined and target tests pass independently.
- Delete legacy packages in a single atomic commit after all of the
  above are confirmed.

## What is now safe to delete

After Phase 11, the following packages have no runtime dependency from
`main.py` or any target module:

- `iris/event`
- `iris/kernel`
- `iris/io`
- `iris/account`
- `iris/room`
- `iris/agency`
- `iris/memory`
- `iris/limbic`
- `iris/llm`
- `iris/tools`
- `iris/heartbeat`
- `iris/admin`

Architecture tests at `tests/architecture/test_phase10_runtime_cutover.py`
and `tests/architecture/test_phase9_migration_control.py` enforce target
package isolation.  The import gate is satisfied for all target packages.

The runtime gate is now satisfied — `main.py` no longer imports or starts
any legacy package.

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
