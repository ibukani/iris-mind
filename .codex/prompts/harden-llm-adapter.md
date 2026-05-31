# Codex Prompt: Harden LLM Adapter

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

Improve robustness of the LLM adapter area.

## Initial investigation targets

```text
iris/llm/
iris/kernel/config.py
iris/agency/execution/llm/
iris/agency/execution/nodes/
tests/
```

## Goals

- correct model/provider routing
- safe cache keys
- clear environment validation
- capability-driven tools/thinking behavior
- correct `temperature=0.0` handling
- robust streaming cancellation
- tests that avoid real external LLM calls

## Out of scope

```text
iris/memory/
iris/limbic/
iris/io/transport/
proto/
```

Only cross these boundaries if discovery proves it is necessary.

## Validation

```bash
python -m compileall -q iris tests
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```
