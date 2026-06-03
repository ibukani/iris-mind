# Legacy Deletion Record

## Phase 12: Hard Legacy Architecture Deletion (complete)

Phase 12 has deleted the legacy Plugin/EventBus architecture entirely.

## What was deleted

All legacy packages:

- `iris/event` — EventBus, event types, tracer
- `iris/kernel` — PluginManager, KernelProcess, Supervisor, config
- `iris/io` — IOManager, gRPC transport, session management, auth
- `iris/account` — Account dispatcher, manager, store
- `iris/room` — Room dispatcher, manager, store, handler
- `iris/agency` — Planning, execution (LangGraph), inhibition
- `iris/memory` — Sensory, short-term, long-term, LangMem, archive
- `iris/limbic` — Appraisal, relationship, mood, state
- `iris/llm` — LLM bridge, provider discovery, context window
- `iris/tools` — Tool registry, decorators, builtins
- `iris/heartbeat` — Heartbeat service
- `iris/admin` — Admin CLI

All legacy tests:

- `tests/agency/`, `tests/kernel/`, `tests/llm/`, `tests/limbic/`
- `tests/memory/`, `tests/room/`, `tests/account/`, `tests/tools/`
- `tests/legacy/`, `tests/fakes/`
- Legacy architecture tests: `test_dependency_rules.py`,
  `test_handler_only_subscriptions.py`, `test_layer_imports.py`,
  `test_no_service_locator.py`, `test_plugin_boundaries.py`,
  `test_public_init_side_effects.py`, `test_legacy_audit.py`

Proto and gRPC:

- `proto/` directory and all `.proto` files
- Generated `*_pb2.py` and `*_pb2_grpc.py` files

## What was kept

Target runtime packages:

- `iris/core` — Foundation types
- `iris/contracts` — Domain contracts
- `iris/cognitive` — Cognitive cycle, pipeline, workspace
- `iris/presentation` — Output formatting
- `iris/safety` — Safety gates
- `iris/features` — Feature definitions
- `iris/adapters` — LLM/memory adapters (FakeLLM, OpenAI, etc.)
- `iris/runtime` — App composition, CLI, wiring

Target tests:

- `tests/architecture/` (updated for post-deletion guards)
- `tests/adapters/`, `tests/cognitive/`, `tests/contracts/`
- `tests/features/`, `tests/runtime/`
- `tests/test_oneturn_flow.py`

## Dependencies removed from pyproject.toml

Legacy-only dependencies removed:

- `grpcio`, `protobuf`
- `langchain-core`, `langgraph`, `langchain`, `langchain-ollama`,
  `langchain-openai`, `langchain-chroma`, `langmem`
- `transformers`, `torch`, `tokenizers`
- `chromadb`, `rank-bm25`
- `ollama`
- `pandas`, `orjson`, `instructor`
- `loguru`, `tenacity`, `cachetools`

## Current runtime path

```
main.py / iris.runtime.cli
→ IrisApp
→ CognitiveCycle (PerceptionStep → ActionSelectionStep)
→ target LLM adapter (FakeLLMClient or OpenAI adapter)
→ Presenter / Safety
→ stdout
```

## What remains to be rebuilt (future)

The following features may be rebuilt as target-native implementations:

- Full memory system (episodic/semantic/vector stores)
- Tool execution
- Proactive / autonomous behavior
- gRPC / Discord transport
- Relationship / limbic system
- Room/account management

## Validation commands

```bash
uv run python main.py --text "hello"
uv run python -m iris.runtime.cli --text "hello"
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
```
