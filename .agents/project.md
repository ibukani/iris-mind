# Iris Project Brief

This file is a compact helper note for Iris-specific scope and responsibility boundaries. Use `.agents/skills/iris-dev-workflow/SKILL.md` as the source for ordinary development rules, and `docs/architecture.md` as the source for design decisions.

## Scope

- Iris is a Python AI companion / assistant Kernel. It handles autonomous behavior and task execution, and ultimately aims to support self-evolution.
- This repository contains the Kernel itself. UI and external clients belong to separate projects.
- LLM providers such as Ollama and OpenRouter are switched through configuration.
- Models support both a single-model setup and role-based multi-model setups.
- Configuration lives in `config.yaml`. `model.providers` defines provider connection information, and `model.models[].provider` selects the provider for each model.

## Main Modules

- `iris/kernel/`: process management, DI, Plugin lifecycle, commands.
- `iris/event/`: Global EventBus, event types, tracing.
- `iris/io/`: input/output, gRPC, sessions, permissions.
- `iris/account/`: user identity, external identity linkage, presence.
- `iris/room/`: Room CRUD, membership, account linkage.
- `iris/memory/`: sensory / short-term / long-term memory.
- `iris/limbic/`: emotion, mood, relationship.
- `iris/agency/`: planning, inhibition, execution.
- `iris/llm/`: providers, context window, tokenizer, prompts.
- `iris/tools/`: `@tool`, ToolRegistry, builtins.
- `iris/admin/`: CLI administration.

### Design Policy: Iris Identity and Rooms

- **Only one Iris exists as an individual.**
- Rooms are a system for adding conversation locations, not copies of Iris.
- Emotion (`limbic`) is global. It is not managed per room.
- Relationship is per user (`Account`), not per room.
- If the same user talks to Iris in multiple rooms, intimacy and related relationship values are shared.

## Boundaries

- `iris/kernel/` is a domain layer. Do not put external service implementations directly into it.
- `iris/llm/` and `iris/tools/` are infrastructure layers injected into the kernel.
- `iris/io/`, `iris/agency/`, `iris/memory/`, `iris/event/`, `iris/account/`, and `iris/room/` are independent layers separated from the kernel.
- All layers stay loosely coupled through the EventBus (`iris/event/`).
- `debug_tools/` may depend on `iris/`, but `iris/` must not depend on `debug_tools/`.
- For IPC and process design details, read `docs/architecture.md`.

## Workflows

- Ordinary development: `.agents/skills/iris-dev-workflow/SKILL.md`
- Capability addition: `.agents/skills/capability-pattern/SKILL.md`
- Documentation update check: `.agents/skills/doc-sync/SKILL.md`
- Design changes: record them in `docs/architecture.md` and update only the required design documents.

## Context Rules

- Do not write branch status, completed tasks, or past decision logs here.
- Before implementation, read only the files required for the task. For large design documents, inspect only relevant sections.
- After changes, ensure they do not conflict with the loading policy in `AGENTS.md` and `.agents/README.md`.
- Do not add a detailed directory tree here. Use `rg --files iris` to inspect actual code when needed.
