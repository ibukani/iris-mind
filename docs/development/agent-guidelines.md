# AI Coding Agent Guidelines

## Architecture source of truth

The Cognitive Runtime Architecture v1.2.1 (`docs/architecture/current.md`) is the sole source of truth.

The legacy EventBus/PluginManager/Kernel architecture has been deleted. Do not reintroduce it.

## Do not add

- EventBus, PluginManager, KernelProcess, Supervisor
- Service locator, global registry, hidden DI container
- gRPC, Protocol Buffers, Discord integration
- LangMem, LangGraph, multi-agent orchestration
- Heartbeat/scheduler system
- Room/Account/Session management
- Tool execution framework
- Full memory pipeline (sensory, short-term, episodic, semantic)

## Wiring rules

- Use explicit constructor injection in wiring files
- Wiring files must not call `resolve()`, `get_service()`, or `locate()`
- Wiring files must not define domain classes (CognitiveCycle, PipelineStep, etc.)

## Adding features

- Add features as target-native implementations in `iris/features/`
- Use `FeatureDefinition` protocol from `iris/features/definition.py`
- Features must not mutate `WorkspaceFrame` directly
- Features must not import from `iris/adapters`, `iris/runtime`, `iris/presentation`, `iris/safety`

## Testing rules

- All tests must validate the current target architecture
- No new tests should reference deleted legacy packages
- Architecture guards in `tests/architecture/` must remain passing
