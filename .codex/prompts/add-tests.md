# Codex Prompt: Add Tests

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

Add or update tests for the requested behavior or current diff.

## Rules

- Do not weaken tests to make them pass.
- Prefer focused tests near the changed code.
- Avoid real external LLM API calls.
- Avoid requiring Ollama or external services in unit tests.
- Use fakes/stubs for provider, bridge, gateway, and transport dependencies.
- If a failure is environment-related, report it clearly.

## Test priorities

- capability/tool/thinking behavior
- streaming cancellation behavior
- config/env validation behavior
- memory retention/consolidation behavior
- limbic appraisal/mood/relationship behavior
- transport adapter and error mapping behavior

## Validation

```bash
python -m compileall -q iris tests
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```
