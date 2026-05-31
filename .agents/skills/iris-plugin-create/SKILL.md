---
name: iris-plugin-create
description: |
  Use ONLY when creating a brand-new top-level Iris Plugin class under iris/<plugin_name>/.
  Do NOT use: modifying existing plugins, adding hooks, adding @tool capabilities,
  adding LLM providers, adding store backends, or adding sub-plugins.
license: MIT
metadata:
  audience: developers
  workflow: iris-extension
---

## Purpose

Read this only when creating a brand-new top-level Iris Plugin. For internal file layout and naming details, also read `iris-plugin-structure`.

## Plugin Categories

- DOMAIN: core Iris domain modules such as memory, agency, limbic, room, account.
- INFRA: infrastructure modules such as llm, tools, io.
- TOOL: tool-facing modules that expose `@tool` capabilities.
- ADMIN: admin, CLI, diagnostics, or debug support.

## Steps

### 1. Create the directory

```text
iris/<plugin_name>/
├── __init__.py
├── manager.py
├── handler.py        # required when subscribing to EventBus
├── hooks.py          # optional when registering Hook handlers
├── models.py         # optional data types
└── protocols.py      # optional Protocols
```

For complex components, add `builder.py`. Do not create extra files until they have a real responsibility.

### 2. Create `__init__.py`

Use `PluginProtocol`, `PluginManifest`, and `PluginCategory`. Keep lifecycle methods thin. Move complex component wiring to `builder.py`.

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from iris.kernel.plugin import PluginCategory, PluginManifest, PluginProtocol

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager


MANIFEST = PluginManifest(
    name="example",
    version="0.1.0",
    description="Example Plugin",
    category=PluginCategory.DOMAIN,
)


class ExamplePlugin(PluginProtocol):
    @property
    def manifest(self) -> PluginManifest:
        return MANIFEST

    def init(self, manager: PluginManager) -> None:
        # Create components and provide public services here.
        ...

    async def start(self) -> None:
        ...

    async def shutdown(self) -> None:
        ...


plugin = ExamplePlugin()
```

### 3. Create `hooks.py` when needed

Use this only for HookRegistry integration. Do not mix EventBus subscription into `hooks.py`.

```python
def register_hooks(manager):
    hooks = manager.hook_registry
    hooks.register("llm.before_chat", _before_chat, priority=500)
```

### 4. Create `handler.py` when EventBus subscription is needed

If the Plugin subscribes to the EventBus, separate subscription logic into `handler.py`. Managers should not subscribe directly.

```python
class _ExampleEventHandler:
    def __init__(self, event_bus, manager):
        self._event_bus = event_bus
        self._manager = manager

    def subscribe(self) -> None:
        self._event_bus.subscribe("some.event", self._on_event)

    async def _on_event(self, event) -> None:
        await self._manager.handle(event)
```

Wire the handler from `__init__.py` or `builder.py`.

### 5. Check dependencies

- Use constructor injection for dependencies.
- Do not keep `PluginManager` inside logic classes.
- Depend on Protocols when collaborating with other Plugins.
- Keep the EventBus as the cross-layer integration mechanism.
- Avoid direct imports that create cycles.

### 6. Use Plugin configuration when needed

Read configuration through the kernel configuration object. Do not hard-code environment-specific values in Plugin logic. Add documentation updates when configuration shape changes.

### 7. Add tests

- Test manager logic without starting external services.
- Test EventBus handlers with fakes or minimal fixtures.
- Do not require real external LLM APIs or Ollama in unit tests.
- Add integration tests only when the boundary itself is being tested.

### 8. Disable during debugging

Use the existing Plugin configuration or runtime controls. Do not add ad hoc debug branches into production logic.

### 9. Validate

```bash
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

When fixes are allowed:

```bash
uv run ruff check --fix .
uv run ruff format .
```

### 10. Commit

Commit only when the user explicitly asks.

```bash
git add .
git commit -m "feat: add <plugin-name> plugin"
```

## Rules

- Create a new top-level Plugin only when a real top-level responsibility exists.
- Keep lifecycle methods small.
- Use `builder.py` when component construction becomes complex.
- Use `handler.py` for EventBus subscription.
- Use `hooks.py` for HookRegistry integration.
- Do not create sub-plugins through `PluginManager` lifecycle.
- Do not add compatibility layers unless explicitly requested.
- Do not add future-only hooks or unused extension points.

## Plugin Standard Implementation Contract

- `MANIFEST` is required.
- The Plugin class must implement `manifest`.
- The module should expose `plugin = XxxPlugin()`.
- `init()` is for dependency resolution and component registration.
- `start()` is for runtime start behavior.
- `shutdown()` is for cleanup.
- Public services should be provided through the manager / container mechanism used by the current implementation.

### Lifecycle Hook Usage

| Hook | Use for | Avoid |
|---|---|---|
| `init()` | dependency wiring, service registration | long-running tasks |
| `start()` | async startup, background services | dependency graph mutation |
| `shutdown()` | cleanup, closing resources | new work scheduling |
| reload-related hooks | configuration reload behavior | broad reinitialization without need |

## Plugin Internal File Split Rules

Follow `iris-plugin-structure` for full details. Minimum rules:

- 1 file = 1 responsibility.
- Split files over 200 lines when they contain multiple responsibilities.
- `manager.py` is orchestration, not EventBus subscription.
- `handler.py` owns EventBus subscription.
- `dispatcher.py` routes operations.
- `models.py` contains data structures.
- `protocol.py` / `protocols.py` contain Protocol definitions.
- `builder.py` wires components when `init()` becomes complex.

### Naming Rules

- File names: `snake_case.py`.
- Classes: `PascalCase`.
- Private internal classes/functions: leading underscore.
- Functions: `verb_object` style when possible.
- Constants: `UPPER_SNAKE_CASE`.

### Import Rules

- Use relative imports inside the same Plugin.
- Use absolute imports for other Plugins.
- Put type-only imports under `if TYPE_CHECKING:` to avoid runtime cycles.
- `__init__.py` should re-export only public API.

### Other Important Rules

- Do not refactor unrelated existing Plugins only to satisfy this template.
- Do not move provider-specific behavior into domain layers.
- Do not move memory persistence into limbic.
- Do not put domain logic into transport.
