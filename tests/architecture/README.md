# Architecture Tests for v1.2.1 Cognitive Runtime

Tests in this directory enforce dependency and design rules of the
[v1.2.1 target architecture](../../docs/architecture/cognitive-runtime-v1.2.1.md).

## Test Files

| File | Enforces |
|---|---|
| `test_cognitive_runtime_boundaries.py` | Layer dependency direction, legacy module quarantine, runtime wiring rules |
| `test_cognitive_runtime_contracts.py` | WorkspaceFrame immutability, CognitiveCycle coordinator role, PipelineStep typed results |
| `test_cognitive_runtime_anti_patterns.py` | Forbidden patterns: service locator, EventBus main flow, PluginManager extension, `action: str` dispatch, untyped contexts, global registries |

## Legacy Tests

The remaining `test_*.py` files in this directory enforce rules for the legacy
Plugin/EventBus-centered architecture. They are migration source tests —
they may be removed or replaced as legacy modules are migrated.

## Behaviour When Target Modules Do Not Exist

Many tests require v1.2.1 target modules (e.g. `iris/cognitive/`, `iris/contracts/`)
that have not yet been implemented. These tests skip with a clear reason
rather than fail. As each module is added, the corresponding tests activate.

## Run

```bash
pytest tests/architecture/ -v
```

## See Also

- `docs/architecture/cognitive-runtime-v1.2.1.md`
- `.agents/project.md`
