---
description: Add tests for the current diff or specified target.
---

@tester

Target: `$1`

Add or update the necessary tests.

## Rules

- Do not treat only the diff or specified files as the complete scope.
- Check references, existing tests, config, and entrypoints.
- Do not depend on external LLM APIs or a running Ollama instance.
- Do not weaken the specification just to make tests pass.

## Validation Candidates

```bash
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```
