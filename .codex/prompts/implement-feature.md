# Codex Prompt: Implement Feature

Read `AGENTS.md` first.

## Discovery requirement

Treat the user request and any listed files as initial investigation targets, not a complete scope.

Before editing:

1. Search for references to target classes/functions/config keys.
2. Inspect import sites and call sites.
3. Inspect related tests.
4. Inspect configuration, registration, and runtime entrypoints.
5. Look for parallel, legacy, deprecated, or similarly named implementations.
6. Identify whether additional files must be read or changed.
7. Report whether the initial assumptions were sufficient.

Do not assume the listed files are sufficient.


## Task

Implement the requested feature in Iris-Mind.

## Rules

- Keep the change focused.
- Do not cross layer boundaries without justification.
- Add or update tests for behavior changes.
- Avoid external LLM API calls in tests.
- Avoid requiring Ollama or external services in unit tests.
- Keep provider-specific logic inside `iris/adapters/llm`.

## Validation

Run when possible:

```bash
python -m compileall -q iris tests
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

## Report

```text
Changed files:
- ...

Summary:
- ...

Tests:
- ...

Validation:
- ...

Remaining concerns:
- ...
```
