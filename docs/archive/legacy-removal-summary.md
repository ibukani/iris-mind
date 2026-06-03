# Legacy Architecture Removal Summary

## What was removed

The original Iris architecture was built around EventBus, PluginManager, and KernelProcess — a plugin-based framework inspired by multi-agent systems. This architecture grew complex and was replaced by the Cognitive Runtime Architecture v1.2.1.

### Deleted packages (Phase 12)

| Package | Description |
|---------|-------------|
| `iris/event` | EventBus, event types, event routing |
| `iris/kernel` | KernelProcess, PluginManager, supervisor |
| `iris/io` | I/O abstraction layer |
| `iris/account` | Account/Session management |
| `iris/room` | Room/Channel management |
| `iris/agency` | Agency/Orchestrator system |
| `iris/memory` | Full memory pipeline (sensory, short-term, episodic, semantic), LangMem |
| `iris/limbic` | Limbic system (appraisal, classification, mood, relationship) |
| `iris/llm` | LLM providers, bridge, prompt system |
| `iris/tools` | Tool registration and execution |
| `iris/heartbeat` | Heartbeat/scheduler |
| `iris/admin` | Admin/management interfaces |

### Deleted dependencies

grpcio, protobuf, googleapis-common-protos, langchain-core, langgraph, transformers, torch, chromadb, ollama, pydantic-compat, and others.

### Deleted infrastructure

- `proto/` — Protocol Buffers and gRPC service definitions
- `debug_tools/` — gRPC-based debug CLI
- Legacy skill files for Plugin/EventBus workflows

## Current architecture

The project now uses Cognitive Runtime Architecture v1.2.1:

```
main.py / iris.runtime.cli
→ iris.runtime (IrisApp, wiring, CLI)
→ iris.cognitive (CognitiveCycle, PipelineStep)
→ iris.contracts (domain contracts)
→ iris.presentation (output formatting)
→ iris.safety (safety gates)
→ iris.adapters (LLM adapters, memory adapters)
```

See `docs/architecture/current.md` for full details.

## Future features

Removed features (gRPC, Discord, LangMem, proactive, heartbeat, tools, room/account, full memory pipeline) may be rebuilt later as **target-native implementations**. Do not reintroduce EventBus, PluginManager, or KernelProcess.

## Migration phases

| Phase | Purpose |
|-------|---------|
| 0–8   | Initial Cognitive Runtime implementation |
| 9–11  | Migration control and cutover |
| 12    | Legacy architecture deletion |
| 12.1  | Legacy residue cleanup |
| 12.5  | Target architecture guards |
| 12.6  | Documentation consolidation |
