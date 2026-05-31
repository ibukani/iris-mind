# Codex Prompt: Fix Bug

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

Fix the described bug.

## Bug-fix workflow

1. Reproduce or reason to the failing path.
2. Identify the smallest responsible unit.
3. Add a failing test when practical.
4. Fix the bug.
5. Verify the test passes.
6. Check nearby edge cases.

## Rules

- Do not rewrite unrelated code.
- Do not weaken tests.
- Do not hide the bug with mocks.
- If the issue is environment-dependent, report the dependency or condition clearly.

## Validation

```bash
python -m compileall -q iris tests
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```
