---
name: doc-sync
description: |
  Use after making changes to iris code or project rules
  (new features, refactoring, architecture changes, AGENTS/skills workflow changes).
  Checks which docs need updating.
  Do NOT use: purely informational requests with no file changes.
license: MIT
metadata:
  audience: developers
  workflow: iris-docs
---

## What I Do

This workflow identifies and updates documentation that may need changes after feature additions, code changes, refactoring, architecture changes, or project rule changes.

## Documents to Check

### 1. Design documents `docs/*.md`

Update the relevant document according to the type of change:

| Change target | Documents to update |
|---|---|
| Architecture changes | `docs/architecture.md` |
| Memory system changes | `docs/memory-layer.md`, `docs/how-it-works/02-memory-system.md` |
| EventBus changes | `docs/how-it-works/01-eventbus.md`, `docs/architecture.md`, related layer documents |
| Decision-making / action execution changes | `docs/agency-layer.md`, `docs/how-it-works/05-decision-making.md`, `docs/how-it-works/08-execution-pipeline.md` |
| Process management changes | `docs/kernel-layer.md` |
| Input/output changes | `docs/io-layer.md`, `docs/external/*.md` |
| Configuration changes | `docs/config.md` |
| Model routing changes | `docs/how-it-works/11-model-routing.md`, `docs/config.md` |
| General new feature | Consider creating a new relevant document when none exists |

When updating docs, also check consistency with related code such as `iris/event/event_types.py`.

### 2. Self profile `.iris/config/iris_profile.md`

Update only when:

- Personality, tone, or behavior rules changed.
- A capability change affects Iris self-recognition, available capabilities, or behavior.
- Do not update it for internal implementation-only changes.

### 3. `AGENTS.md`

Update only for:

- Reference route changes for the agent entry point.
- Changes to the always-read file policy.
- Changes to highest-priority operating principles.

Do not move detailed coding standards, workflows, or directory structures back into `AGENTS.md`. Put them in the relevant Skill or `.agents/project.md`.

### 4. `.agents/README.md`, `.agents/project.md`

Update when these change:

- Agent routing (`.agents/README.md`).
- Project summary (`.agents/project.md`).
- Skill selection rules or responsibility boundaries.

Keep `.agents/` token-efficient. Do not duplicate detailed design information, progress logs, or history. Link to the source of truth instead.

### 5. Skills `.agents/skills/*/SKILL.md`

Update when capability addition patterns, development workflow, MVP decisions, or Plugin conventions change.

## Procedure

1. Identify what changed.
2. Use the table above to list documents that may need updates.
3. Read each document and update the relevant sections.
   - Remove descriptions of deleted features completely. Do not leave historical residue such as "currently", "previously", or "formerly" notes. Documentation should describe the current state only.
4. Validate according to the change type.

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

5. If and only if the user explicitly asks for a commit, include code changes and documentation updates in the same commit.

## When to Use Me

- After adding or changing features.
- Before a commit when you need to check for missed documentation updates.
- After changing project rules.
