# Iris Project Brief

This file is a compact helper note for Iris-specific scope and responsibility boundaries. Use `.agents/skills/iris-dev-workflow/SKILL.md` as the source for ordinary development rules, and `docs/architecture/cognitive-runtime-v1.2.1.md` as the source for migration design decisions.

## Current Direction

- Iris is migrating to Cognitive Runtime Architecture v1.2.1.
- The target architecture source of truth is `docs/architecture/cognitive-runtime-v1.2.1.md`.
- The old Plugin/EventBus-centered architecture is a migration source, not the target architecture.
- Do not preserve old Plugin/EventBus APIs, shims, wrappers, or compatibility layers unless the user explicitly requests them.
- During migration, prefer moving existing logic by responsibility into the v1.2.1 structure over wrapping old modules.

## Scope

- Iris is a Python AI companion / assistant Cognitive Runtime. It handles autonomous behavior, task execution, memory, relationship, proactive behavior, and presentation policy.
- This repository contains the Iris runtime core. UI, Discord bot, Voice runtime, Twitch client, and other concrete external apps belong to separate projects.
- External apps communicate with Iris through `Observation`, `AppAction`, and `ActionResult` style boundaries.
- LLM providers such as Ollama and OpenRouter are implementation details behind adapters and ports.
- Configuration lives in `config.yaml` until the runtime configuration is migrated.

## Target Main Modules

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
- `iris/admin/`: administration and diagnostics that are still needed.

## Legacy Modules During Migration

These modules currently contain useful implementation pieces but are not the target architecture boundaries.

- `iris/kernel/`: migrate process management, configuration, lifecycle, and composition into `runtime/`; do not keep PluginManager as the center.
- `iris/event/`: retire as main control flow; if needed later, limit to lifecycle, telemetry, audit, background notification, or diagnostics.
- `iris/io/`: migrate external app protocol boundaries into `adapters/app_gateway/`; concrete app runtimes should live outside Iris core.
- `iris/account/`: migrate identity and user context into `contracts/identity.py` and context services.
- `iris/room/`: migrate room/session concepts into `contracts/conversation.py` and app gateway context.
- `iris/memory/`: split into `cognitive/memory/`, `features/memory_consolidation/`, and `adapters/stores/`.
- `iris/limbic/`: migrate appraisal, mood, and relationship into `cognitive/affect/`.
- `iris/agency/`: split planning/inhibition/execution into `cognitive/policy/` and `cognitive/action/`.
- `iris/llm/`: migrate provider calls into `adapters/llm/`; prompt/action response policy belongs near `cognitive/action/`.
- `iris/tools/`: split tool-use decisions into `cognitive/action/` and actual execution into `adapters/tools/`.
- `iris/heartbeat/`: migrate scheduler behavior into `runtime/scheduler.py` and ObservationSource-based ticks.

### Design Policy: Iris Identity and Rooms

- **Only one Iris exists as an individual.**
- Rooms are a system for adding conversation locations, not copies of Iris.
- Emotion / mood is global unless the v1.2.1 design explicitly introduces a different typed state.
- Relationship is per user identity, not per room.
- If the same user talks to Iris in multiple rooms, intimacy and related relationship values are shared.

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
- Capability addition: `.agents/skills/capability-pattern/SKILL.md`
- Documentation update check: `.agents/skills/doc-sync/SKILL.md`
- Design changes: record them in `docs/architecture/cognitive-runtime-v1.2.1.md` or a focused ADR when the change updates the target architecture.

## Context Rules

- Do not write branch status, completed tasks, or past decision logs here.
- Before implementation, read only the files required for the task. For large design documents, inspect only relevant sections.
- After changes, ensure they do not conflict with the loading policy in `AGENTS.md` and `.agents/README.md`.
- Do not add a detailed directory tree here. Use `rg --files iris` to inspect actual code when needed.
