from __future__ import annotations

from iris.tools.decorator import _generate_schema, get_tool_def, tool
from iris.tools.models import ToolDef
from iris.tools.registry import ToolRegistry

# ── ToolDef ────────────────────────────────────────────────────


def test_tooldef_to_openai_tool() -> None:
    td = ToolDef(
        name="test_fn",
        description="A test function",
        parameters={
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": ["x"],
        },
        fn=lambda x: x,
    )
    result = td.to_openai_tool()
    assert result["type"] == "function"
    assert result["function"]["name"] == "test_fn"
    assert result["function"]["description"] == "A test function"
    assert result["function"]["parameters"]["required"] == ["x"]


def test_tooldef_execute() -> None:
    td = ToolDef(name="echo", description="", parameters={}, fn=lambda msg: f"echo:{msg}")
    assert td.execute(msg="hello") == "echo:hello"


def test_tooldef_side_effect_default() -> None:
    td = ToolDef(name="t", description="", parameters={}, fn=lambda: "")
    assert td.side_effect is False


# ── ToolResult ─────────────────────────────────────────────────


def test_toolresult_defaults() -> None:
    from iris.tools.models import ToolResult

    r = ToolResult()
    assert r.success is True
    assert r.data is None
    assert r.error is None
    assert r.content == ""


# ── @tool decorator ────────────────────────────────────────────


@tool(description="Add two numbers")
def add(a: int, b: int) -> int:
    return a + b


def test_tool_decorator_attaches_def() -> None:
    td = get_tool_def(add)
    assert td is not None
    assert td.name == "add"
    assert td.description == "Add two numbers"
    assert td.side_effect is False


def test_tool_decorator_schema() -> None:
    td = get_tool_def(add)
    assert td is not None
    params = td.parameters
    assert params["type"] == "object"
    assert "a" in params["properties"]
    assert "b" in params["properties"]
    assert params["properties"]["a"]["type"] == "integer"
    assert params["properties"]["b"]["type"] == "integer"
    assert params["required"] == ["a", "b"]


@tool(side_effect=True)
def notify(msg: str) -> str:
    """Send a notification"""
    return f"notified: {msg}"


def test_tool_decorator_side_effect() -> None:
    td = get_tool_def(notify)
    assert td is not None
    assert td.side_effect is True
    assert td.description == "Send a notification"


@tool(allowed_roles={"smart"})
def restricted_task(data: str) -> str:
    return f"processed: {data}"


def test_tool_decorator_allowed_roles() -> None:
    td = get_tool_def(restricted_task)
    assert td is not None
    assert td.allowed_roles == {"smart"}


# ── _generate_schema ───────────────────────────────────────────


def test_generate_schema_str_int() -> None:
    def fn(name: str, count: int = 1) -> str:  # type: ignore[empty-body]
        ...

    schema = _generate_schema(fn)
    assert schema["properties"]["name"]["type"] == "string"
    assert schema["properties"]["count"]["type"] == "integer"
    assert "required" not in schema or "count" not in schema["required"]


def test_generate_schema_descriptions() -> None:
    def fn(x: str) -> str:  # type: ignore[empty-body]
        ...

    schema = _generate_schema(fn, descriptions={"x": "The input value"})
    assert schema["properties"]["x"]["description"] == "The input value"


# ── ToolRegistry ───────────────────────────────────────────────


def test_registry_register_and_get() -> None:
    r = ToolRegistry()
    td = ToolDef(name="hello", description="", parameters={}, fn=lambda: "hi")
    r.register(td)
    assert r.get("hello") is td
    assert r.get("missing") is None


def test_registry_list_tools() -> None:
    r = ToolRegistry()
    r.register(ToolDef(name="a", description="AA", parameters={}, fn=lambda: ""))
    r.register(ToolDef(name="b", description="BB", parameters={}, fn=lambda: ""))
    tools = r.list_tools()
    assert len(tools) == 2
    names = {t["function"]["name"] for t in tools}
    assert names == {"a", "b"}


def test_registry_list_tools_for_role() -> None:
    r = ToolRegistry()
    r.register(ToolDef(name="all", description="", parameters={}, fn=lambda: "", allowed_roles=None))
    r.register(ToolDef(name="smart_only", description="", parameters={}, fn=lambda: "", allowed_roles={"smart"}))
    all_tools = r.list_tools_for_role("base")
    assert len(all_tools) == 1
    assert all_tools[0]["function"]["name"] == "all"
    smart_tools = r.list_tools_for_role("smart")
    assert len(smart_tools) == 2


def test_registry_execute() -> None:
    r = ToolRegistry()
    r.register(ToolDef(name="echo", description="", parameters={}, fn=lambda msg: f"echo:{msg}"))
    assert r.execute("echo", msg="test") == "echo:test"
    assert r.execute("unknown") == "Error: tool 'unknown' not found"


def test_registry_is_side_effect() -> None:
    r = ToolRegistry()
    r.register(ToolDef(name="normal", description="", parameters={}, fn=lambda: ""))
    r.register(ToolDef(name="side", description="", parameters={}, fn=lambda: "", side_effect=True))
    assert r.is_side_effect("side") is True
    assert r.is_side_effect("normal") is False
    assert r.is_side_effect("unknown") is False
