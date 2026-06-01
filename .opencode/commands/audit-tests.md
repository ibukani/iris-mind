---
description: Audit and clean up tests for the specified target.
---

@test-auditor

Test audit target: `$1`

Audit the tests and clean up low-value or harmful coverage.

## Goals

- Determine which tests should be kept, rewritten, or deleted.
- Remove duplicate, stale, misleading, or over-specified tests.
- Rewrite valuable tests around current public behavior and boundaries.
- Identify code that should be refactored because bad tests were hiding it.

## Rules

- Do not assume the test suite is correct.
- Do not delete tests without checking the implementation and related callers.
- Do not preserve obsolete compatibility tests unless the current specification requires them.
- Do not require external LLM APIs or a running Ollama instance.

## Validation Candidates

```bash
uv run pytest <related-tests> -q
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```
