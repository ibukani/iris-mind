---
name: capability-pattern
description: |
  Use ONLY when adding a new Tool/capability (new @tool decorated function with register function).
  Do NOT use: creating plugins, adding hooks, adding LLM providers, adding store backends.
license: MIT
metadata:
  audience: developers
  workflow: iris-extension
---

## Purpose

Read this only when adding a new capability / tool to Iris. Treat existing capabilities and the implementation under `iris/tools/` as the source of truth.

## Steps

1. Decide where to place it.

- Standard location: `iris/tools/builtins/<name>/server.py`
- Auto-discovery: `discover_modules()` scans for `server.py` under `iris/tools/builtins/` and registers it automatically.

2. Define it with `@tool()`.

```python
from iris.tools.decorator import tool


@tool(allowed_roles={"base", "smart"})
def my_tool(param: str) -> str:
    """Tool description. This docstring becomes the tool description."""
    return f"Result: {param}"
```

- JSON Schema is generated from type hints.
- Parameters without default values are required; parameters with default values are optional.
- Use `descriptions={...}` when parameter descriptions are needed.
- Use `side_effect=True` for action tools whose result should not be returned to the conversation.

3. Add `register()` for auto-discovery.

```python
def register(registry):
    registry.register_decorated(my_tool)
```

For multiple tools, refer to existing examples using `iris.tools.decorator.register_decorated_tools`.

4. Add tests.

- Add tests under `tests/tools/` or the existing relevant test area.
- At minimum, verify name / schema / `side_effect` / `allowed_roles` through `get_tool_def()`.
- For tools with runtime side effects, test with fakes or temporary directories.

5. Update documentation and structural memory.

- Update `.iris/config/iris_profile.md` only when the change affects Iris self-recognition, available capabilities, or behavior.
- Do not update `.iris/config/iris_profile.md` for purely internal implementation changes.
- Update `docs/` or `docs/adr/` when needed.
- Use `.agents/skills/doc-sync/SKILL.md` to check for missed documentation updates.

6. Validate.

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

7. Commit.

Commit only when the user explicitly asks.

```bash
git add .
git commit -m "feat: add <tool-name> capability"
```

## Rules

- Use `@tool()` for new additions.
- Add `__init__.py` to packages that need it.
- Prefer `str` return values.
- If `allowed_roles` is omitted, all roles may use the tool.
- Do not create a new top-level Plugin for a capability / tool addition.
