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

### 1. Target architecture documents

For v1.2.1 migration work, prefer the current target architecture document:

| Change target | Documents to update |
|---|---|
| Cognitive Runtime architecture changes | `docs/architecture/current.md` or a focused ADR |
| CognitiveCycle / WorkspaceFrame / PipelineStep changes | `docs/architecture/current.md` |
| FeatureDefinition / feature extension changes | `docs/architecture/current.md` |
| AppGateway / external app boundary changes | `docs/architecture/current.md`, relevant `docs/external/*.md` if the external protocol changes |
| Safety / presentation flow changes | `docs/architecture/current.md` |
| Runtime wiring / scheduler / background job changes | `docs/architecture/current.md` |
| Configuration changes | `docs/config.md` and target architecture sections if the runtime model changes |
| Model routing / LLM adapter changes | `docs/how-it-works/11-model-routing.md`, `docs/config.md`, and target adapter sections when relevant |

### 2. Legacy documents `docs/*.md`

Existing documents such as `docs/architecture.md`, `docs/kernel-layer.md`, `docs/io-layer.md`, `docs/agency-layer.md`, `docs/memory-layer.md`, `docs/limbic-layer.md`, and `docs/how-it-works/*.md` may describe the pre-v1.2.1 design.

Update them only when one of these is true:

- the user explicitly asks to keep legacy docs synchronized during migration
- the changed code still belongs to the pre-migration structure
- external protocol documentation must remain accurate for existing clients

Do not rewrite all legacy docs during unrelated migration steps. Prefer marking the v1.2.1 target document as the source of truth for migration direction.

### 3. Self profile `.iris/config/iris_profile.md`

Update only when:

- Personality, tone, or behavior rules changed.
- A capability change affects Iris self-recognition, available capabilities, or behavior.
- Do not update it for internal implementation-only changes.

### 4. `AGENTS.md`

Update only for:

- Reference route changes for the agent entry point.
- Changes to the always-read file policy.
- Changes to highest-priority operating principles.

Do not move detailed coding standards, workflows, or directory structures back into `AGENTS.md`. Put them in the relevant Skill or `.agents/project.md`.

### 5. `.agents/README.md`, `.agents/project.md`

Update when these change:

- Agent routing (`.agents/README.md`).
- Project summary (`.agents/project.md`).
- Skill selection rules or responsibility boundaries.

Keep `.agents/` token-efficient. Do not duplicate detailed design information, progress logs, or history. Link to the source of truth instead.

### 6. Skills `.agents/skills/*/SKILL.md`

Update when capability addition patterns, development workflow, MVP decisions, Cognitive Runtime migration rules, or legacy Plugin conventions change.

## Procedure

1. Identify what changed.
2. Use the tables above to list documents that may need updates.
3. Read each relevant document and update only the affected sections.
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
