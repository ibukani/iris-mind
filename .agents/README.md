# .agents

`.agents/` contains auxiliary context for coding agents. Do not duplicate permanent project facts here. Prefer links and routes to the source of truth.

## Context Budget

- Only `AGENTS.md` should be read by default.
- Read this file only when you need to confirm the role of `.agents/`.
- Read `project.md` only when you need a project summary or responsibility boundaries.
- Read `skills/*/SKILL.md` only when the current task matches that skill.
- When multiple skills apply, prefer the most specific skill.
- Read only the relevant files under `docs/` when a design decision is needed.
- Retrieve only the necessary Git history or test results. Do not copy past logs into `.agents/`.

## Skill Priority

When responsibilities overlap, use this priority order:

1. Cognitive Runtime migration: `skills/iris-cognitive-runtime/SKILL.md`
2. Capability / tool addition: `skills/capability-pattern/SKILL.md`
3. Ordinary development: `skills/iris-dev-workflow/SKILL.md`
4. Documentation update check: `skills/doc-sync/SKILL.md`

## Legacy Plugin Skills

The following Skills describe the old Plugin/EventBus-centered architecture. They are legacy-only during the v1.2.1 migration and must not be used for new Cognitive Runtime work unless the user explicitly asks for legacy Plugin maintenance.

- `skills/iris-plugin-provider/SKILL.md`
- `skills/iris-plugin-hook/SKILL.md`
- `skills/iris-plugin-create/SKILL.md`
- `skills/iris-plugin-structure/SKILL.md`

## Files

- `project.md`: Minimal project summary for agents. Follow links to design documents for details.
- `skills/`: Skill definitions that standardize repeated work.

## Source of Truth

- Agent entry point: `AGENTS.md`
- Target architecture: `docs/architecture/cognitive-runtime-v1.2.1.md`
- Cognitive Runtime migration rules: `skills/iris-cognitive-runtime/SKILL.md`
- Ordinary development rules: `skills/iris-dev-workflow/SKILL.md`
- Legacy architecture documents: existing `docs/*.md` files that describe pre-v1.2.1 behavior
- Implementation history: Git commits / PRs / Issues
- Temporary work notes: Do not keep them permanently here. Manage them only with the user or inside the working branch when needed.

## Rules

- Do not keep progress logs or branch status permanently in `.agents/`.
- Record target architecture decisions in `docs/architecture/cognitive-runtime-v1.2.1.md` or a focused ADR.
- If an operational procedure changes, update the corresponding Skill. Keep `AGENTS.md` limited to minimal references.
- Prefer references over summaries. Do not write the same fact in multiple files unless doing so prevents incorrect agent routing.
