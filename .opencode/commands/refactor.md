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

## Rules

- Treat specified files as initial targets only.
- Inspect references, imports, related tests, config, and runtime entrypoints.
- Do not let bad tests block valid refactoring.
- Preserve async cancellation and streaming behavior.
- Do not leak provider-specific behavior into upper layers.
- Keep domain code independent from transport-generated types.

## Validation Candidates

```bash
uv run pytest <related-tests> -q
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```
