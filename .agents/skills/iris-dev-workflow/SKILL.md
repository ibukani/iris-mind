---
name: iris-dev-workflow
description: |
  Use when making ordinary Iris code or documentation changes, especially MVP implementation,
  refactoring, deleting or changing existing functions, validation, and commit preparation.
  Do NOT use for plugin-specific creation/provider/hook details; use the dedicated plugin skills.
license: MIT
metadata:
  audience: developers
  workflow: iris-development
---

## Purpose

This is the ordinary Iris development workflow. Avoid overly conservative decisions that block MVP development. Fix the implementation into the smallest working shape that matches the current specification.

## Operating Rules

- Narrow the impact area first with `rg` / `rg --files`.
- Read related files in parallel. As a default, read up to 5 files per turn.
- Implementation is the primary source. If documentation or Skills conflict with code, inspect and fix the implementation or documentation as needed.
- Preserve backward compatibility only when explicitly requested.
- Specification changes may change, delete, or rename existing functions.
- Do not keep unnecessary functions, branches, settings, tests, or docs.
- Do not layer new behavior on top of obsolete implementation. Replace it with a shape that matches the current specification.
- Add abstraction only when it actually reduces duplication or complexity.
- Do not create future-only extension points, unused hooks, or compatibility wrappers.

## Workflow

1. Confirm requirements. Ask only about blockers.
2. Investigate impact area with glob + grep.
3. Read existing implementation and tests.
4. Delete or replace old implementation that does not match the current specification.
5. Validate per change unit.
6. Use `doc-sync` to check for missed documentation updates.
7. Commit only when the user explicitly asks.

## MVP Decision Policy

- Prefer "correct for the current specification" over "avoid breaking anything".
- Public APIs may be changed when the user requested a specification change.
- Do not add migration code, deprecated paths, or old-format parsing unless explicitly requested.
- Tests should lock the new specification. Delete or rewrite tests for the old specification.
- Prefer small complete replacements over large redesigns.
- However, explicitly confirm destructive data changes, authentication changes, external sending, persistent storage deletion, and Git history changes.

## Python Rules

- Python 3.13+.
- Put `from __future__ import annotations` at the top of each Python file.
- Use `X | None`, not `Optional[X]`.
- Use `list[X]`, `dict[K, V]`, and `X | Y`, not `List[X]`, `Dict[K, V]`, or `Union[X, Y]`.
- Use `-> None` when there is no return value.
- Import order: future -> stdlib -> third party -> `iris.`.
- Naming: `snake_case`, `PascalCase`, `UPPER_SNAKE_CASE`.
- Do not use bare `except:`. Use `except Exception:` only sparingly.
- Use `with` for resources.
- Comment only where intent is not obvious.
- Prefer f-strings.

## Architecture Rules

- All layers stay loosely coupled through `iris/event/`.
- `debug_tools/` may depend on `iris/`; the reverse is forbidden.
- Do not keep `PluginManager` inside logic classes. Use explicit constructor injection.
- EventBus subscription should generally live in `handler.py`. Managers should not subscribe directly.
- Do not perform a large refactor solely to make existing implementation perfectly match structure rules. Split responsibilities only when it is relevant to the current change.
- For Plugin structure details, read `iris-plugin-structure`.

## Refactor Policy

- If forcing a specification change into the current structure would increase mixed responsibilities, duplication, or complex branching, perform the necessary refactor first.
- When an old design no longer matches the new specification, prefer replacing it with a current-spec structure over preserving compatibility.
- Limit refactoring to the scope needed to implement the current specification naturally.
- Do not perform unrelated beautification, broad cleanups, or changes whose only goal is perfect compliance with structure rules.

## Validation

Validation only:

```bash
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

When fixes are allowed:

```bash
uv run ruff check --fix .
uv run ruff format .
```

For narrow changes, start with targeted tests. Expand validation to the necessary range before finishing.

## Docs

- After code changes, read `doc-sync`.
- Do not leave descriptions of deleted features.
- Do not leave historical notes such as "currently", "previously", or "formerly".
- Do not move details back into `AGENTS.md`; keep it reference-only.

## Git

- Commit only when the user explicitly asks.
- Use Japanese commit messages.
- Put code changes and required documentation updates in the same commit.
