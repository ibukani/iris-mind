---
description: Add or update tests for the current diff or specified target.
---

@tester

Target: `$1`

Add, update, or delete the necessary tests.

## Rules

- Do not treat only the diff or specified files as the complete scope.
- Check references, existing tests, config, and entrypoints.
- Prefer behavior-level assertions over implementation-detail assertions.
- Do not depend on external LLM APIs or a running Ollama instance.
- Do not weaken a valid specification just to make tests pass.
- Rewrite or delete stale, duplicate, or misleading tests with rationale.

## Validation Candidates

```bash
uv run pytest <related-tests> -q
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```
