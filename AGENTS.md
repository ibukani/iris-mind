# Iris Agent Entry

## Highest Priority

- `AGENTS.md` is the entry point. Do not add detailed rules here.
- Only this file should be read by default.
- Read referenced files only when they are needed for the current task.
- Implementation is the source of truth. If documentation conflicts with code, inspect the implementation and update the documentation when necessary.

## Response Style

- Reply to the user in Japanese by default, unless the user explicitly requests another language.
- Omit greetings and redundant prefaces.
- Keep answers concise.
- Do not omit change rationale, risks, validation results, or unverified items.

## Safety

- Do not perform destructive data changes, authentication changes, external sending, persistent storage deletion, or Git history changes without explicit confirmation.
- Commit only when the user explicitly asks for a commit.

## Work Style

- Prioritize MVP delivery. Make the current specification work with the shortest maintainable path.
- When specifications change, do not prioritize preserving old functions or old APIs.
- Delete unnecessary functions, compatibility layers, old branches, dead tests, and outdated documentation.
- Do not fear changing or deleting code. Replace it with a small design that matches the current specification.
- Avoid overlay implementations, temporary wrappers, excessive abstraction, and future-only hooks.
- Ask only about true blockers. Infer the rest from the implementation.

## References

- Project summary and responsibility boundaries: `.agents/project.md`
- Ordinary development, MVP decisions, code rules, validation, Git: `.agents/skills/iris-dev-workflow/SKILL.md`
- New top-level Plugin: `.agents/skills/iris-plugin-create/SKILL.md`
- Hook additions: `.agents/skills/iris-plugin-hook/SKILL.md`
- Provider / sub-plugin additions: `.agents/skills/iris-plugin-provider/SKILL.md`
- Plugin structure cleanup: `.agents/skills/iris-plugin-structure/SKILL.md`
- Diagrams / Mermaid: `.agents/skills/iris-visualize/SKILL.md`
- Documentation sync: `.agents/skills/doc-sync/SKILL.md`
- Capability / tool additions: `.agents/skills/capability-pattern/SKILL.md`
- Design details: `docs/`

## When to Read

- Task start: `.agents/project.md` if needed.
- Code changes: `iris-dev-workflow`.
- Plugin-related work: the relevant plugin skill.
- Documentation update check: `doc-sync`.
- Design decisions: only the relevant `docs/*.md` files.

## Commands

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

## Git

- Commit only when the user explicitly asks for it.
- Use Japanese commit messages.
- Put code changes and required documentation updates in the same commit.
