---
name: iris-plugin-hook
description: |
  Use when: adding a new handler to an existing HookPoint, or defining a new HookPoint.
  Do NOT use: creating a new plugin, adding sub-plugins, adding capabilities.
license: MIT
metadata:
  audience: developers
  workflow: iris-extension
---

## Purpose

Read this when registering a new handler to an existing HookPoint or defining a new HookPoint.

## HookPoint List

| HookPoint | Timing | Signature | Example use |
|---|---|---|---|
| `llm.before_chat` | Immediately before LLM call | `(messages: list) -> list` | LoRA adapter injection, prompt transformation |
| `llm.after_chat` | Immediately after LLM response | `(response: dict) -> dict` | Response filtering, emotion analysis |
| `llm.before_stream` | For each stream chunk | `(chunk: str) -> str` | Real-time filtering |
| `memory.before_store` | Before episode storage | `(episode: Episode) -> Episode` | Emotion tagging |
| `memory.after_search` | After memory search | `(hits: list[SearchHit]) -> list[SearchHit]` | Search result reranking |
| `agency.plan_decided` | When a plan is decided | `(plan: Plan) -> Plan` | Plan adjustment, constraint addition |
| `agency.before_exec` | Before execution | `(state: ExecState) -> ExecState` | Execution state injection |
| `io.before_send` | Before sending | `(msg: Message) -> Message` | Send filtering |
| `io.after_receive` | After receiving | `(msg: Message) -> Message` | Receive transformation |
| `io.dispatch` | Dispatch of IO received messages | `(ctx: dict) -> dict` | Command routing |

## HookPriority

| Range | Category | Example |
|---|---|---|
| 0-99 | SYSTEM | Required system hooks |
| 100-999 | CORE | Core layer hooks |
| 1000-4999 | FEATURE | Feature plugin hooks |
| 5000-9999 | USER | External plugin hooks |

Handlers run in ascending priority order. Within the same priority, registration order is used. `HookPriority` defines ranges for validation; pass an integer inside the appropriate range when registering.

## Steps

### Register a handler to an existing HookPoint

Option 1: manual registration.

```python
# iris/<plugin>/hooks.py
def register_hooks(manager):
    hooks = manager.hook_registry

    def _my_before_chat(messages):
        return messages

    hooks.register("llm.before_chat", _my_before_chat, priority=500)
```

Option 2: `@hook` decorator, preferred.

```python
# iris/<plugin>/hooks.py
from iris.kernel.plugin import hook

class MyHooks:
    @hook("llm.before_chat", priority=100)
    def _my_before_chat(self, messages):
        return messages

    @hook("memory.after_search", priority=500)
    def _my_after_search(self, hits):
        return hits
```

Call `manager.hook_registry.register_decorated(self)` in Plugin `init()` to automatically register all `@hook` methods.

```python
def init(self, manager):
    manager.hook_registry.register_decorated(self)
```

Rules:

- A handler receives input and returns transformed data of the same shape.
- If a handler raises, later handlers still run.
- Use `priority` to control order.

### Async handlers

```python
async def _my_async_hook(data):
    await some_async_operation()
    return data

hooks.register("llm.before_chat", _my_async_hook, priority=500)
```

`HookRegistry.execute()` detects async handlers automatically. The caller is expected to `await` execution.

### Add a new HookPoint

1. Add the definition to `iris/kernel/plugin/hook_points.py`:

```python
HOOK_POINTS: dict[str, HookPoint] = {
    ...
    "agency.plan_decided": HookPoint("agency.plan_decided", "when a plan is decided"),
}
```

2. Call `execute()` from the caller:

```python
result = await manager.hook_registry.execute("agency.plan_decided", plan)
```

3. Register a handler in the Plugin-side `hooks.py`:

```python
hooks.register("agency.plan_decided", _on_plan_decided, priority=1000)
```

## Rules

- Do not mutate input data in place; return new transformed data.
- Exceptions are logged and swallowed. They must not block later handlers.
- `HookRegistry.execute()` is async; `execute_sync()` is sync.
- Always register a new HookPoint in the `HOOK_POINTS` dict.
- HookPoint names must follow dot-separated `layer.action` naming.
- `priority` must be an integer within a `HookPriority` range.
