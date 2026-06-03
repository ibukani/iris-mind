---
description: Implement the specified feature or change.
---

@implementer

Implementation request: `$1`

Implement the specified feature or change.

## Rules

- Investigate the necessary scope first.
- Keep the change scope as small as necessary for the requested outcome.
- For Cognitive Runtime migration work, read `.agents/skills/iris-cognitive-runtime/SKILL.md` and relevant sections of `docs/architecture/current.md`.
- Add, update, or delete tests according to current behavior and current architecture.
- Do not preserve obsolete compatibility unless explicitly required.
- Do not add PluginManager/EventBus compatibility shims unless explicitly requested.
- Do not leak provider-specific behavior into cognitive/domain layers.
- Do not let generated transport types or external app SDK types leak into cognitive/domain code.
- Treat tests as evidence, not authority. Rewrite stale or over-specified tests with rationale.

## v1.2.1 Guardrails

- `cognitive/` must not import `adapters/`, `runtime/`, or `features/`.
- `contracts/` must not import `cognitive/`, `adapters/`, or `runtime/`.
- Use typed contracts and typed step results instead of `dict[str, Any]` internal boundaries.
- Use constructor injection instead of service locators or global registries.
- Features register through `FeatureDefinition`.

## Validation Candidates

```bash
uv run pytest <related-tests> -q
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```
