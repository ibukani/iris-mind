from __future__ import annotations

from collections.abc import Callable
from textwrap import dedent

from langchain_core.tools import StructuredTool

from iris.tools.decorator import get_tool_def, register_tools, tool
from iris.tools.models import ToolDef
from iris.tools.registry import ToolRegistry

# ── ToolDef ────────────────────────────────────────────────────


def _make_tool_def(
    name: str = "test_fn",
    description: str = "A test function",
    fn: Callable = lambda x: x,
    allowed_roles: set[str] | None = None,
    side_effect: bool = False,
) -> ToolDef:
    structured = StructuredTool.from_function(func=fn, name=name, description=description)
    return ToolDef(
        name=name,
        description=description,
        tool=structured,
        allowed_roles=allowed_roles,
        side_effect=side_effect,
    )


def test_tooldef_to_openai_tool() -> None:
    td = _make_tool_def(description="A test function")
    result = td.to_openai_tool()
    assert result["type"] == "function"
    assert result["function"]["name"] == "test_fn"
    assert result["function"]["description"] == "A test function"
    assert result["function"]["parameters"]["required"] == ["x"]


def test_tooldef_execute() -> None:
    td = _make_tool_def(fn=lambda msg: f"echo:{msg}")
    assert td.execute(msg="hello") == "echo:hello"


def test_tooldef_side_effect_default() -> None:
    td = _make_tool_def(name="t", fn=lambda: "")
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


# ── _generate_schema (replaced by StructuredTool) ──────────────


def test_structured_tool_schema_str_int() -> None:
    def fn(name: str, count: int = 1) -> str:
        return f"{name}:{count}"

    structured = StructuredTool.from_function(func=fn, description="test")
    schema = structured.get_input_jsonschema()
    assert schema["properties"]["name"]["type"] == "string"
    assert schema["properties"]["count"]["type"] == "integer"
    # Default values may or may not appear in schema
    assert "required" not in schema or "count" not in schema["required"]


# ── ToolRegistry ───────────────────────────────────────────────


def test_registry_register_and_get() -> None:
    r = ToolRegistry()
    td = _make_tool_def(fn=lambda: "hi")
    r.register(td)
    assert r.get("test_fn") is td
    assert r.get("missing") is None


def test_registry_list_tools() -> None:
    r = ToolRegistry()
    r.register(_make_tool_def(name="a", description="AA", fn=lambda: ""))
    r.register(_make_tool_def(name="b", description="BB", fn=lambda: ""))
    tools = r.list_tools()
    assert len(tools) == 2
    names = {t["function"]["name"] for t in tools}
    assert names == {"a", "b"}


def test_registry_list_tools_for_role() -> None:
    r = ToolRegistry()
    r.register(_make_tool_def(name="all", fn=lambda: "", allowed_roles=None))
    r.register(_make_tool_def(name="medium_only", fn=lambda: "", allowed_roles={"medium"}))
    all_tools = r.list_tools_for_role("high")
    assert len(all_tools) == 1
    assert all_tools[0]["function"]["name"] == "all"
    medium_tools = r.list_tools_for_role("medium")
    assert len(medium_tools) == 2


def test_registry_execute() -> None:
    r = ToolRegistry()
    r.register(_make_tool_def(name="echo", fn=lambda msg: f"echo:{msg}"))
    assert r.execute("echo", msg="test") == "echo:test"
    assert r.execute("unknown") == "Error: tool 'unknown' not found"


def test_registry_is_side_effect() -> None:
    r = ToolRegistry()
    r.register(_make_tool_def(name="normal", fn=lambda: "", side_effect=False))
    r.register(_make_tool_def(name="side", fn=lambda: "", side_effect=True))
    assert r.is_side_effect("side") is True
    assert r.is_side_effect("normal") is False
    assert r.is_side_effect("unknown") is False


def test_register_tools_helper() -> None:
    r = ToolRegistry()

    @tool()
    def first() -> str:
        return "first"

    @tool()
    def second() -> str:
        return "second"

    register_tools(r, first, second)

    assert r.get("first") is not None
    assert r.get("second") is not None


def test_discover_modules_registers_decorated_tools(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    package_dir = tmp_path / "fake_tools" / "sample"
    package_dir.mkdir(parents=True)
    (tmp_path / "fake_tools" / "__init__.py").touch()
    (package_dir / "__init__.py").touch()
    (package_dir / "server.py").write_text(
        dedent(
            """
            from iris.tools.decorator import tool

            @tool()
            def hello() -> str:
                return 'hi'
            """,
        ).lstrip(),
        encoding="utf-8",
    )

    registry = ToolRegistry()
    registry.discover_modules(["fake_tools"])

    assert registry.get("hello") is not None
