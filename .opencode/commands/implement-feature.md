---
description: Implement the specified feature or change.
---

@implementer

Implementation request: `$1`

Implement the specified feature or change.

## Rules

- Investigate the necessary scope first.
- Keep the change scope as small as necessary.
- Add, update, or delete tests according to current behavior.
- Do not preserve obsolete compatibility unless explicitly required.
- Do not leak provider-specific behavior into upper layers.
- Do not break memory / limbic / execution / transport responsibility boundaries.
- Treat tests as evidence, not authority. Rewrite stale or over-specified tests with rationale.

## Validation Candidates

```bash
uv run pytest <related-tests> -q
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```
