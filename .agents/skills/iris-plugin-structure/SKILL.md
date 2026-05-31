---
name: iris-plugin-structure
description: |
  Use when: refactoring an existing plugin's internal file layout, or deciding component structure for a new plugin.
  Do NOT use: creating a plugin from scratch (see iris-plugin-create), adding hooks.
license: MIT
metadata:
  audience: developers
  workflow: iris-extension
---

## Purpose

Read this when organizing or splitting internal files of an existing Plugin, or when deciding component layout for a new Plugin. `iris-plugin-create` covers creation steps; this Skill defines structure and naming rules.

## Basic Principles

- **1 file = 1 responsibility.** Split a file when it exceeds a single responsibility.
- **Responsibility should be inferable from the file name.**
- **Class names should match file responsibility**: `manager.py` -> `XxxManager`, `protocols.py` -> `XxxProtocol`.
- **Internal implementation uses `_leading_underscore`** to discourage direct external use.
- **Dependency inversion (DIP)**: collaborate with other Plugins through `Protocol`, not concrete classes.
- **Dependency injection (DI)**: inject dependencies explicitly through constructors. Do not keep `PluginManager` inside logic classes as a service locator.
- **Separate pure logic from I/O**: scorers and extractors should only transform data. They should not perform file I/O or publish to EventBus.
- **EventBus subscription belongs in handlers**: managers must not subscribe directly. Put subscription in `handler.py` and wire it from `__init__.py` or `builder.py`.
- **No excessive refactor of existing Plugins**: do not perform a broad refactor only to force perfect compliance. Split only responsibilities relevant to the current change.

## Standard Directory Structure

```text
iris/<plugin_name>/
├── __init__.py           # MANIFEST + Plugin class + plugin instance
├── builder.py            # component assembly when init() is complex
├── manager.py            # core orchestrator
├── handler.py            # EventBus event handlers
├── dispatcher.py         # operation routing for store/retrieve/search/etc.
├── router.py             # conditional routing
├── protocol.py           # one Protocol definition
├── protocols.py          # multiple Protocol definitions
├── models.py             # dataclass / TypedDict / Pydantic models
├── base.py               # abstract base classes
├── hooks.py              # HookPoint registration
├── events.py             # Plugin-specific event types
├── utils.py              # utility functions
├── scorer.py             # scoring/evaluation
├── extractor.py          # entity extraction
├── renderer.py           # formatting/rendering
├── formatter.py          # output formatting
├── config.py             # configuration loading
└── tools/                # @tool definitions for TOOL category
    └── __init__.py
```

## File Naming by Responsibility

### Orchestration

| File | Contents | Class/function pattern | Example |
|---|---|---|---|
| `manager.py` | central orchestrator | `XxxManager` | `MemoryManager`, `AgencyManager` |
| `handler.py` | EventBus subscriptions | `_XxxEventHandler` private | `_MemoryEventHandler` |
| `dispatcher.py` | operation dispatch | `build_xxx_handlers()` + `_xxx_yyy()` | `build_store_handlers()` + `_store_sensory()` |
| `router.py` | conditional branching | `route_xxx_yyy()` | `route_after_llm(state) -> str` |
| `builder.py` | component assembly | `build_xxx(manager)` | `build_agency(manager) -> dict` |

### Data Structures

| File | Contents | Class pattern | Example |
|---|---|---|---|
| `models.py` | data type definitions | `XxxData`, `XxxState` | `TurnData`, `SearchResult`, `ExecutionState` |
| `protocol.py` | single Protocol | `XxxProtocol` | `MemoryManagerProtocol` |
| `protocols.py` | multiple Protocols | `XxxProtocol` | `EpisodicStoreProtocol`, `SemanticStoreProtocol` |
| `base.py` | abstract base | `_XxxBase` private | `_JsonlStore` |

### Single-purpose Processing

| File | Contents | Pattern | Example |
|---|---|---|---|
| `scorer.py` | scoring | `XxxScorer` Protocol + `DefaultXxxScorer` | `ImportanceScorer` + `DefaultImportanceScorer` |
| `extractor.py` | extraction/analysis | `XxxExtractor` Protocol + concrete extractor | `EntityExtractor` + `RegexEntityExtractor` |
| `renderer.py` | rendering | `render_xxx_context(...)` | `render_short_term_context(turns, ...) -> str` |
| `formatter.py` | output formatting | `XxxFormatter` | `CaptureFormatter` |
| `utils.py` | utilities | `xxx_yyy()` functions | `build_time_label() -> str` |
| `config.py` | config loading | `XxxConfig` | - |

### Hooks and Events

| File | Contents | Function pattern |
|---|---|---|
| `hooks.py` | HookPoint registration | `register_hooks(manager)` |
| `events.py` | event type definitions | `XxxEvent(DataClass)` |

## Split Triggers

| Condition | Extract to |
|---|---|
| `__init__.py` `init()` body > 50 lines | `builder.py` |
| File > 200 lines and has 2+ responsibilities | split by responsibility |
| One or more EventBus subscriptions | `handler.py` required |
| 3+ Protocol classes | `protocols.py` |
| Base class exists | `base.py` |
| File contains only module-level functions | keep if single-responsibility, otherwise split into `utils.py` / `router.py` |
| 2+ static methods | module-level functions in `utils.py` |
| Component creation is complex (> 10 lines) | `builder.py` |

## Detailed Naming Rules

### File Names

- Use `snake_case.py`.
- Avoid abbreviations (`di.py` -> `service_container.py`).
- Prefer singular names, except container modules such as `protocols.py` or `stores.py`.
- Do not use numeric suffixes such as `handler2.py`; split by responsibility instead.

### Class Names

- Use `PascalCase` and align with the file responsibility.
- `manager.py` -> `XxxManager`.
- `protocols.py` -> `XxxProtocol`.
- Internal-only classes use `_` prefix, such as `_MemoryEventHandler` or `_JsonlStore`.
- Prefer `XxxProtocol` for `typing.Protocol` subclasses.

### Function Names

- Use `snake_case`.
- Module-level functions should generally use `verb_object` style.
- Private functions use `_prefix`.
- Event handlers use `_on_xxx_event`; Hook handlers use `_xxx_hook`.

### Constants

- Use `UPPER_SNAKE_CASE`.
- Keep module-level constants near the top of the file.

## Private Visibility Rules

| Visibility | Naming | Intended use |
|---|---|---|
| Public API | `XxxManager`, `build_xxx()` | intended for use from other Plugins |
| Internal implementation | `_XxxHandler`, `_xxx_helper()` | same Plugin only |
| Same file only | nested function / nested class | function scope only |

## Package Import Rules

- Inside the same Plugin, prefer relative imports such as `from .manager import XxxManager`.
- Across Plugins, use absolute imports such as `from iris.memory.manager import MemoryManager`.
- For type-only references, import inside `if TYPE_CHECKING:` to avoid runtime cycles.
- `__init__.py` should re-export only public API. Direct access to internal modules is discouraged.

## Sub-plugin and Provider Structure

```text
iris/llm/providers/
├── __init__.py               # calls discover_providers()
├── base.py                   # BaseLLMProvider + registry
├── ollama.py
├── openrouter.py
└── google.py

iris/tools/builtins/
├── __init__.py
└── <tool_name>/
    └── server.py             # register(registry) function
```

- LLM providers use auto-registration through `BaseLLMProvider.provider_name`.
- Tool capabilities use `register(registry)` / decorators.
- Use provider/tool names directly as file names, such as `ollama.py` or `git.py`.

## Implementation Patterns

### Builder and `__init__.py`

```python
# iris/<plugin>/__init__.py
from __future__ import annotations
from typing import TYPE_CHECKING

from iris.kernel.plugin import PluginProtocol
from .builder import build_components

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager


class XxxPlugin(PluginProtocol):
    def init(self, manager: PluginManager) -> None:
        self._components = build_components(manager)
```

```python
# iris/<plugin>/builder.py
from __future__ import annotations
from typing import Any, TYPE_CHECKING

from iris.event.event_bus import EventBus

from .manager import XxxManager

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager


def build_components(manager: PluginManager) -> dict[str, Any]:
    event_bus = manager.resolve(EventBus)
    component = XxxManager(event_bus=event_bus)
    manager.provide(XxxManager, component)
    return {"manager": component}
```

### Handler for EventBus Subscription

```python
# iris/<plugin>/handler.py
from __future__ import annotations


class _XxxEventHandler:
    def __init__(self, event_bus, manager):
        self._event_bus = event_bus
        self._manager = manager

    def subscribe(self) -> None:
        self._event_bus.subscribe("some.event", self._on_event)

    async def _on_event(self, event) -> None:
        await self._manager.handle_event(event)
```

### Protocol + Implementation

```python
# iris/<plugin>/protocols.py
from __future__ import annotations
from typing import Protocol


class XxxStoreProtocol(Protocol):
    async def save(self, item: object) -> None: ...
```

### Dispatcher

```python
def build_store_handlers(manager):
    return {
        "sensory": lambda item: manager.store_sensory(item),
        "short_term": lambda item: manager.store_short_term(item),
    }
```

## Existing Plugin Structure Examples

Use existing code as the source of truth. Before changing structure, inspect the current implementation, imports, call sites, tests, plugin registration, and runtime entrypoints.

## Rules

- Do not refactor only to satisfy the template.
- Do not add unused abstraction.
- Keep public API small.
- Preserve async cancellation and streaming behavior.
- Do not put provider-specific logic into execution / limbic / memory.
- Do not move persistence responsibilities into limbic.
- Do not put domain logic into transport.
