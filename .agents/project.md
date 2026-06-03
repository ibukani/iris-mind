# Iris Project Brief

This file is a compact helper note for Iris-specific scope and responsibility boundaries. Use `.agents/skills/iris-dev-workflow/SKILL.md` as the source for ordinary development rules, and `docs/architecture/current.md` as the source for architecture decisions.

## Current Direction

- Iris is built on Cognitive Runtime Architecture v1.2.1.
- The architecture source of truth is `docs/architecture/current.md`.
- The legacy Plugin/EventBus architecture has been deleted (Phase 12).
- Do not add PluginManager/EventBus compatibility shims unless the user explicitly requests them.

## Scope

- Iris is a Python AI companion / assistant Cognitive Runtime. It handles autonomous behavior, task execution, memory, relationship, proactive behavior, and presentation policy.
- This repository contains the Iris runtime core. UI, Discord bot, Voice runtime, Twitch client, and other concrete external apps belong to separate projects.
- External apps communicate with Iris through `Observation`, `AppAction`, and `ActionResult` style boundaries.
- LLM providers such as Ollama and OpenRouter are implementation details behind adapters and ports.

## Target Modules

- `iris/core/`: shared low-level IDs, time, errors, result types, and small utilities.
- `iris/contracts/`: shared typed contracts such as observations, actions, identity, conversation, memory, affect, and commands.
- `iris/runtime/`: app startup, configuration, lifecycle, scheduler, background jobs, telemetry, and dependency wiring.
- `iris/runtime/wiring/`: constructor-injection-only composition split by area.
- `iris/cognitive/`: CognitiveCycle, workspace, perception, memory, affect, motivation, policy, action, and learning.
- `iris/cognitive/workspace/`: frozen typed `WorkspaceFrame` snapshots for one cognitive turn.
- `iris/presentation/`: transforms `ActionPlan` into `PresentedOutput`; decides how to show behavior, not what to do.
- `iris/safety/`: action and output gates before external execution.
- `iris/adapters/`: external technology boundaries such as app gateway, LLM, stores, tools, embeddings, and external clients.
- `iris/features/`: vertical feature definitions registered through `FeatureDefinition`.
- `iris/admin/`: administration and diagnostics.

## Target Boundaries

- `contracts/` may depend on `core/` only.
- `cognitive/` may depend on `contracts/` and `core/`, but not on `adapters/`, `runtime/`, or `features/`.
- `presentation/`, `safety/`, and `adapters/` may depend on `contracts/` and `core/`.
- `features/` registers extension providers through `FeatureDefinition`; it must not patch cognitive internals directly.
- `runtime/` is the composition root and may know all layers.
- `runtime/wiring/` performs constructor injection only; it must not contain cognitive, business, or adapter behavior.
- `debug_tools/` may depend on `iris/`, but `iris/` must not depend on `debug_tools/`.

## Explicit Non-Targets

- Do not use EventBus as CognitiveCycle main control flow.
- Do not add PluginManager compatibility layers.
- Do not add service locator, global registry, or `resolve_optional` paths.
- Do not add `action: str` dispatcher branches for new behavior.
- Do not use `dict[str, Any]` or `dict[str, object]` as internal cross-layer context.
- Do not create unused extension points just because they may be useful later.

## Workflows

- Cognitive Runtime migration: `.agents/skills/iris-cognitive-runtime/SKILL.md`
- Ordinary development: `.agents/skills/iris-dev-workflow/SKILL.md`
- Diagrams / Mermaid: `.agents/skills/iris-visualize/SKILL.md`
- Documentation update check: `.agents/skills/doc-sync/SKILL.md`
- Design changes: record them in `docs/architecture/current.md` or a focused ADR when the change updates the target architecture.

## Context Rules

- Do not write branch status, completed tasks, or past decision logs here.
- Before implementation, read only the files required for the task. For large design documents, inspect only relevant sections.
- After changes, ensure they do not conflict with the loading policy in `AGENTS.md` and `.agents/README.md`.
- Do not add a detailed directory tree here. Use `rg --files iris` to inspect actual code when needed.
