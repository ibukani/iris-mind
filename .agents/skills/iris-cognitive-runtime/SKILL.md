---
name: iris-cognitive-runtime
description: |
  Use when migrating Iris to Cognitive Runtime Architecture v1.2.1, adding new v1.2.1
  architecture tests, creating the Cognitive Runtime scaffold, or deciding where existing
  Plugin/EventBus-era responsibilities should move.
license: MIT
metadata:
  audience: developers
  workflow: iris-cognitive-runtime-migration
---

## Purpose

This Skill is the migration route for Cognitive Runtime Architecture v1.2.1. It prevents AI-coding agents from mixing the old Plugin/EventBus-centered structure with the new target structure.

Read the relevant sections of `docs/architecture/current.md` before making architecture decisions.

## Migration Priority

- Prefer the v1.2.1 target architecture over old docs, old tests, and old module names.
- Existing code is useful as implementation material, not as an architecture boundary to preserve.
- Preserve behavior only when it still belongs to the current specification.
- Do not create compatibility wrappers, shims, or old API forwarding layers unless the user explicitly asks.
- Do not add future-only hooks, empty extension points, or generic managers just to make later work look easier.

## Target Layers

```text
core/          shared low-level IDs, time, errors, result types
contracts/     typed cross-layer contracts
runtime/       startup, lifecycle, scheduler, background jobs, telemetry
runtime/wiring constructor-injection-only composition
cognitive/     CognitiveCycle, workspace, perception, memory, affect, motivation, policy, action, learning
presentation/  ActionPlan -> PresentedOutput
safety/        ActionSafetyGate and OutputSafetyGate
adapters/      external technology boundaries
features/      FeatureDefinition-based vertical extensions
admin/         admin and diagnostics when still needed
```

## Required Flow

```text
External App
→ Observation
→ AppGateway
→ CognitiveCycle
→ typed PipelineStep results
→ WorkspaceFrame
→ ActionPlan
→ ActionSafetyGate
→ Presentation
→ PresentedOutput
→ OutputSafetyGate
→ AppAction
→ External App
→ ActionResult
→ LearningHook
→ BackgroundJob
```

## Dependency Rules

Allowed direction:

```text
contracts -> core
cognitive -> contracts, core
presentation -> contracts, core
safety -> contracts, core
adapters -> contracts, core
features -> contracts, cognitive extension protocols, core
runtime -> cognitive, features, adapters, presentation, safety, contracts, core
```

Forbidden direction:

```text
cognitive -> adapters
cognitive -> runtime
cognitive -> features
contracts -> cognitive
contracts -> adapters
contracts -> runtime
features -> adapters, except with an explicit architecture decision
adapters -> cognitive, except with an explicit architecture decision
```

`runtime` is the composition root. Other layers must not learn the whole system.

## CognitiveCycle Rules

- `CognitiveCycle.run()` is a pipeline coordinator only.
- It may sequence steps, collect results, delegate frame updates, and select the final plan.
- It must not build prompts, call provider APIs, update memory stores, update relationships, execute adapters, or run safety gates.
- Cognitive modules must not directly call each other for main control flow. The cycle controls order.

Good shape:

```text
CognitiveCycle -> PerceptionStep -> FrameBuilder
CognitiveCycle -> MemoryRetrievalStep -> FrameBuilder
CognitiveCycle -> AppraisalStep -> FrameBuilder
CognitiveCycle -> ActionSelectionStep -> FrameBuilder
```

Bad shape:

```text
memory -> affect -> policy -> action
```

## WorkspaceFrame Rules

- `WorkspaceFrame` is a frozen typed snapshot for one turn.
- `PipelineStep` must not mutate a frame.
- `PipelineStep` returns a typed `PipelineStepResult` subtype.
- Only `FrameBuilder` creates the next frame from a previous frame and a typed result.
- Do not use `dict[str, Any]`, `dict[str, object]`, `MutableMapping`, manager references, stores, adapters, or giant prompt strings as cross-layer frame state.

## Feature Rules

- New vertical behavior goes under `features/<name>/` only when it is a feature extension.
- Feature registration goes through `FeatureDefinition`.
- MVP `FeatureDefinition` starts small: pipeline steps, observation sources, learning hooks, and background jobs.
- Do not create empty extension-point lists for future features.
- Features must not patch `CognitiveCycle` or cognitive internals directly.

## Adapter Rules

- Adapters translate between external technology and Iris contracts.
- `adapters/app_gateway/` receives `Observation`, executes `AppAction`, and returns `ActionResult`.
- AppGateway must not decide response content, proactive behavior, memory updates, relationship updates, or presentation style.
- Discord, Voice, Twitch, Avatar, TTS, and STT concrete runtimes should live outside Iris core unless the user explicitly changes that architecture.

## Safety and Presentation Rules

- `cognitive/` decides what Iris wants to do as an `ActionPlan`.
- `safety/ActionSafetyGate` checks whether the plan may proceed.
- `presentation/` decides how the plan is shown as `PresentedOutput`.
- `safety/OutputSafetyGate` checks the final output.
- `adapters/` convert the safe output into executable app actions.
- Do not merge character inhibition with external-operation safety.

## Legacy Migration Map

```text
kernel/    -> runtime/
event/     -> retire, or later restrict to telemetry/audit/lifecycle diagnostics
io/        -> adapters/app_gateway/
account/   -> contracts/identity.py and context services
room/      -> contracts/conversation.py and session context
memory/    -> cognitive/memory/ + features/memory_consolidation/ + adapters/stores/
limbic/    -> cognitive/affect/
agency/    -> cognitive/policy/ + cognitive/action/
llm/       -> adapters/llm/ + cognitive/action/response.py
tools/     -> adapters/tools/ + cognitive/action/tool_use.py
heartbeat/ -> runtime/scheduler.py
```

## MVP Scope Lock

For the first implementation scaffold, create only the minimal interfaces and text-only one-turn flow defined in the architecture document.

Do not implement during Phase 0.

Phase 1 should add or update architecture tests first.

Phase 2 scaffold should be limited to:

```text
core/ids.py
contracts/identity.py
contracts/observations.py
contracts/actions.py
cognitive/workspace/frame.py
cognitive/cycle/models.py
cognitive/cycle/pipeline.py
cognitive/cycle/frame_builder.py
cognitive/cycle/service.py
presentation/presenter.py
safety/action_gate.py
safety/output_filter.py
adapters/app_gateway/ports.py
features/definition.py
runtime/wiring/cognitive.py
runtime/wiring/presentation.py
```

## Architecture Tests to Prefer

Add or update tests that enforce:

- `iris/cognitive/**` does not import `iris/adapters/**`, `iris/runtime/**`, or `iris/features/**`.
- `iris/contracts/**` does not import `iris/cognitive/**`, `iris/adapters/**`, or `iris/runtime/**`.
- `WorkspaceFrame` is a frozen dataclass.
- `WorkspaceFrame` does not expose `dict[str, Any]`, `dict[str, object]`, or mutable context maps.
- `PipelineStep.run()` returns a typed `PipelineStepResult` subtype.
- `PipelineStep.run()` does not mutate `WorkspaceFrame`.
- `FrameBuilder` owns frame updates.
- `CognitiveCycle.run()` is coordinator-only.
- Features are registered through `FeatureDefinition`.
- `runtime/wiring/**` is the only place allowed to compose concrete dependencies.
- EventBus is not used as CognitiveCycle main flow.
- `action: str` dispatcher branches are not expanded for new behavior.

## Phase 0 Rules

Phase 0 is instruction and documentation preparation only.

Allowed:

- add `docs/architecture/current.md`
- update `AGENTS.md`
- update `.agents/project.md`
- add or update Skills
- update `.opencode/agents/*.md` and `.opencode/commands/*.md`
- mark Plugin/EventBus-centered guidance as legacy

Forbidden:

- create `iris/core/`, `iris/contracts/`, `iris/cognitive/`, `iris/runtime/`, `iris/adapters/`, `iris/features/`, `iris/presentation/`, or `iris/safety/` scaffold
- modify production runtime behavior
- add compatibility wrappers
- rewrite tests for Phase 1 early unless the user asks

## Completion Report

Report in Japanese by default.

```text
Changed files:
- ...

Old assumptions removed:
- ...

v1.2.1 rules added:
- ...

Legacy references left intentionally:
- ...

Validation:
- ...

Remaining conflicts before Phase 1:
- ...
```
