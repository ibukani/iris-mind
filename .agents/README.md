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

1. Capability / tool addition: `skills/capability-pattern/SKILL.md`
2. LLM provider / store backend / sub-plugin addition: `skills/iris-plugin-provider/SKILL.md`
3. Hook or HookPoint addition: `skills/iris-plugin-hook/SKILL.md`
4. New top-level Plugin creation: `skills/iris-plugin-create/SKILL.md`
5. Existing Plugin structure cleanup: `skills/iris-plugin-structure/SKILL.md`
6. Ordinary development: `skills/iris-dev-workflow/SKILL.md`
7. Documentation update check: `skills/doc-sync/SKILL.md`

## Files

- `project.md`: Minimal project summary for agents. Follow links to design documents for details.
- `skills/`: Skill definitions that standardize repeated work.

## Source of Truth

- Agent entry point: `AGENTS.md`
- Ordinary development rules: `skills/iris-dev-workflow/SKILL.md`
- Architecture and design decisions: `docs/architecture.md`
- Implementation history: Git commits / PRs / Issues
- Temporary work notes: Do not keep them permanently here. Manage them only with the user or inside the working branch when needed.

## Rules

- Do not keep progress logs or branch status permanently in `.agents/`.
- Record design decisions in `docs/architecture.md`; create `docs/adr/` when needed.
- If an operational procedure changes, update the corresponding Skill. Keep `AGENTS.md` limited to minimal references.
- Prefer references over summaries. Do not write the same fact in multiple files.
