# Iris Agent Entry

## Highest Priority

- `AGENTS.md` is the entry point. Do not add detailed rules here.
- Only this file should be read by default.
- Read referenced files only when they are needed for the current task.
- Iris uses Cognitive Runtime Architecture v1.2.1.
- The current architecture source of truth is `docs/architecture/current.md`.
- The legacy Plugin/EventBus-centered architecture has been deleted (Phase 12).
- Implementation remains the source of truth for current behavior, but v1.2.1 is the source of truth for architecture direction.

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
- Do not add PluginManager/EventBus compatibility shims.
- When the user explicitly requests code-quality-first refactoring, use `iris-dev-workflow` Quality-First Refactoring Mode instead of MVP/minimal-diff defaults.
- Ask only about true blockers. Infer the rest from the implementation and the v1.2.1 architecture document.

## References

- Project summary and responsibility boundaries: `.agents/project.md`
- Cognitive Runtime migration rules: `.agents/skills/iris-cognitive-runtime/SKILL.md`
- Ordinary development, MVP decisions, code rules, validation, Git: `.agents/skills/iris-dev-workflow/SKILL.md`
- Diagrams / Mermaid: `.agents/skills/iris-visualize/SKILL.md`
- Documentation sync: `.agents/skills/doc-sync/SKILL.md`
- Current architecture target: `docs/architecture/current.md`
- Legacy removal record: `docs/archive/legacy-removal-summary.md`
- Development/testing guide: `docs/development/testing.md`
- AI agent guidelines: `docs/development/agent-guidelines.md`

## When to Read

- Task start: `.agents/project.md` if project boundaries matter.
- v1.2.1 architecture work: `iris-cognitive-runtime` and `docs/architecture/current.md`.
- Ordinary code changes: `iris-dev-workflow`.
- Documentation update check: `doc-sync`.

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


<!-- headroom:rtk-instructions -->

# RTK (Rust Token Killer) - Selective Token-Optimized Commands

RTK is optional. Do not prefix every shell command with `rtk`.

Use RTK only when the command is expected to produce large, repetitive, or low-signal output where lossy filtering is acceptable. Prefer raw commands when exact output is needed for reasoning, debugging, review, or patching.

## Default Policy

* Use raw commands by default.
* Use `rtk` for noisy exploratory commands.
* Do not use `rtk` when the exact output matters.
* If RTK output is missing needed detail, rerun the original command directly and avoid repeated RTK retries.
* If unsure, prefer the raw command.

## Good RTK Use Cases

```bash
# Large directory or environment inspection
rtk ls <path>
rtk find <pattern>
rtk env
rtk deps

# Noisy install/build logs where only errors matter
rtk npm install
rtk pnpm install
rtk cargo build
rtk pip list

# Broad test runs where only failures are needed
rtk pytest tests/
rtk cargo test
rtk test <cmd>

# Large logs or JSON summaries
rtk log <file>
rtk json <file>
rtk summary <cmd>

# Infrastructure outputs
rtk docker ps
rtk docker logs <container>
rtk kubectl get <resource>
```

## Avoid RTK For Exact Reasoning

Do not use RTK for commands where omitted lines may change the conclusion:

```bash
git diff
git show
git status --porcelain
git log --patch
pytest <specific failing test>
mypy
ruff check
tsc
rg <important symbol or pattern>
grep <important symbol or pattern>
sed -n ...
cat <small or important file>
```

## Git and Review Rules

* Use raw `git diff` for code review and patch verification.
* Use raw `git show` when inspecting commit contents.
* Use raw `git status --short` or `git status --porcelain` when deciding what changed.
* RTK may be used for broad summaries, but raw git output is required before making conclusions.

## Debugging Rules

* For failing tests, first use the raw failing command when the output is small or specific.
* For large test suites, `rtk pytest tests/` may be used to locate failures.
* After identifying a failing test, rerun the specific failing test without RTK.
* For type/lint errors, prefer raw output unless the output is extremely large.

## Command Chains

Do not blindly prefix every segment in command chains. Use RTK only for the noisy segment.

```bash
git status --short && rtk pytest tests/
```

## Tracking Without Filtering

Use `rtk proxy <cmd>` only when tracking is useful but filtering is not desired.

<!-- /headroom:rtk-instructions -->
