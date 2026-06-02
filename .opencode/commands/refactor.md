---
description: Refactor the specified target while preserving current intended behavior.
---

@refactorer

Refactor target: `$1`

Perform a scoped refactor.

## Goals

- Improve structure, type-safety, readability, and responsibility boundaries.
- Delete dead code, unnecessary compatibility layers, and obsolete branches.
- Do not preserve backward compatibility unless explicitly required.
- Update affected tests and documentation.
- For v1.2.1 migration, move responsibilities toward the Cognitive Runtime target architecture rather than wrapping old modules.

## Rules

- Treat specified files as initial targets only.
- Inspect references, imports, related tests, config, and runtime entrypoints.
- Do not let bad tests block valid refactoring.
- Preserve async cancellation and streaming behavior when still in scope.
- Do not leak provider-specific behavior into cognitive/domain layers.
- Keep cognitive/domain code independent from transport-generated and external app SDK types.
- Do not retain PluginManager/EventBus compatibility layers for new architecture unless explicitly requested.

## v1.2.1 Guardrails

- Read `.agents/skills/iris-cognitive-runtime/SKILL.md` for migration refactors.
- `cognitive/` must not import `adapters/`, `runtime/`, or `features/`.
- `contracts/` must not import `cognitive/`, `adapters/`, or `runtime/`.
- `WorkspaceFrame` must remain frozen and typed.
- `PipelineStep` returns typed results; `FrameBuilder` owns frame updates.
- Features register through `FeatureDefinition`.

## Validation Candidates

```bash
uv run pytest <related-tests> -q
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```
