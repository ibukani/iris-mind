---
description: Implement the specified feature or change.
---

@implementer

Implementation request: `$1`

Implement the specified feature or change.

## Rules

- Investigate the necessary scope first.
- Keep the change scope as small as necessary.
- Add or update tests for changed behavior.
- Do not leak provider-specific behavior into upper layers.
- Do not break memory / limbic / execution / transport responsibility boundaries.

## Validation Candidates

```bash
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```
